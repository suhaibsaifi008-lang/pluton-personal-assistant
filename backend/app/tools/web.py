import html as html_module
import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from ..config import get_settings
from ..security import PermissionLevel
from .base import Tool, _STRING_PROP, _schema
from .registry import ToolRegistry

USER_AGENT = "PLUTON-Agent/0.1 (local personal agent)"


def _strip_tags(text: str) -> str:
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_module.unescape(re.sub(r"\s+", " ", text)).strip()


def _web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    settings = get_settings()
    results: list[dict[str, str]] = []
    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=settings.web_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        html = response.text
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S):
            raw_url, title = match.group(1), html_module.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
            url = raw_url
            if "uddg=" in raw_url:
                start = raw_url.index("uddg=") + len("uddg=")
                end = raw_url.find("&", start)
                url = unquote(raw_url[start:end if end != -1 else len(raw_url)])
            elif url.startswith("//"):
                url = f"https:{url}"
            results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= max_results:
                break
        snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.S)
        for index, snippet in enumerate(snippets):
            if index >= len(results):
                break
            results[index]["snippet"] = html_module.unescape(re.sub(r"<[^>]+>", "", snippet)).strip()
        if not results:
            return {"results": [], "note": "No results found.", "query": query}
        return {"query": query, "results": results[:max_results]}
    except httpx.HTTPStatusError:
        return {"error": "Web search failed (provider returned an error).", "query": query}
    except httpx.RequestError:
        return {"error": "Web search failed: PLUTON could not reach the search service.", "query": query}


def _web_fetch(url: str, max_chars: int = 6000) -> dict[str, Any]:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"error": "Only http/https URLs are allowed.", "url": url}
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=settings.web_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        text = _strip_tags(response.text)
        if len(text) > max_chars:
            text = f"{text[:max_chars]}\n...[truncated]"
        return {"url": url, "title": _strip_tags(re.sub(r"<title[^>]*>([\s\S]*?)</title>", r"\1", response.text))[:200], "content": text}
    except httpx.HTTPStatusError as error:
        return {"error": f"HTTP {error.response.status_code} for {url}.", "url": url}
    except httpx.RequestError:
        return {"error": f"PLUTON could not fetch {url}.", "url": url}


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "web.search",
            "Search the web for a query and return the top result titles, URLs, and snippets.",
            PermissionLevel.LOW,
            _schema({"query": _STRING_PROP}, ["query"]),
            _web_search,
        )
    )
    registry.register(
        Tool(
            "web.fetch",
            "Fetch an http/https web page and return its visible text content.",
            PermissionLevel.LOW,
            _schema({"url": _STRING_PROP}, ["url"]),
            _web_fetch,
        )
    )
