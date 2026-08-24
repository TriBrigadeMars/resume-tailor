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
