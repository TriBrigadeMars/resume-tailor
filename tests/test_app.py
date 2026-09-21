"""Smoke tests for ResumeTailor.

Run with:
    python -m pytest tests/ -v
"""

import io

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
