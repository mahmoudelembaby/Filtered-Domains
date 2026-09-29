"""Parse HTML safely: scripts/styles removed, only required metadata extracted."""
from bs4 import BeautifulSoup
import json


def _text(v: str | None, limit: int) -> str:
    if not v:
        return ""
    return " ".join(v.split())[:limit]


def parse_metadata(html: str, url: str, domain: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    title = _text(soup.title.string if soup.title and soup.title.string else "", 300)

    def meta_content(*names: str) -> str:
        for name in names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find(
                "meta", attrs={"property": name}
            )
            if tag and tag.get("content"):
                return _text(tag["content"], 500)
        return ""

    description = meta_content("description")
    keywords_raw = meta_content("keywords")
    keywords = [k.strip()[:100] for k in keywords_raw.split(",") if k.strip()][:20]

    og_title = ""
    og_desc = ""
    for prop, key in (("og:title", "og_title"), ("og:description", "og_desc")):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            if key == "og_title":
                og_title = _text(tag["content"], 300)
            else:
                og_desc = _text(tag["content"], 500)

    headings: list[str] = []
    for level in ("h1", "h2", "h3"):
        for h in soup.find_all(level)[:7]:
            t = _text(h.get_text(" "), 200)
            if t:
                headings.append(t)
            if len(headings) >= 20:
                break

    schema_description = ""
    # JSON-LD description
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("description"):
                schema_description = _text(str(item["description"]), 500)
                break
        if schema_description:
            break
    if not schema_description:
        tag = soup.find(attrs={"itemprop": "description"})
        if tag:
            schema_description = _text(tag.get_text(" "), 500)

    return {
        "domain": domain,
        "url": url,
        "title": title,
        "description": description,
        "keywords": keywords,
        "headings": headings,
        "og_title": og_title,
        "og_description": og_desc,
        "schema_description": schema_description,
    }
