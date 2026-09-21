"""Web search clients for company/role research.

Supported providers: Tavily, Brave Search, SerpAPI.
Each takes an API key + query and returns clean text snippets.
"""

from __future__ import annotations

import urllib.request
import urllib.parse
import json
import urllib.error

USER_AGENT = "ResumeTailor/1.0"


def _tavily(api_key, query):
    """Tavily: POST a JSON body, authenticated with a bearer token."""
    payload = {"query": query, "search_depth": "basic", "max_results": 5}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    return req, lambda body: "\n\n".join(
        r.get("content", "") for r in body.get("results", [])
    )


def _brave(api_key, query):
    """Brave: GET with the key in a dedicated header."""
    params = urllib.parse.urlencode({"q": query, "count": 5})
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
        "User-Agent": USER_AGENT,
    }
    req = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}", headers=headers
    )
    return req, lambda body: "\n\n".join(
        r.get("description", "") for r in body.get("web", {}).get("results", [])
    )


def _serpapi(api_key, query):
    """SerpAPI: GET with the key as a query parameter."""
    params = urllib.parse.urlencode(
        {"q": query, "api_key": api_key, "engine": "google", "num": 5}
    )
    req = urllib.request.Request(
        f"https://serpapi.com/search?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    return req, lambda body: "\n\n".join(
        r.get("snippet", "") for r in body.get("organic_results", [])
    )


SEARCH_PROVIDERS = {
    "tavily": {"label": "Tavily Search", "build": _tavily},
    "brave": {"label": "Brave Search", "build": _brave},
    "serpapi": {"label": "SerpAPI", "build": _serpapi},
}


def search_web(provider, api_key, query, timeout=30.0):
    """Run a web search and return concatenated result text.

    Raises RuntimeError on failure.
    """
    cfg = SEARCH_PROVIDERS.get(provider)
    if not cfg:
        raise RuntimeError(f"Unknown search provider: {provider}")

    req, extract = cfg["build"](api_key, query)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Search API returned HTTP {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach search API: {exc.reason}")

    text = extract(body)
    if not text.strip():
        raise RuntimeError("Search returned no results.")

    return text
