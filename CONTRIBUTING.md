# Contributing

Thanks for your interest in ResumeTailor! Contributions are welcome.

## Getting started

1. Fork the repository and clone it locally.
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # macOS / Linux
   pip install -r requirements.txt
   ```

3. Run the app from source:

   ```bash
   python app.py
   # open http://localhost:8000
   ```

## Making changes

- Keep changes focused. Open an issue first for large features so we can
  discuss the approach.
- Follow the existing code style (PEP 8, `from __future__ import annotations`,
  type hints on function signatures).
- Add or update tests in `tests/` for any behavior you change.
- Update the README and CHANGELOG if the change affects usage or the public
  API.

## Running tests

```bash
python -m pytest tests/
```

## Building the executables

Backend-only web app:

```bash
.venv\Scripts\pyinstaller --clean --noconfirm ResumeTailor.spec
```

Desktop app (native window + tray):

```bash
.venv\Scripts\pyinstaller --clean --noconfirm --distpath dist-desktop Desktop.spec
```

## Commit conventions

- Write clear, imperative commit messages ("Add X", "Fix Y", "Refactor Z").
- Keep each commit self-contained.

## Security

- Never commit API keys, tokens, or secrets. Keys are stored only in the
  browser's `localStorage` and never written to disk by the app.
- If you find a security issue, do **not** open a public issue. See
  `SECURITY.md` for how to report it privately.
