# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
