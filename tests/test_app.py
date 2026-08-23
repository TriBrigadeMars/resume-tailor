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
