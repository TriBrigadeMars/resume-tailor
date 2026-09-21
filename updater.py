"""Check GitHub Releases for a newer ResumeTailor version.

This module never downloads or replaces binaries automatically. It only asks
GitHub's public ``/releases/latest`` endpoint for the current tag, compares
it with the running version, and returns the URL the user can use to install
the update themselves. In-place Windows exe replacement is fragile and is a
security surface we deliberately avoid in v1.

The endpoint is read-only and unauthenticated. We set a short timeout and a
descriptive ``User-Agent`` (GitHub rejects unidentified clients) so failures
degrade gracefully into a no-update response.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

from version import __version__

RELEASES_API = "https://api.github.com/repos/TriBrigadeMars/resume-tailor/releases/latest"
USER_AGENT = "ResumeTailor"


def _is_newer(latest: str, current: str) -> bool:
    """Compare two dotted-numeric version strings (e.g. ``1.2.0`` vs ``1.10.0``).

    Anything non-numeric (a pre-release tag suffix like ``1.2.0-rc1``) is
    ignored; this is intentionally simple and may mis-order pre-release
    suffixes, which is fine for the "is there a stable release?" check.
    """

    def parts(v: str) -> list[int]:
        return [int(x) for x in (v or "").split(".") if x.isdigit()]

    return parts(latest) > parts(current)


def check_for_update(timeout: float = 5.0) -> dict:
    """Return ``{current, latest, update_available, url, error}``.

    ``error`` is populated only when the network call failed; in that case
    ``update_available`` is always ``False`` so the UI can show "could not
    check" without alarming the user.
    """
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = (data.get("tag_name") or "").lstrip("v")
        html_url = data.get("html_url", "")
        return {
            "current": __version__,
            "latest": latest,
            "update_available": bool(latest) and _is_newer(latest, __version__),
            "url": html_url,
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "current": __version__,
            "latest": "",
            "update_available": False,
            "url": "",
            "error": str(exc),
        }