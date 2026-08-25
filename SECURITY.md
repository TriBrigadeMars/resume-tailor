# Security Policy

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security vulnerabilities.
Instead, report them privately so they can be addressed before disclosure.

You can report a vulnerability by opening a **private security advisory** on
GitHub:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Provide a clear description of the issue, the affected version(s), and any
   reproduction steps.

We aim to acknowledge reports within 5 business days and will keep you updated
as the issue is triaged and fixed.

## Scope

The following are in scope:

- Remote code execution, injection, or data-exfiltration via the app.
- Authentication / authorization issues with the LLM or search backends.
- Exposure of API keys or other secrets.

## What this project does about secrets

- **API keys are never stored on disk.** OpenRouter, LM Studio, and search
  provider keys are kept only in the browser's `sessionStorage` and sent to the
  app's local server at request time. The server forwards a key only to the
  remote provider for the feature the user explicitly selected.
- The app binds to `127.0.0.1` by default. When exposing it beyond localhost
  (e.g. in Docker), put it behind a reverse proxy with authentication and TLS.

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 1.x     | ✅                 |
| < 1.0   | ❌ (development)   |
