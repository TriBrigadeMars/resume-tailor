"""Web search clients for company/role research.

Supported providers: Tavily, Brave Search, SerpAPI.
Each takes an API key + query and returns clean text snippets.
"""

from __future__ import annotations

import urllib.request
import urllib.parse
import json
import urllib.error

SEARCH_PROVIDERS = {
    "tavily": {
        "label": "Tavily Search",
        "url": "https://api.tavily.com/search",
        "params": {"query": "$QUERY", "search_depth": "basic", "max_results": 5},
        "headers": lambda key: {"Authorization": f"Bearer {key}"},
        "extract": lambda body: "\n\n".join(
            r.get("content", "") for r in body.get("results", [])
        ),
        "get_url": lambda body: "",
    },
    "brave": {
        "label": "Brave Search",
        "url": "https://api.search.brave.com/res/v1/web/search",
        "params": {"q": "$QUERY", "count": 5},
        "headers": lambda key: {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        },
        "extract": lambda body: "\n\n".join(
            r.get("description", "") for r in body.get("web", {}).get("results", [])
        ),
        "get_url": lambda body: "",
    },
    "serpapi": {
        "label": "SerpAPI",
        "url": "https://serpapi.com/search",
        "params": {"q": "$QUERY", "api_key": "$KEY", "engine": "google", "num": 5},
        "headers": lambda key: {},
        "extract": lambda body: "\n\n".join(
            r.get("snippet", "")
            for r in body.get("organic_results", [])
        ),
        "get_url": lambda body: "",
    },
}


def search_web(provider: str, api_key: str, query: str, timeout: float = 30.0) -> str:
    """Run a web search and return concatenated result text.

    Raises RuntimeError on failure.
    """
    cfg = SEARCH_PROVIDERS.get(provider)
    if not cfg:
        raise RuntimeError(f"Unknown search provider: {provider}")

    url = cfg["url"]
    params = {}
    for k, v in cfg["params"].items():
        v = v.replace("$QUERY", query).replace("$KEY", api_key)
        params[k] = v
    headers = cfg["headers"](api_key)
    # Add user-agent
    headers["User-Agent"] = "ResumeTailor/1.0"

    if provider in ("tavily",):
        # POST with JSON body
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST"
        )
    elif provider == "brave":
        # GET with query string
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers=headers)
    else:
        # SerpAPI: GET with query string (api_key in params)
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Search API returned HTTP {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach search API: {exc.reason}")

    text = cfg["extract"](body)
    if not text.strip():
        raise RuntimeError("Search returned no results.")

    return text
