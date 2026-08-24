# ResumeTailor — Self-Hosted AI Resume & Cover Letter Generator

A small, private web app that runs entirely on your own machine (or in a
container). It takes your existing resume and a job description, then uses a
local or remote LLM (**Ollama**, **LM Studio / Bionic**, or **OpenRouter**) to
produce a **tailored resume** and a **cover letter** you can download as
`.docx` or `.txt`.

Optional add-ons: **web research** (search APIs or LLM knowledge), **MCP server
tools** the LLM can call while generating, and **RSS job feeds** to load
opportunities in-app.

> **Privacy note:** your API keys (OpenRouter, LM Studio, search providers) are
> kept only in the browser's `localStorage` and sent to the app's local server
> at request time. They are **never written to disk** and never leave your
> machine unless you use a remote LLM backend.

---

## ✨ Features

- **Four LLM backends** — Ollama, LM Studio / Bionic (local), OpenRouter, and
  LM Studio Bionic (cloud).
- **Tailored resume + cover letter** generated from your resume + a job
  description, then downloaded as `.docx` or `.txt`.
- **Web research** (opt-in) — live search via **Tavily**, **Brave**, or
  **SerpAPI**, or LLM-knowledge research with no extra key.
- **MCP server tools** (opt-in) — the LLM can call external tools (HTTP or
  stdio servers) while generating.
- **RSS job feed** — paste a job RSS/Atom feed URL, load the opportunities
  in-app, and generate a tailored resume + cover letter for a selected role.
- **Cron job feed** — a dedicated column displays job opportunities from the
  most recent Hermes cron job output (JSON feed); click a job to load it and
  generate a tailored resume + cover letter.
- **Auto-process jobs** — for each job in an RSS or cron feed, fetch the page,
  populate the job description, and auto-run resume/cover-letter generation,
  pausing after each job for review. Optionally select a resume file to use for
  all jobs in the batch.
- **Desktop app** (Windows) — native window + system tray, no browser needed.

---

## 📦 Requirements

- Python 3.10+ (to run from source) **or** Docker (to run in a container)
- A running LLM backend, **one of**:
  - **Ollama** at `http://localhost:11434`
  - **LM Studio / Bionic** (local server) at `http://localhost:1234`
  - **OpenRouter** or **LM Studio Bionic (cloud)** — paste an API key in the UI

---

## 🚀 Run from source

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

### Web app (browser)

```bash
python app.py
```

Then open <http://localhost:8000>.

### Desktop GUI (native window + system tray)

```bash
python desktop.py
```

On Windows you can also double-click **`launch_desktop.bat`** to start the
desktop GUI without opening a terminal.

## 🐨 Run with Docker

```bash
docker compose up --build
# open http://localhost:8000
```

The container reaches the host's Ollama / LM Studio through
`host.docker.internal` (see `docker-compose.yml`). Build just the image with
`docker build -t resume-tailor:latest .`.

By default the container's port is published **loopback-only**
(`127.0.0.1:8000:8000`), so it is reachable only from this machine. To allow
LAN access, change the port binding to `8000:8000` in `docker-compose.yml` and
be aware the app will be exposed on your network without authentication.

## 🖥️ Run the Windows executables

Two pre-built executables are available (see **Releases** or build from source):

| Executable | Description |
|------------|-------------|
| `ResumeTailor.exe` | Web app — opens in your browser |
| `ResumeTailor-Desktop.exe` | Native window + system tray (no browser) |

Rebuild after code changes:

```bash
# Web app
.venv\Scripts\pyinstaller --clean --noconfirm ResumeTailor.spec

# Desktop app
.venv\Scripts\pyinstaller --clean --noconfirm --distpath dist-desktop Desktop.spec
```

---

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

---

## 📁 Project structure

```
resume-tailor/
├── app.py                 # Flask backend (API + routes)
├── desktop.py             # Desktop launcher (pywebview + pystray)
├── launch_desktop.bat     # Windows launcher for the desktop GUI
├── llm.py                 # LLM client (Ollama / LM Studio / OpenRouter)
├── docgen.py              # Markdown → .docx conversion
├── search.py              # Web search clients (Tavily / Brave / SerpAPI)
├── mcp_integration.py     # MCP server client + tool-calling loop
├── rss.py                 # RSS/Atom feed parser
├── static/                # Frontend (app.js, style.css)
├── templates/             # index.html
├── tests/                 # Smoke tests
├── Dockerfile             # Container image (Python + Node.js)
├── docker-compose.yml     # Compose config
├── ResumeTailor.spec      # PyInstaller spec (web app)
├── Desktop.spec           # PyInstaller spec (desktop app)
└── requirements.txt
```

---

## 🔌 API endpoints

| Method | Path              | Description                                   |
|--------|-------------------|-----------------------------------------------|
| GET    | `/`               | Web UI                                        |
| GET    | `/api/backends`   | List backends + models (local auto-detected)  |
| POST   | `/api/models`     | Fetch remote backend models with an API key   |
| POST   | `/api/generate`   | Generate tailored resume + cover letter       |
| POST   | `/api/extract`    | Extract text from an uploaded resume file     |
| POST   | `/api/mcp/tools`  | List tools from configured MCP servers        |
| GET    | `/api/rss`        | Fetch + parse a job RSS feed (`?url=`)        |
| GET    | `/api/cron-jobs`  | Read the latest Hermes cron job feed (JSON)   |
| POST   | `/download/<type>`| Download output as `.docx` or `.txt`          |

---

## ⚙️ Environment variables

| Variable             | Default               | Purpose                                   |
|----------------------|-----------------------|-------------------------------------------|
| `HOST`               | `127.0.0.1`           | Bind address (`0.0.0.0` in Docker)        |
| `PORT`               | auto-find             | Port to listen on (`8000` in Docker)      |
| `AUTO_OPEN_BROWSER`  | `1`                   | Set `0` in containers                     |
| `OLLAMA_BASE_URL`    | `http://localhost:11434` | Ollama endpoint                        |
| `LMSTUDIO_BASE_URL`  | `http://localhost:1234`  | LM Studio / Bionic endpoint            |
| `MCP_SERVERS`        | `[]`                  | JSON list of MCP servers                  |
| `RSS_FEED_URL`       | *(none)*              | Optional default RSS feed URL (prefilled in UI) |
| `JOB_FEED_FILE`      | `…/hermes/cron/output/job_hunting/latest.json` | Path to the Hermes cron job JSON feed |
| `ALLOW_CLIENT_MCP_SERVERS` | `0` | Set `1` to allow the browser to configure MCP servers (desktop app sets this automatically) |

See [`.env.example`](.env.example) for a template.

---

## 🐙 MCP server tools

The LLM can call external tools while generating. Configure MCP servers in the
UI (stdio command or HTTP URL), or via the `MCP_SERVERS` env var for Docker:

```json
[{"name":"web","type":"http","url":"http://host:port/mcp"},
 {"name":"fs","type":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}]
```

Example: connect a filesystem or web-search MCP server, enable "Use MCP server
tools", and the model can read files / search while writing your resume.

---

## 🤖 Hermes AI (Nous Research)

The app works with any Hermes model out of the box:

- **Local**: `ollama pull hermes3:8b` (or load a Hermes GGUF in LM Studio) — it
  appears in the backend dropdown automatically.
- **Cloud**: Hermes models are available on **OpenRouter** — pick OpenRouter,
  paste your key, and select a Hermes model.
- **Hermes Agent** (the autonomous agent) can be connected to this app as an
  MCP server or used as the LLM backend.

---

## 📝 Notes & tips

- The AI is instructed to **only use facts from your original resume** — it
  should never invent employers, dates, or credentials. Always review output.
- Local generation can take a minute or two per run.
- If both Ollama and LM Studio are running, use the **Backend** dropdown.
- In Docker, `stdio` MCP servers need their runtime installed in the image
  (e.g. add Node for `npx` servers). HTTP MCP servers work without extra setup.

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
testing, and build instructions. Security issues should be reported privately
per [SECURITY.md](SECURITY.md).

## 📄 License

[MIT](LICENSE)
