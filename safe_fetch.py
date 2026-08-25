"""SSRF-safe HTTP fetching shared by RSS loading and job-page previews.

Both RSS feed loading and the job preview endpoint fetch user-supplied URLs
server-side. This module centralizes the protections so the two paths cannot
drift: reject localhost/private/link-local/multicast/reserved destinations,
validate every redirect target, and enforce a timeout, redirect limit, and
response-size limit.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 10.0   # seconds
MAX_REDIRECTS = 5
MAX_BYTES = 2 * 1024 * 1024  # 2 MiB default

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def host_is_private(host: str) -> bool:
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


def validate_url(url: str) -> None:
    """Validate a URL; raise ValueError if it is unsafe or not http(s)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("URL must be http/https.")
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid URL.")
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("URL resolves to a local/private address.")
    if host_is_private(host):
        raise ValueError("URL resolves to a local/private address.")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that validates each redirect target for SSRF safety."""

    # HTTPRedirectHandler defaults to 10. Keep the documented application limit
    # explicit here so MAX_REDIRECTS is not merely informational.
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(
    url: str,
    max_bytes: int = MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Fetch a URL with SSRF protections. Returns the raw response bytes.

    Raises ValueError for unsafe/invalid URLs and RuntimeError on fetch or
    size-limit failures.
    """
    validate_url(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Request failed (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc
    if len(data) > max_bytes:
        raise RuntimeError("Response is too large to download.")
    return data
