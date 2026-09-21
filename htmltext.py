"""Convert raw HTML into readable plain text.

Kept separate from the Flask routes so the heuristics can be tested and
reused without importing the web app.
"""

from __future__ import annotations

import html as _html_mod
import re

MAX_TEXT_LEN = 20000


def html_to_text(html: str, max_len: int = MAX_TEXT_LEN) -> str:
    """Strip scripts/styles/nav and extract readable text from a page."""
    # Drop non-content blocks (scripts, styles, nav, etc.).
    html = re.sub(
        r"<(script|style|nav|header|footer|aside|form)[^>]*>.*?</\1>",
        " ", html, flags=re.IGNORECASE | re.DOTALL,
    )
    # Defensive: remove any remaining style/script blocks.
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    # Turn block tags into newlines.
    html = re.sub(
        r"<(br|/p|/div|/li|/h[1-6]|/tr|/section|/article)[^>]*>", "\n", html,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html_mod.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)

    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        # CSS rules / styled-components noise (e.g. .cls{...} or @media{...}).
        if re.match(r"^[.#][A-Za-z][\w-]*\{", s):
            continue
        if re.match(r"^@media", s):
            continue
        if "/*!sc*/" in s or re.search(r"^[.#][A-Za-z][\w-]*\{.*\}", s):
            continue
        # JavaScript noise.
        if re.search(r"function\s*\(|=>|window\.|document\.|\bvar\s+\w+\s*=", s):
            continue
        # Very long single-line CSS (minified) that still contains braces.
        if "{" in s and "}" in s and ";" in s:
            continue
        lines.append(s)
    return "\n".join(lines)[:max_len]