import logging
import os
import aiohttp

logger = logging.getLogger("bot.web_search")

TAVILY_URL = "https://api.tavily.com/search"


async def web_search(query: str, num: int = 5) -> str:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return "Web search is not configured (missing TAVILY_API_KEY)."

    payload = {
        "query": query,
        "max_results": num,
        "include_answer": True,
        "search_depth": "basic",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    logger.error("Tavily search HTTP %d: %s", resp.status, detail)
                    return f"Search error: HTTP {resp.status}"
                data = await resp.json()
    except Exception as e:
        logger.exception("web_search failed")
        return f"Search error: {e}"

    parts = []
    answer = data.get("answer")
    if answer:
        parts.append(f"Quick answer: {answer}")

    for i, item in enumerate(data.get("results", []), 1):
        title = item.get("title", "")
        content = (item.get("content", "") or "").replace("\n", " ")
        url = item.get("url", "")
        parts.append(f"Result {i}: {title}\nURL: {url}\nSnippet: {content}")

    return "\n\n".join(parts) if parts else "No results found."
