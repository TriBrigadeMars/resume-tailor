"""MCP (Model Context Protocol) server integration for ResumeTailor.

Connects to configured MCP servers (stdio or streamable HTTP), discovers their
tools, and runs an agentic tool-calling loop so the LLM can call external tools
(e.g. web search, URL fetching, file access) while generating.

MCP servers can be configured two ways:
  1. Env var MCP_SERVERS (JSON) — good for Docker:
       [{"name":"web","type":"http","url":"http://host:port/mcp"}]
       [{"name":"fs","type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}]
  2. From the web UI (stored in the browser and sent with each request).

Note: the mcp SDK uses anyio task groups that must be entered and exited
within the same task. We therefore run the whole connect -> use -> close
lifecycle inside a single asyncio.run() coroutine.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os

import llm

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    try:
        from mcp.client.streamable_http import streamable_http_client as _streamable_client
    except ImportError:  # older SDK naming
        from mcp.client.streamable_http import streamablehttp_client as _streamable_client
except Exception:  # pragma: no cover - mcp SDK not installed
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    _streamable_client = None


def get_servers_from_env() -> list[dict]:
    """Read MCP server config from the MCP_SERVERS environment variable."""
    raw = os.environ.get("MCP_SERVERS", "[]")
    try:
        servers = json.loads(raw)
        return servers if isinstance(servers, list) else []
    except Exception:
        return []


def _tool_schema(tool) -> dict:
    """Return the input schema for an MCP Tool across SDK versions."""
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    return schema or {"type": "object", "properties": {}}


class MCPManager:
    """Connects to MCP servers and exposes their tools to the LLM."""

    def __init__(self, servers: list[dict]):
        self.servers = servers or []
        self._exit_stack = contextlib.AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}

    async def connect_all(self) -> None:
        if ClientSession is None:
            return
        for server in self.servers:
            name = server.get("name") or server.get("url") or "mcp"
            try:
                if server.get("type") == "stdio":
                    params = StdioServerParameters(
                        command=server["command"],
                        args=server.get("args", []),
                        env=server.get("env"),
                    )
                    read, write = await self._exit_stack.enter_async_context(
                        stdio_client(params)
                    )
                else:
                    read, write, _ = await self._exit_stack.enter_async_context(
                        _streamable_client(server["url"])
                    )
                session = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._sessions[name] = session
            except Exception as exc:  # noqa: BLE001
                print(f"MCP: failed to connect to '{name}': {exc}")

    async def list_tools(self) -> list[dict]:
        """Return all tools in OpenAI function-calling format."""
        tools = []
        for name, session in self._sessions.items():
            try:
                result = await session.list_tools()
                for t in result.tools:
                    tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": f"{name}__{t.name}",
                                "description": t.description or "",
                                "parameters": _tool_schema(t),
                            },
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"MCP: list_tools failed for '{name}': {exc}")
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        server_name, _, name = tool_name.rpartition("__")
        session = self._sessions.get(server_name)
        if not session:
            return f"Error: no MCP server named '{server_name}'"
        try:
            result = await session.call_tool(name, arguments or {})
            parts = []
            for block in result.content:
                parts.append(getattr(block, "text", None) or str(block))
            return "\n".join(parts)
        except Exception as exc:  # noqa: BLE001
            return f"Error calling {tool_name}: {exc}"

    async def close(self) -> None:
        await self._exit_stack.aclose()

    # ---- single-coroutine public API ----

    def list_tools_sync(self) -> tuple[list[dict], str]:
        """Connect, list tools, close. Returns (tools, error)."""

        async def _run():
            async with self._exit_stack:
                await self.connect_all()
                return await self.list_tools()

        try:
            return asyncio.run(_run()), ""
        except Exception as exc:  # noqa: BLE001
            return [], str(exc)

    def run_tool_loop(
        self,
        backend: str,
        model: str,
        messages: list[dict],
        api_key: str = "",
        temperature: float = 0.4,
        max_iterations: int = 5,
    ) -> str | None:
        """Connect, run an agentic tool-calling loop, close.

        Returns the final LLM content, or None if no MCP tools were available
        (caller should fall back to plain generation).
        """

        async def _run():
            async with self._exit_stack:
                await self.connect_all()
                tools = await self.list_tools()
                if not tools:
                    return None
                current = list(messages)
                final_content = ""
                for _ in range(max_iterations):
                    content, tool_calls = await asyncio.to_thread(
                        llm.chat_with_tools,
                        backend, model, current, tools,
                        temperature=temperature, api_key=api_key,
                    )
                    if not tool_calls:
                        return content or final_content
                    # Preserve the assistant response as ONE message carrying the
                    # complete tool_calls array, then one tool message per result.
                    current.append(
                        {"role": "assistant", "content": content, "tool_calls": tool_calls}
                    )
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except Exception:
                            args = {}
                        result = await self.call_tool(name, args)
                        current.append(
                            {"role": "tool", "tool_call_id": tc.get("id"), "content": result}
                        )
                    final_content = content
                return final_content

        try:
            return asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            print(f"MCP: tool loop failed: {exc}")
            return None
