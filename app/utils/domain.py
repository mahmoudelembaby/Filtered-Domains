"""Domain normalization + cache keys. No per-department logic (global relevance)."""
import re
from urllib.parse import urlparse

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_domain(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        raise ValueError("empty domain")
    if "://" not in s:
        s = "https://" + s
    parsed = urlparse(s)
    host = parsed.hostname or ""
    host = host.strip().rstrip(".").lower()
    if not host:
        raise ValueError(f"invalid domain: {raw!r}")
    # canonical: strip single www. prefix, keep all other subdomains
    if host == "www." or host.startswith("www."):
        host = host[4:]
    if len(host) > 253:
        raise ValueError("domain too long")
    labels = host.split(".")
    if len(labels) < 2 or any(not _LABEL.match(lb) for lb in labels):
        raise ValueError(f"invalid domain: {raw!r}")
    # IDNA round-trip to reject weird unicode
    try:
        host = host.encode("idna").decode("ascii")
    except Exception as e:
        raise ValueError(f"invalid domain: {raw!r}: {e}")
    return host


def cache_key(domain: str) -> str:
    return f"website:classification:{domain}"


def override_key(domain: str) -> str:
    return f"website:override:{domain}"
