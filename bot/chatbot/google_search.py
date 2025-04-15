import asyncio
from bs4 import BeautifulSoup
from googlesearch import search
from http.cookiejar import MozillaCookieJar
import httpx

from config import COOKIES_PATH
from bot.search import is_url


def search_sites(query: str, num_results: int = 15) -> list:
    """Return a list of URLs based on the query, using Google search."""
    results = []
    for result in search(query, advanced=True, lang="en", num_results=num_results):
        results.append(result)

    return results


async def search_(
    query: str,
    scrap: bool = False,
    text_limit_per_site: int = 5000,
    site_limit: int = 6,
) -> str:
    """Return a summary and the scraped text based on a query."""
    results = await asyncio.to_thread(search_sites, query)

    # Get the description of results
    summary = ", ".join([f"{r.url} : {r.description}" for r in results])
    if not scrap:
        return summary

    # Scraping mode
    seen_urls = set()
    scraped_text = ""
    i = 0
    seen_sites = 0
    scraped_text = ""
    cookie_jar = None
    try:
        cookie_jar = MozillaCookieJar(COOKIES_PATH)
        cookie_jar.load()
    except FileNotFoundError:
        ...

    async with httpx.AsyncClient(cookies=cookie_jar) as client:
        while i < len(results) and seen_sites < site_limit:
            url = results[i].url
            i += 1

            if not is_url(url) or url in seen_urls:
                continue

            seen_urls.add(url)
            seen_sites += 1

            response = await client.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            paragraphs = soup.find_all("p")

            text = "\n".join(
                line.strip()
                for p in paragraphs
                for line in p.text.splitlines()
                if line.strip()
            )

            scraped_text += text[:text_limit_per_site]

    return scraped_text
