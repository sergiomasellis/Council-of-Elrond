"""Brave Search and web fetch tools for LLM Council models."""

import logging
import httpx
import json
from .config import BRAVE_SEARCH_API_KEY

logger = logging.getLogger(__name__)

# Max characters to return from a fetched page
FETCH_MAX_CHARS = 20000

# OpenAI-compatible tool definitions
SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use this when you need up-to-date facts, recent events, current data, or to verify claims.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch the contents of a URL. Use this to read documentation pages, articles, llms.txt files, or any publicly accessible web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch"
                    }
                },
                "required": ["url"]
            }
        }
    }
]


async def brave_search(query: str) -> str:
    """
    Search the web using Brave's LLM Context API.

    Args:
        query: The search query string

    Returns:
        Formatted search results as a string, or error message on failure
    """
    if not BRAVE_SEARCH_API_KEY:
        logger.error("BRAVE_SEARCH_API_KEY is not configured")
        return "Error: BRAVE_SEARCH_API_KEY is not configured."
    
    logger.info(f"Brave search initiated: {query}")

    url = "https://api.search.brave.com/res/v1/llm/context"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }
    params = {"q": query}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        # The LLM context API returns a summarized context string
        # Format varies but typically includes web results
        parts = []

        # Handle summarizer/context response
        if "summary" in data:
            parts.append(data["summary"])

        # Handle web search results if present
        if "web" in data and "results" in data["web"]:
            for i, result in enumerate(data["web"]["results"][:5], 1):
                title = result.get("title", "")
                url_str = result.get("url", "")
                description = result.get("description", "")
                parts.append(f"{i}. {title}\n   URL: {url_str}\n   {description}")

        if parts:
            return "\n\n".join(parts)

        # Fallback: return raw response text if structure is unexpected
        return json.dumps(data, indent=2)[:3000]

    except httpx.HTTPStatusError as e:
        logger.error(f"Brave Search HTTP error: {e.response.status_code} - {e.response.text[:200]}")
        return f"Search error: HTTP {e.response.status_code}"
    except Exception as e:
        logger.exception("Brave Search unexpected error")
        return f"Search error: {e}"


async def fetch_url(url: str) -> str:
    """
    Fetch the text content of a URL.

    Handles plain text directly and strips HTML to plain text for web pages.

    Args:
        url: The URL to fetch

    Returns:
        Page content as plain text, truncated to FETCH_MAX_CHARS
    """
    logger.info(f"Fetching URL: {url}")
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "LLM-Council/1.0 (web fetch tool)",
                "Accept": "text/plain, text/html, text/markdown, application/json, */*",
            })
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            text = response.text

            # For HTML, do a lightweight strip to plain text
            if "text/html" in content_type:
                text = _strip_html(text)

            if len(text) > FETCH_MAX_CHARS:
                text = text[:FETCH_MAX_CHARS] + "\n\n[...truncated]"

            logger.info(f"Fetched {len(text)} chars from {url}")
            return text

    except httpx.HTTPStatusError as e:
        logger.error(f"Fetch URL HTTP error: {e.response.status_code} for {url}")
        return f"Fetch error: HTTP {e.response.status_code}"
    except Exception as e:
        logger.exception(f"Fetch URL unexpected error for {url}")
        return f"Fetch error: {e}"


def _strip_html(html: str) -> str:
    """Lightweight HTML to plain text conversion."""
    import re
    # Remove script and style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block tags with newlines
    text = re.sub(r'<(br|p|div|h[1-6]|li|tr)[^>]*/?>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def execute_search_tool(name: str, arguments: str) -> str:
    """
    Execute a tool call by name.

    Args:
        name: The tool function name (e.g., "web_search", "fetch_url")
        arguments: JSON string of arguments

    Returns:
        Tool result as a string
    """
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON arguments for tool {name}: {arguments}")
        return f"Error: Invalid JSON arguments for {name}."

    # Strip whitespace from tool name (some models emit leading/trailing spaces)
    name = name.strip()

    logger.info(f"Executing tool '{name}' with args {args}")

    if name == "web_search":
        query = args.get("query", "")
        if not query:
            logger.warning("web_search called with empty query")
            return "Error: No search query provided."
        logger.debug(f"[Tool] web_search: {query}")
        result = await brave_search(query)
        logger.debug(f"[Tool] web_search result length: {len(result)}")
        return result

    elif name == "fetch_url":
        url = args.get("url", "")
        if not url:
            logger.warning("fetch_url called with empty URL")
            return "Error: No URL provided."
        logger.debug(f"[Tool] fetch_url: {url}")
        result = await fetch_url(url)
        logger.debug(f"[Tool] fetch_url result length: {len(result)}")
        return result

    else:
        logger.warning(f"Attempted to execute unknown search tool '{name}'")
        return f"Error: Unknown tool '{name}'."
