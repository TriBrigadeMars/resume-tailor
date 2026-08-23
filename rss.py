"""RSS / Atom feed fetching for job opportunities.

Parses a job RSS feed and returns a normalized list of job entries so they
can be shown in the app and fed into the resume/cover-letter generator.

Security: feed URLs are user-supplied, so fetching is hardened against SSRF.
We reject localhost/private/link-local/multicast/reserved destinations,
validate every redirect target, and enforce a timeout, redirect limit, and
response-size limit. The fetched bytes are parsed with feedparser directly
(rather than letting feedparser fetch an arbitrary URL).
"""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

import feedparser

# Limits
FETCH_TIMEOUT = 10.0          # seconds
MAX_REDIRECTS = 5
MAX_FEED_BYTES = 2 * 1024 * 1024  # 2 MiB

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)  # strip tags
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _host_is_private(host: str) -> bool:
    """Return True if the host resolves to a private/loopback/etc. address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Cannot resolve -> treat as unsafe.
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_unspecified or ip.is_reserved
        ):
            return True
    return False


def _validate_url(url: str) -> None:
    """Validate a feed URL; raise RuntimeError if it is unsafe."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("Invalid feed URL (must be http/https).")
    host = parsed.hostname
    if not host:
        raise RuntimeError("Invalid feed URL.")
    # Obvious local hostnames.
    if host == "localhost" or host.endswith(".local"):
        raise RuntimeError("Feed URL resolves to a local/private address.")
    if _host_is_private(host):
        raise RuntimeError("Feed URL resolves to a local/private address.")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that validates each redirect target for SSRF safety."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_feed_bytes(url: str) -> bytes:
    """Fetch a feed with SSRF protections. Returns the raw bytes."""
    _validate_url(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read(MAX_FEED_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Feed request failed (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Feed request failed: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"Feed request failed: {exc}") from exc
    if len(data) > MAX_FEED_BYTES:
        raise RuntimeError("Feed is too large to download.")
    return data


def fetch_feed(url: str, limit: int = 50) -> list[dict]:
    """Fetch and parse an RSS/Atom feed. Returns a list of job entries.

    Raises RuntimeError on network/parse/validation failure.
    """
    data = _fetch_feed_bytes(url)
    feed = feedparser.parse(data)
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
