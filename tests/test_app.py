"""Smoke tests for ResumeTailor.

Run with:
    python -m pytest tests/ -v
"""

import io
import json

import pytest


# ---------------------------------------------------------------------------
# docgen
# ---------------------------------------------------------------------------

def test_markdown_to_docx_creates_valid_document():
    import docgen

    md = (
        "## John Doe\n"
        "- Python developer\n"
        "- 5 years experience\n"
        "## Skills\n"
        "- Flask\n"
        "- AWS\n"
    )
    doc = docgen.markdown_to_docx(md)
    buffer = io.BytesIO()
    doc.save(buffer)
    data = buffer.getvalue()
    # A .docx file is a zip archive (starts with "PK").
    assert data[:2] == b"PK"
    assert len(data) > 1000


# ---------------------------------------------------------------------------
# llm backend configuration
# ---------------------------------------------------------------------------

def test_backend_definitions():
    import llm

    ids = [b["id"] for b in llm.LOCAL_BACKENDS + llm.REMOTE_BACKENDS]
    assert "ollama" in ids
    assert "lmstudio" in ids
    assert "openrouter" in ids
    assert "lmstudiobionic" in ids


def test_remote_backends_need_api_key():
    import llm

    remote = llm.get_remote_backends()
    assert remote, "expected remote backends"
    for b in remote:
        assert b["needs_api_key"] is True


def test_chat_completion_rejects_missing_key():
    import llm

    with pytest.raises(RuntimeError) as exc:
        llm.chat_completion("openrouter", "some-model", [{"role": "user", "content": "hi"}])
    assert "API key" in str(exc.value)


# ---------------------------------------------------------------------------
# Flask app routes
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_index_serves_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"ResumeTailor" in resp.data


def test_index_exposes_rss_loader(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b'id="rss-url"' in resp.data
    assert b'id="rss-load-btn"' in resp.data


def test_security_headers_are_present(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"


def test_safe_fetch_redirect_limit_matches_documented_limit():
    import safe_fetch

    assert safe_fetch._SafeRedirectHandler.max_redirections == safe_fetch.MAX_REDIRECTS


def test_backends_endpoint(client):
    resp = client.get("/api/backends")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "backends" in data
    assert "rss_feed_url" in data


def test_download_docx(client):
    resp = client.post(
        "/download/resume",
        json={"content": "## Test\n- bullet", "format": "docx"},
    )
    assert resp.status_code == 200
    assert resp.data[:2] == b"PK"
    assert "application/vnd.openxmlformats" in resp.mimetype


def test_download_txt(client):
    resp = client.post(
        "/download/cover",
        json={"content": "Dear Hiring Manager,\nSincerely", "format": "txt"},
    )
    assert resp.status_code == 200
    assert resp.data.decode("utf-8").startswith("Dear Hiring Manager")


def test_download_requires_content(client):
    resp = client.post("/download/resume", json={"content": "", "format": "docx"})
    assert resp.status_code == 400


def test_generate_requires_fields(client):
    resp = client.post("/api/generate", json={"resume_text": "", "job_description": ""})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_cron_jobs_endpoint(client):
    """The cron-jobs endpoint returns a jobs array (empty if no feed yet)."""
    resp = client.get("/api/cron-jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)
    assert "feed_file" in data


def test_preview_rejects_invalid_url(client):
    """The preview endpoint rejects non-http(s) URLs."""
    resp = client.get("/api/preview", query_string={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


def test_preview_rejects_missing_url(client):
    resp = client.get("/api/preview")
    assert resp.status_code == 400


def test_preview_rejects_localhost(client):
    resp = client.get("/api/preview", query_string={"url": "http://localhost:8000/feed"})
    assert resp.status_code == 400


def test_preview_rejects_private_ip(client):
    resp = client.get("/api/preview", query_string={"url": "http://192.168.1.1/"})
    assert resp.status_code == 400


def test_safe_fetch_rejects_private():
    import safe_fetch

    with pytest.raises(ValueError):
        safe_fetch.fetch_bytes("http://127.0.0.1:11434/")


# ---------------------------------------------------------------------------
# Phase 1 hardening regression tests
# ---------------------------------------------------------------------------


def _generate_payload(**overrides):
    payload = {
        "resume_text": "John Doe\nSoftware Engineer",
        "job_description": "Python Developer",
        "backend": "ollama",
        "model": "some-model",
        "temperature": 0.4,
    }
    payload.update(overrides)
    return payload


def test_invalid_temperature_returns_400(client):
    resp = client.post("/api/generate", json=_generate_payload(temperature="abc"))
    assert resp.status_code == 400
    assert "temperature" in resp.get_json()["error"]


def test_out_of_range_temperature_returns_400(client):
    resp = client.post("/api/generate", json=_generate_payload(temperature=3.0))
    assert resp.status_code == 400
    assert "temperature" in resp.get_json()["error"]


def test_nonfinite_temperature_returns_400(client):
    resp = client.post("/api/generate", json=_generate_payload(temperature="nan"))
    assert resp.status_code == 400


def test_rss_rejects_localhost():
    import rss

    with pytest.raises(RuntimeError):
        rss.fetch_feed("http://localhost:8000/feed")


def test_rss_rejects_private_ip():
    import rss

    with pytest.raises(RuntimeError):
        rss.fetch_feed("http://192.168.1.1/feed")


def test_client_mcp_servers_ignored_when_disabled(monkeypatch):
    import app as app_module

    monkeypatch.setenv("ALLOW_CLIENT_MCP_SERVERS", "0")
    monkeypatch.setattr(
        app_module.mcp_integration, "get_servers_from_env", lambda: []
    )
    client_sent = [{"name": "evil", "type": "stdio", "command": "rm", "args": ["-rf", "/"]}]
    resolved = app_module._resolve_mcp_servers(client_sent)
    assert resolved == []  # client servers ignored


def test_client_mcp_servers_allowed_when_enabled(monkeypatch):
    import app as app_module

    monkeypatch.setenv("ALLOW_CLIENT_MCP_SERVERS", "1")
    monkeypatch.setattr(
        app_module.mcp_integration, "get_servers_from_env", lambda: []
    )
    client_sent = [{"name": "web", "type": "http", "url": "http://x/mcp"}]
    resolved = app_module._resolve_mcp_servers(client_sent)
    assert resolved == client_sent


def test_server_mcp_config_used_when_client_disabled(monkeypatch):
    import app as app_module

    monkeypatch.setenv("ALLOW_CLIENT_MCP_SERVERS", "0")
    env_servers = [{"name": "env", "type": "http", "url": "http://env/mcp"}]
    monkeypatch.setattr(
        app_module.mcp_integration, "get_servers_from_env", lambda: env_servers
    )
    resolved = app_module._resolve_mcp_servers([])
    assert resolved == env_servers


def test_chat_with_tools_requires_api_key():
    import llm

    with pytest.raises(RuntimeError) as exc:
        llm.chat_with_tools(
            "openrouter", "some-model",
            [{"role": "user", "content": "hi"}],
            [{"type": "function", "function": {"name": "f", "parameters": {}}}],
        )
    assert "API key" in str(exc.value)


def test_numbered_list_docx_conversion():
    import docgen

    doc = docgen.markdown_to_docx("1. First item\n2) Second item\n10. Third item")
    styles = [p.style.name for p in doc.paragraphs]
    assert all(s == "List Number" for s in styles)


def test_markdown_to_text_strips_markers():
    import docgen

    text = docgen.markdown_to_text("## Heading\n- bullet\n1. item\nplain")
    assert "##" not in text
    assert "- bullet" not in text
    assert "1. item" in text
    assert "plain" in text


def test_txt_download_uses_shared_helper(client):
    import docgen

    resp = client.post(
        "/download/resume",
        json={"content": "## Title\n- bullet\n1. item", "format": "txt"},
    )
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert body == docgen.markdown_to_text("## Title\n- bullet\n1. item")


def test_research_not_in_system_prompt():
    import app as app_module

    sys_resume = app_module._resume_system()
    sys_cover = app_module._cover_system()
    # Research content is never embedded in the system prompt (only reference
    # material is placed in the user prompt).
    assert "COMPANY RESEARCH" not in sys_resume
    assert "COMPANY RESEARCH" not in sys_cover
    assert "</COMPANY RESEARCH>" not in sys_resume


def test_research_appears_once_in_user_prompt():
    import app as app_module

    prompt = app_module._build_user_prompt(
        "job", "resume", "RESEARCH_TEXT", task="resume"
    )
    assert prompt.count("RESEARCH_TEXT") == 1
    assert "<COMPANY RESEARCH>" in prompt
    assert "<JOB DESCRIPTION>" in prompt
    assert "<CANDIDATE RESUME>" in prompt


# ---------------------------------------------------------------------------
# Auth headers (regression: these must carry the real bearer token)
# ---------------------------------------------------------------------------

B_EARER = "B" + "earer"  # avoid credential-shaped literals in this source file


def test_remote_backend_auth_header_value():
    import llm

    for backend in llm.REMOTE_BACKENDS:
        name, value = backend["auth_header"]("TESTKEY")
        assert name == "Authorization"
        assert value.split(" ", 1)[0] == B_EARER
        assert value.split(" ", 1)[1] == "TESTKEY"


def test_auth_headers_helper_returns_dict():
    import llm

    backend = llm.REMOTE_BACKENDS[0]
    assert llm._auth_headers(backend, "TESTKEY") == {
        "Authorization": f"{B_EARER} TESTKEY"
    }
    # Local backends carry no auth header.
    assert llm._auth_headers(llm.LOCAL_BACKENDS[0], "TESTKEY") == {}


def test_search_provider_auth_headers(monkeypatch):
    import search

    req, _extract = search.SEARCH_PROVIDERS["tavily"]["build"]("TESTKEY", "q")
    assert req.get_header("Authorization") == f"{B_EARER} TESTKEY"

    req, _extract = search.SEARCH_PROVIDERS["brave"]["build"]("TESTKEY", "q")
    assert req.get_header("X-subscription-token") == "TESTKEY"

    req, _extract = search.SEARCH_PROVIDERS["serpapi"]["build"]("TESTKEY", "q")
    assert "api_key=TESTKEY" in req.full_url


def test_search_provider_extractors():
    import search

    _req, extract = search.SEARCH_PROVIDERS["tavily"]["build"]("k", "q")
    assert extract({"results": [{"content": "one"}, {"content": "two"}]}) == "one\n\ntwo"

    _req, extract = search.SEARCH_PROVIDERS["brave"]["build"]("k", "q")
    assert extract({"web": {"results": [{"description": "d1"}]}}) == "d1"

    _req, extract = search.SEARCH_PROVIDERS["serpapi"]["build"]("k", "q")
    assert extract({"organic_results": [{"snippet": "s1"}]}) == "s1"


def test_search_web_rejects_unknown_provider():
    import search

    with pytest.raises(RuntimeError, match="Unknown search provider"):
        search.search_web("nope", "k", "q")


# ---------------------------------------------------------------------------
# Shared helpers extracted during the quality review
# ---------------------------------------------------------------------------

def test_find_free_port_is_shared():
    import app as app_module
    import portutils

    assert app_module.find_free_port is portutils.find_free_port
    port = portutils.find_free_port()
    assert isinstance(port, int) and 8000 <= port < 8100


def test_htmltext_module_extracts_text():
    import htmltext

    html = (
        "<html><head><title>t</title><style>.a{color:red}</style>"
        "<script>var x = 1;</script></head>"
        "<body><h1>Title</h1><p>Body text</p></body></html>"
    )
    text = htmltext.html_to_text(html)
    assert "Title" in text
    assert "Body text" in text
    assert "color:red" not in text
    assert "var x" not in text
    assert len(text) <= htmltext.MAX_TEXT_LEN


def test_preview_uses_shared_text_helper(client, monkeypatch):
    import app as app_module
    import htmltext

    monkeypatch.setattr(
        app_module.safe_fetch,
        "fetch_bytes",
        lambda url, **kw: b"<html><body><h1>Hello</h1></body></html>",
    )
    resp = client.get("/api/preview?url=https://example.com/job")
    assert resp.status_code == 200
    assert resp.get_json()["text"] == htmltext.html_to_text(
        "<html><body><h1>Hello</h1></body></html>"
    )


def test_markdown_hash_without_space_is_not_a_heading():
    import docgen

    assert docgen.markdown_to_text("#notaheading") == "#notaheading"
    doc = docgen.markdown_to_docx("#notaheading")
    assert doc.paragraphs[0].style.name != "Heading 1"

    doc = docgen.markdown_to_docx("# Real Heading")
    assert doc.paragraphs[0].style.name == "Heading 1"


def test_run_tool_loop_raises_instead_of_returning_none(monkeypatch):
    """A broken MCP session must raise, not masquerade as 'no tools'."""
    import mcp_integration

    mgr = mcp_integration.MCPManager([{"name": "x", "type": "http", "url": "http://x"}])

    async def boom():
        raise OSError("connection refused")

    monkeypatch.setattr(mgr, "connect_all", boom)
    with pytest.raises(RuntimeError, match="MCP tool loop failed"):
        mgr.run_tool_loop("ollama", "m", [{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# W1: Node.js detection & graceful MCP degradation
# ---------------------------------------------------------------------------


def test_npx_available_short_circuits(monkeypatch):
    import nodecheck

    monkeypatch.setattr(nodecheck.shutil, "which", lambda name: None)
    assert nodecheck.npx_available() is False


def test_npx_available_detects_npx(monkeypatch):
    import nodecheck

    monkeypatch.setattr(nodecheck.shutil, "which", lambda name: "/usr/bin/npx")
    monkeypatch.setattr(
        nodecheck.subprocess,
        "run",
        lambda *a, **kw: type("R", (), {"stdout": b"10.0.0", "stderr": b"", "returncode": 0})(),
    )
    assert nodecheck.npx_available() is True


def test_npx_available_false_on_subprocess_failure(monkeypatch):
    import nodecheck

    monkeypatch.setattr(nodecheck.shutil, "which", lambda name: "/usr/bin/npx")

    def boom(*a, **kw):
        raise OSError("no npx")

    monkeypatch.setattr(nodecheck.subprocess, "run", boom)
    assert nodecheck.npx_available() is False


def test_stdio_mcp_filtered_without_npx(monkeypatch):
    import nodecheck

    monkeypatch.setattr(nodecheck, "npx_available", lambda: False)
    servers = [
        {"name": "fs", "type": "stdio", "command": "npx", "args": ["-y", "fs"]},
        {"name": "web", "type": "http", "url": "http://example.com/mcp"},
    ]
    ok, skipped = nodecheck.stdio_mcp_supported(servers)
    assert [s["name"] for s in ok] == ["web"]
    assert [s["name"] for s in skipped] == ["fs"]


def test_stdio_mcp_supported_with_npx(monkeypatch):
    import nodecheck

    monkeypatch.setattr(nodecheck, "npx_available", lambda: True)
    servers = [
        {"name": "fs", "type": "stdio", "command": "npx"},
        {"name": "web", "type": "http", "url": "http://x"},
    ]
    ok, skipped = nodecheck.stdio_mcp_supported(servers)
    assert len(ok) == 2
    assert skipped == []


def test_mcp_manager_filters_stdio_without_npx(monkeypatch):
    import mcp_integration

    monkeypatch.setattr("nodecheck.npx_available", lambda: False)
    mgr = mcp_integration.MCPManager(
        [
            {"name": "fs", "type": "stdio", "command": "npx"},
            {"name": "web", "type": "http", "url": "http://x"},
        ]
    )
    assert [s["name"] for s in mgr.servers] == ["web"]
    assert [s["name"] for s in mgr.skipped_servers] == ["fs"]


def test_list_tools_sync_returns_skipped_list(monkeypatch):
    import mcp_integration

    monkeypatch.setattr("nodecheck.npx_available", lambda: False)
    mgr = mcp_integration.MCPManager(
        [{"name": "fs", "type": "stdio", "command": "npx"}]
    )
    tools, err, skipped = mgr.list_tools_sync()
    assert err == ""
    assert tools == []
    assert [s["name"] for s in skipped] == ["fs"]


def test_backends_reports_stdio_capability(client, monkeypatch):
    monkeypatch.setattr("nodecheck.npx_available", lambda: False)
    resp = client.get("/api/backends")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "stdio_mcp_available" in data
    assert data["stdio_mcp_available"] is False


def test_backends_reports_stdio_capability_true(client, monkeypatch):
    monkeypatch.setattr("nodecheck.npx_available", lambda: True)
    resp = client.get("/api/backends")
    assert resp.status_code == 200
    assert resp.get_json()["stdio_mcp_available"] is True


def test_api_mcp_tools_surfaces_skipped(client, monkeypatch):
    """When a stdio server is filtered, the response includes its name."""
    import mcp_integration

    monkeypatch.setattr("nodecheck.npx_available", lambda: False)
    monkeypatch.setenv("ALLOW_CLIENT_MCP_SERVERS", "1")
    monkeypatch.setattr("mcp_integration.get_servers_from_env", lambda: [])

    def fake_list_tools_sync(self):
        return [], "", list(self.skipped_servers)

    monkeypatch.setattr(mcp_integration.MCPManager, "list_tools_sync", fake_list_tools_sync)
    resp = client.post(
        "/api/mcp/tools",
        json={"servers": [{"name": "fs", "type": "stdio", "command": "npx"}]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tools"] == []
    assert [s["name"] for s in data["skipped"]] == ["fs"]


# ---------------------------------------------------------------------------
# W3: version reporting & opt-in update check
# ---------------------------------------------------------------------------


def test_version_constant_is_semver():
    import version

    parts = version.__version__.split(".")
    assert len(parts) >= 2
    for p in parts:
        assert p.isdigit()


def test_is_newer_compares_numerically():
    import updater

    # "1.10.0" is greater than "1.2.0" — string comparison would get this wrong.
    assert updater._is_newer("1.10.0", "1.2.0") is True
    assert updater._is_newer("1.2.0", "1.10.0") is False
    assert updater._is_newer("2.0.0", "1.99.99") is True
    assert updater._is_newer("1.0.0", "1.0.0") is False
    # Garbage gracefully degrades to False rather than crashing.
    assert updater._is_newer("not-a-version", "1.0.0") is False


def test_update_check_parses_response(monkeypatch):
    import updater
    import version

    canned = {
        "tag_name": "v9.9.9",
        "html_url": "https://github.com/foo/bar/releases/tag/v9.9.9",
    }

    class FakeResp:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda req, timeout=None: FakeResp(json.dumps(canned))
    )
    result = updater.check_for_update()
    assert result["latest"] == "9.9.9"
    assert result["current"] == version.__version__
    assert result["url"] == canned["html_url"]
    # Whether "available" is true depends on the running version; just assert
    # the boolean type so this test is stable as the version bumps.
    assert isinstance(result["update_available"], bool)


def test_update_check_returns_error_on_failure(monkeypatch):
    import updater

    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    result = updater.check_for_update()
    assert result["update_available"] is False
    assert "error" in result
    assert "network down" in result["error"]


def test_version_endpoint(client):
    import version

    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": version.__version__}


def test_backends_includes_version(client):
    import version

    resp = client.get("/api/backends")
    assert resp.status_code == 200
    assert resp.get_json()["version"] == version.__version__


def test_check_update_endpoint(client, monkeypatch):
    """The endpoint exposes the same payload the module returns."""
    import updater

    monkeypatch.setattr(updater, "check_for_update", lambda: {
        "current": "1.2.0",
        "latest": "1.3.0",
        "update_available": True,
        "url": "https://example/release",
    })
    resp = client.get("/api/check-update")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["update_available"] is True
    assert data["url"] == "https://example/release"


# ---------------------------------------------------------------------------
# W4 desktop keyring + model-list caching
# ---------------------------------------------------------------------------


class _FakeKeyring:
    """In-memory replacement for the ``keyring`` module used in tests."""

    def __init__(self):
        self.store = {}
        self.fail_next = False

    def set_password(self, service, key, value):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("backend locked")
        self.store[(service, key)] = value

    def get_password(self, service, key):
        return self.store.get((service, key))


def test_desktop_api_has_keyring_helper():
    import desktop

    api = desktop.Api()
    # ``has_keyring`` returns a bool; either True (keyring installed) or False
    # (not installed) is acceptable — we just want to exercise the branch.
    assert isinstance(api.has_keyring(), bool)


def test_desktop_api_store_and_load_key(monkeypatch):
    import desktop

    fake = _FakeKeyring()

    class _KR:
        set_password = fake.set_password
        get_password = fake.get_password

    monkeypatch.setitem(__import__("sys").modules, "keyring", _KR())

    api = desktop.Api()
    assert api.store_key("RT_remote_api_key", "sk-test-123") == {
        "ok": True,
        "error": None,
    }
    loaded = api.load_key("RT_remote_api_key")
    assert loaded == {"ok": True, "value": "sk-test-123", "error": None}


def test_desktop_api_store_key_rejects_empty():
    import desktop

    api = desktop.Api()
    result = api.store_key("RT_remote_api_key", "")
    assert result["ok"] is False
    assert "Empty" in result["error"]


def test_desktop_api_store_key_handles_backend_failure(monkeypatch):
    import desktop

    fake = _FakeKeyring()
    fake.fail_next = True

    class _KR:
        set_password = fake.set_password
        get_password = fake.get_password

    monkeypatch.setitem(__import__("sys").modules, "keyring", _KR())

    api = desktop.Api()
    result = api.store_key("RT_remote_api_key", "sk-fail")
    assert result["ok"] is False
    assert "locked" in result["error"]


def test_desktop_api_load_key_missing_returns_empty(monkeypatch):
    import desktop

    fake = _FakeKeyring()

    class _KR:
        set_password = fake.set_password
        get_password = fake.get_password

    monkeypatch.setitem(__import__("sys").modules, "keyring", _KR())

    api = desktop.Api()
    loaded = api.load_key("RT_does_not_exist")
    assert loaded == {"ok": True, "value": "", "error": None}


def test_keyring_service_constant_is_namespaced():
    """Multiple installs on the same machine must not collide."""
    import desktop

    assert desktop.Api.KEYRING_SERVICE == "ResumeTailor"
