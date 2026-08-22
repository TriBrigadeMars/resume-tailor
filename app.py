"""ResumeTailor — self-hosted AI resume & cover letter generator.

Run:  .venv/Scripts/python app.py
Then open http://localhost:8000 in your browser.
"""

from __future__ import annotations

import io
import os
import re
import sys
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request, send_file, abort

import llm
import docgen
import search
import mcp_integration
import rss

# ---- prompt helpers (moved up for reuse in API key route) ----


def resource_path(rel: str) -> str:
    """Resolve bundled resources when frozen by PyInstaller, or from source."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB uploads

def _resume_system(research_text: str = "") -> str:
    base = (
        "You are an expert resume writer and ATS (Applicant Tracking System) "
        "optimization specialist. You rewrite a candidate's existing resume so it "
        "is tailored to a specific job description. Rules:\n"
        "- Only use facts, roles, and achievements that are present in the "
        "candidate's original resume. Never invent experience, employers, dates, "
        "or credentials.\n"
        "- Reword bullet points to use strong action verbs and naturally weave in "
        "the most relevant keywords from the job description.\n"
        "- Reorder and emphasize the skills and experiences most relevant to the "
        "role; keep it honest and accurate.\n"
        "- Keep the same overall structure (Contact, Summary, Skills, Experience, "
        "Education, Projects) unless the original differs.\n"
        "- Output ONLY the finished resume as clean markdown. Use '## ' for section "
        "headings and '- ' for bullets. Do not add commentary before or after."
    )
    if research_text:
        base += (
            f"\n\nCompany/role research results:\n{research_text}\n\n"
            "Use the research above to better align the resume with the company's "
            "mission, culture, and products. Do not fabricate anything not in the "
            "candidate's actual experience."
        )
    return base


def _cover_system(research_text: str = "") -> str:
    base = (
        "You are an expert cover letter writer. Based on the candidate's resume "
        "and a specific job description, write a professional, concise cover "
        "letter. Rules:\n"
        "- Use only real details from the candidate's resume. Never invent "
        "employers, titles, dates, or accomplishments.\n"
        "- Address the specific role and company, and connect the candidate's "
        "experience to the requirements in the job description.\n"
        "- Keep it to 3-4 short paragraphs, professional and warm in tone.\n"
        "- Output ONLY the letter as plain text with a 'Dear Hiring Manager,' "
        "salutation and 'Sincerely,' signature placeholder. No commentary."
    )
    if research_text:
        base += (
            f"\n\nCompany/role research results:\n{research_text}\n\n"
            "Use the research above to write a more personalized and authentic "
            "cover letter. Reference specific company details (mission, products, "
            "culture) where natural, but only connect to the candidate's real "
            "experience."
        )
    return base


def _build_user_prompt(
    job_description: str, resume_text: str, research_text: str, task: str
) -> str:
    parts = [f"JOB DESCRIPTION:\n{job_description}"]
    if research_text and "failed" not in research_text.lower():
        parts.append(
            f"COMPANY RESEARCH (found via web search):\n{research_text}"
        )
    parts.append(f"MY CURRENT RESUME:\n{resume_text}")
    if task == "resume":
        parts.append("Please rewrite my resume to best match this job.")
    else:
        parts.append("Please write a cover letter for this role.")
    return "\n\n".join(parts)


def _extract_company_role(
    backend: str, model: str, job_description: str, temperature: float,
    api_key: str = "",
) -> tuple[str, str]:
    """Use the LLM to pull company name and role title from a job description."""
    prompt = (
        "Extract the hiring company name and the job role/title from the "
        "job description below. Return ONLY a JSON object like "
        '{"company":"Company Name","role":"Job Title"}. If you cannot '
        "determine either, use an empty string.\n\nJOB DESCRIPTION:\n"
        f"{job_description}"
    )
    raw = llm.chat_completion(
        backend,
        model,
        [
            {"role": "system", "content": "You extract company names and job titles. Reply ONLY with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=200,
        api_key=api_key,
    )
    # Robust JSON extraction from possibly-markdown-wrapped output.
    raw = raw.strip()
    for delim in ("{", "```json", "```"):
        if delim in raw:
            raw = raw[raw.index(delim):].lstrip("`json").strip()
            break
    for delim in ("}", "```"):
        if delim in raw:
            idx = raw.rindex(delim)
            if delim == "}":
                idx += 1
            raw = raw[:idx]
            break
    import json as _json

    try:
        parsed = _json.loads(raw)
        return (
            str(parsed.get("company", "")).strip(),
            str(parsed.get("role", "")).strip(),
        )
    except Exception:
        return "", ""


def extract_resume_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded .docx, .pdf, or .txt file."""
    name = (filename or "").lower()
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs if p.text.strip())
    if name.endswith(".pdf"):
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    # Fallback: try to decode as text
    return data.decode("utf-8", errors="replace")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/backends")
def api_backends():
    local = llm.detect_backends()
    remote = llm.get_remote_backends()
    return jsonify(
        {
            "backends": local + remote,
            "rss_feed_url": os.environ.get("RSS_FEED_URL", ""),
        }
    )


@app.route("/api/models", methods=["POST"])
def api_models():
    """Fetch model list for a remote backend using an API key."""
    payload = request.get_json(silent=True) or {}
    backend_id = payload.get("backend_id") or ""
    api_key = payload.get("api_key") or ""
    if not backend_id:
        return jsonify({"models": [], "error": "No backend_id provided."}), 400
    models = llm.list_models(backend_id, api_key)
    return jsonify({"models": models})


@app.route("/api/rss")
def api_rss():
    """Fetch and parse a job RSS feed."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"jobs": [], "error": "No feed URL provided."}), 400
    try:
        jobs = rss.fetch_feed(url)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"jobs": [], "error": f"Could not load feed: {exc}"}), 400
    return jsonify({"jobs": jobs})


@app.route("/api/mcp/tools", methods=["POST"])
def api_mcp_tools():
    """Connect to MCP servers and list available tools."""
    payload = request.get_json(silent=True) or {}
    servers = payload.get("servers") or mcp_integration.get_servers_from_env()
    if not servers:
        return jsonify({"tools": [], "error": "No MCP servers configured."})
    manager = mcp_integration.MCPManager(servers)
    tools, error = manager.list_tools_sync()
    if error:
        return jsonify({"tools": [], "error": f"MCP error: {error}"}), 500
    return jsonify({"tools": tools})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    payload = request.get_json(silent=True) or {}
    resume_text = (payload.get("resume_text") or "").strip()
    job_description = (payload.get("job_description") or "").strip()
    backend = payload.get("backend") or "ollama"
    model = payload.get("model") or ""
    temperature = float(payload.get("temperature", 0.4))
    api_key = (payload.get("api_key") or "").strip()
    research_mode = (payload.get("research_mode") or "").strip()  # "web" | "llm" | ""
    research_provider = (payload.get("research_provider") or "").strip()
    research_api_key = (payload.get("research_api_key") or "").strip()
    mcp_enabled = bool(payload.get("mcp_enabled"))
    mcp_servers = payload.get("mcp_servers") or []

    if not resume_text or not job_description:
        return jsonify({"error": "Both a resume and a job description are required."}), 400
    if not model:
        return jsonify({"error": "No model selected."}), 400

    # --- Optional: research ---
    research_text = ""
    if research_mode == "web" and research_provider and research_api_key:
        company, role = _extract_company_role(
            backend, model, job_description, temperature, api_key
        )
        if company:
            query = f'"{company}" company culture mission products values'
            if role:
                query += f' {role}'
            try:
                research_text = search.search_web(
                    research_provider, research_api_key, query
                )
            except Exception as exc:
                research_text = f"[Web research failed: {exc}]"
    elif research_mode == "llm":
        company, role = _extract_company_role(
            backend, model, job_description, temperature, api_key
        )
        if company:
            try:
                research_text = llm.chat_completion(
                    backend,
                    model,
                    [
                        {"role": "system", "content": "You are a knowledgeable research assistant. Answer concisely with factual information."},
                        {
                            "role": "user",
                            "content": (
                                f'Tell me everything you know about the company "{company}". '
                                "Cover: what they do, their mission, products/services, "
                                "company culture, recent news, and values. "
                                "Be specific and factual. Keep it to 3-4 paragraphs."
                            ),
                        },
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                    api_key=api_key,
                )
            except Exception as exc:
                research_text = f"[LLM research failed: {exc}]"

    def _generate(task: str) -> str:
        system = _resume_system(research_text) if task == "resume" else _cover_system(research_text)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": _build_user_prompt(
                    job_description, resume_text, research_text, task=task
                ),
            },
        ]
        if mcp_enabled:
            manager = mcp_integration.MCPManager(
                mcp_servers or mcp_integration.get_servers_from_env()
            )
            result = manager.run_tool_loop(
                backend, model, messages,
                api_key=api_key, temperature=temperature,
            )
            if result is not None:
                return result
            # No MCP tools available -> fall back to plain generation.
        return llm.chat_completion(
            backend, model, messages, temperature=temperature, api_key=api_key
        )

    try:
        resume_md = _generate("resume")
        cover_letter = _generate("cover")
    except Exception as exc:  # noqa: BLE001 - surface a friendly error
        return jsonify({"error": f"LLM request failed: {exc}"}), 502

    return jsonify({"resume_md": resume_md, "cover_letter": cover_letter})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """Extract text from an uploaded resume file (docx/pdf/txt)."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        text = extract_resume_text(file.filename, file.read())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Could not read file: {exc}"}), 400
    if not text.strip():
        return jsonify({"error": "No readable text found in the file."}), 400
    return jsonify({"text": text})


@app.route("/download/<doc_type>", methods=["POST"])
def download(doc_type: str):
    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        abort(400)

    if doc_type == "resume":
        base = "tailored_resume"
    elif doc_type == "cover":
        base = "cover_letter"
    else:
        abort(404)

    fmt = payload.get("format", "docx")

    if fmt == "docx":
        document = docgen.markdown_to_docx(content)
        buffer = io.BytesIO()
        document.save(buffer)
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{base}.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    if fmt == "txt":
        # Strip markdown markers for a clean plain-text version.
        clean = re.sub(r"^#{1,6}\s*", "", content, flags=re.MULTILINE)
        clean = re.sub(r"^\s*[-*]\s+", "- ", clean, flags=re.MULTILINE)
        buffer = io.BytesIO(clean.encode("utf-8"))
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{base}.txt",
            mimetype="text/plain",
        )

    abort(400)


def _find_free_port(start: int = 8000, tries: int = 10) -> int:
    import socket

    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range.")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port_env = os.environ.get("PORT", "")

    if port_env:
        # Explicit port (e.g. in Docker) -> bind directly, no auto-find.
        port = int(port_env)
    else:
        try:
            port = _find_free_port()
        except RuntimeError as exc:
            print(exc)
            raise

    url = f"http://localhost:{port}"
    print(f"ResumeTailor running at {url}")

    # Open the browser shortly after the server starts (skip in containers).
    auto_open = os.environ.get("AUTO_OPEN_BROWSER", "1") != "0"
    if auto_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False)
