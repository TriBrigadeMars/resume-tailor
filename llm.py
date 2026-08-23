"""LLM client for self-hosted + remote backends.

Local backends are auto-detected (Ollama, LM Studio). Remote backends
(OpenRouter, LM Studio Bionic) are user-configured with an API key.

All backends speak an OpenAI-compatible chat completions API.
"""

from __future__ import annotations

import urllib.request
import urllib.error
import json
import os
import ssl

# ---------------------------------------------------------------------------
# Backend definitions
# ---------------------------------------------------------------------------

# Base URLs are configurable via environment variables so the app can reach
# Ollama / LM Studio running on the Docker host (host.docker.internal).
LOCAL_BACKENDS = [
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        "models_endpoint": "/api/tags",
        "models_key": "models",
        "name_key": "name",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio / Bionic (local)",
        "base_url": os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234"),
        "models_endpoint": "/v1/models",
        "models_key": "data",
        "name_key": "id",
    },
]

REMOTE_BACKENDS = [
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api",
        "models_endpoint": "/v1/models",
        "models_key": "data",
        "name_key": "id",
        "auth_header": lambda key: ("Authorization", f"Bearer {key}"),
    },
    {
        "id": "lmstudiobionic",
        "label": "LM Studio Bionic",
        "base_url": "https://api.lmstudio.ai",  # default; user can override endpoint
        "models_endpoint": "/v1/models",
        "models_key": "data",
        "name_key": "id",
        "auth_header": lambda key: ("Authorization", f"Bearer {key}"),
    },
]


def _backends_by_id():
    return {b["id"]: b for b in LOCAL_BACKENDS + REMOTE_BACKENDS}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_json(
    url: str,
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: float = 3.0,
):
    """Smallest possible JSON HTTP helper (stdlib only)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = headers.copy() if headers else {}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        url, data=data, headers=hdrs, method="POST" if data else "GET"
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_backends() -> list[dict]:
    """Return local backends that are reachable, each with its model list."""
    available = []
    for backend in LOCAL_BACKENDS:
        try:
            body = _http_json(backend["base_url"] + backend["models_endpoint"])
            raw = body.get(backend["models_key"], [])
            models = sorted(m.get(backend["name_key"], "") for m in raw)
            models = [m for m in models if m]
            if models:
                available.append(
                    {
                        "id": backend["id"],
                        "label": backend["label"],
                        "base_url": backend["base_url"],
                        "models": models,
                    }
                )
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            continue
    return available


def get_remote_backends() -> list[dict]:
    """Return remote backend metadata (models are not auto-detected)."""
    return [
        {
            "id": b["id"],
            "label": b["label"],
            "base_url": b["base_url"],
            "needs_api_key": True,
            "models": [],  # filled in by list_models once key is provided
        }
        for b in REMOTE_BACKENDS
    ]


def list_models(backend_id: str, api_key: str = "", timeout: float = 8.0) -> list[str]:
    """Fetch model list for any backend (local or remote).

    For remote backends, an api_key is required.
    """
    bmap = _backends_by_id()
    backend = bmap.get(backend_id)
    if not backend:
        return []

    headers = {}
    if backend.get("auth_header"):
        k, v = backend["auth_header"](api_key)
        headers[k] = v

    try:
        body = _http_json(
            backend["base_url"] + backend["models_endpoint"],
            headers=headers,
            timeout=timeout,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return []

    raw = body.get(backend["models_key"], [])
    models = sorted(m.get(backend["name_key"], "") for m in raw)
    return [m for m in models if m]


def _require_api_key(backend: dict, api_key: str) -> None:
    """Raise if a remote backend requires an API key and none was supplied."""
    if backend.get("auth_header") and not api_key:
        raise RuntimeError(
            f"'{backend['label']}' needs an API key. Enter it in Settings."
        )


def chat_completion(
    backend_id: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 4096,
    timeout: float = 300.0,
    api_key: str = "",
) -> str:
    """Send a chat request and return the text reply.

    For remote backends, pass api_key. Local backends ignore it.
    """
    bmap = _backends_by_id()
    backend = bmap.get(backend_id)
    if not backend:
        raise RuntimeError(f"Unknown backend: {backend_id}")

    _require_api_key(backend, api_key)

    url = backend["base_url"] + "/v1/chat/completions"
    headers = {}
    if backend.get("auth_header"):
        k, v = backend["auth_header"](api_key)
        headers[k] = v

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    last_content = ""
    last_error = ""
    for attempt in range(3):
        try:
            body = _http_json(url, payload, headers=headers, timeout=timeout)
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                err_body = err_body.get("error", {}).get("message", str(exc))
            except Exception:
                err_body = str(exc)
            last_error = f"(HTTP {exc.code}) {err_body}"
            if exc.code == 401:
                raise RuntimeError(
                    f"Authentication failed: {err_body}. "
                    f"Check your API key for '{backend['label']}'."
                ) from exc
            if attempt < 2:
                continue
            raise RuntimeError(last_error) from exc
        except urllib.error.URLError as exc:
            last_error = str(exc)
            if attempt < 2:
                continue
            raise RuntimeError(last_error) from exc
        last_content = (
            body.get("choices", [{}])[0].get("message", {}).get("content") or ""
        ).strip()
        if last_content:
            return last_content
    raise RuntimeError(last_error or "The model returned an empty response.")


def chat_with_tools(
    backend_id: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 4096,
    timeout: float = 300.0,
    api_key: str = "",
) -> tuple[str, list]:
    """Send a chat request with tool definitions.

    Returns (content, tool_calls). If the model wants to call tools,
    tool_calls is non-empty and content may be empty.
    """
    bmap = _backends_by_id()
    backend = bmap.get(backend_id)
    if not backend:
        raise RuntimeError(f"Unknown backend: {backend_id}")

    _require_api_key(backend, api_key)

    url = backend["base_url"] + "/v1/chat/completions"
    headers = {}
    if backend.get("auth_header"):
        k, v = backend["auth_header"](api_key)
        headers[k] = v

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    body = _http_json(url, payload, headers=headers, timeout=timeout)
    msg = body.get("choices", [{}])[0].get("message", {})
    content = (msg.get("content") or "").strip()
    tool_calls = msg.get("tool_calls") or []
    return content, tool_calls
