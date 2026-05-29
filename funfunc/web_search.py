import asyncio
import os
from googleapiclient.discovery import build


async def web_search(query: str, num: int = 5) -> str:
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_CSE_ID", "")
    if not api_key or not cse_id:
        return "Web search is not configured (missing GOOGLE_API_KEY or GOOGLE_CSE_ID)."
    try:
        def _search():
            service = build("customsearch", "v1", developerKey=api_key)
            return service.cse().list(q=query, cx=cse_id, num=num).execute()

        res = await asyncio.to_thread(_search)
        items = res.get("items", [])
        if not items:
            return "No results found."

        parts = []
        for i, item in enumerate(items, 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "").replace("\n", " ")
            link = item.get("link", "")
            parts.append(f"Result {i}: {title}\nURL: {link}\nSnippet: {snippet}")
        return "\n\n".join(parts)
    except Exception as e:
        return f"Search error: {e}"
