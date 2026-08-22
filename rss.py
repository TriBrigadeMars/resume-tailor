"""RSS / Atom feed fetching for job opportunities.

Parses a job RSS feed and returns a normalized list of job entries so they
can be shown in the app and fed into the resume/cover-letter generator.
"""

from __future__ import annotations

import html
import re
import urllib.parse

import feedparser


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)  # strip tags
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_feed(url: str, limit: int = 50) -> list[dict]:
    """Fetch and parse an RSS/Atom feed. Returns a list of job entries.

    Raises RuntimeError on network/parse failure.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("Invalid feed URL (must be http/https).")

    feed = feedparser.parse(url)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(f"Could not parse feed: {feed.bozo_exception}")

    jobs = []
    for entry in feed.entries[:limit]:
        title = _clean(getattr(entry, "title", ""))
        summary = _clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        link = getattr(entry, "link", "") or ""
        published = getattr(entry, "published", "") or getattr(entry, "updated", "")
        # Try to infer a company name from the entry/feed if available.
        source = getattr(entry, "source", None)
        company = _clean(
            getattr(entry, "author", "") or (source.get("title", "") if source else "")
        )
        if not title and not summary:
            continue
        jobs.append(
            {
                "title": title,
                "company": company,
                "link": link,
                "description": summary,
                "published": published,
            }
        )
    return jobs
