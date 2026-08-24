# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- Client-supplied MCP server config is disabled by default; only
  `MCP_SERVERS` env config is used unless `ALLOW_CLIENT_MCP_SERVERS=1` is set
  (the trusted local desktop app enables it).
- Docker Compose now publishes the port loopback-only
  (`127.0.0.1:8000:8000`) by default.
- RSS fetching hardened against SSRF: rejects localhost/private/link-local/
  multicast/reserved destinations, validates every redirect, and enforces
  timeout, redirect, and size limits.
- Research/resume/job text are treated as untrusted model context: research is
  removed from the system prompt, appears once in the user prompt, and the
  model is told to ignore instructions inside the input material.
- Generation input is validated: temperature is range-checked (0.0–2.0,
  rejects NaN/inf), and resume/job lengths are capped.
- Remote API keys are no longer persisted to `localStorage`; they now use
  `sessionStorage` and legacy keys are removed on load.

### Security
- Fixed an SSRF in `/api/preview`: job-page previews now use the shared
  SSRF-safe fetch (private/localhost/redirect/size protections), matching RSS.
- Fixed a regex backreference bug in `_html_to_text` so nav/header/footer/
  aside/form blocks are stripped as intended.

### Added
- **Auto-process jobs**: for each job in an RSS or cron feed, fetch the page,
  populate the job description, and auto-run resume/cover-letter generation,
  pausing after each job for review (with Next/Stop controls). Includes a
  "select resume file for all jobs" option.
- New **Job Opportunities** column that displays jobs from the most recent
  Hermes cron job output (JSON feed), with click-to-load into the generator.
- New `GET /api/cron-jobs` endpoint that reads the Hermes cron feed.
- New `JOB_FEED_FILE` environment variable to configure the feed path.
- `job_hunting_feed.py` Hermes cron script that writes an accumulated JSON feed
  of job postings (reuses the consolidated job monitor sources).

## [1.0.0] - 2026-08-22

### Added
- Pure-Python desktop app (`pywebview` + `pystray`) with a native Windows
  window, system tray icon, and minimize-to-tray behavior.
- Native "Save As" dialog for downloading generated `.docx` / `.txt` files in
  the desktop app (reliable in WebView2, where blob-URL downloads don't work).
- Docker image + `docker-compose.yml` with Node.js for `npx`-based stdio MCP
  servers.
- RSS/Atom job feed integration: load jobs in-app and generate a tailored
  resume + cover letter for a selected role.
- MCP server tool integration (HTTP and stdio servers).
- Web research (Tavily / Brave / SerpAPI) and LLM-knowledge research modes.
- Four LLM backends: Ollama, LM Studio / Bionic (local), OpenRouter, and
  LM Studio Bionic (cloud).
- GitHub Actions workflow to build the Windows executables on CI.

### Fixed
- OpenRouter base URL to avoid a double `/v1/v1` path.
- Clear, user-friendly error messages for missing/invalid API keys (401).
- Download buttons in the desktop app now use a native save dialog.

## [0.1.0] - 2026-08-18

### Added
- Initial Flask web app: generate a tailored resume and cover letter from an
  uploaded/pasted resume and a job description.
- `.docx` and `.txt` download endpoints.
- Local LLM backend auto-detection (Ollama, LM Studio).
