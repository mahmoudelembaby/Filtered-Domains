"""Trim + strip control chars. Metadata stays untrusted; never executed as instructions."""
import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(s: str, limit: int) -> str:
    s = _CTRL.sub("", s or "")
    return " ".join(s.split())[:limit]


def sanitize_metadata(d: dict) -> dict:
    d["title"] = clean(d.get("title", ""), 300)
    d["description"] = clean(d.get("description", ""), 500)
    d["og_title"] = clean(d.get("og_title", ""), 300)
    d["og_description"] = clean(d.get("og_description", ""), 500)
    d["schema_description"] = clean(d.get("schema_description", ""), 500)
    d["keywords"] = [clean(k, 100) for k in d.get("keywords", []) if clean(k, 100)][:20]
    d["headings"] = [clean(h, 200) for h in d.get("headings", []) if clean(h, 200)][:20]
    return d
