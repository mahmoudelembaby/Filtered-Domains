"""Async metadata fetcher: validates URL, enforces SSRF guard, timeouts, size limits."""
from __future__ import annotations
from urllib.parse import urlparse
import httpx

from app.security.ssrf import resolve_and_validate, SSRFError
from app.metadata.parser import parse_metadata
from app.metadata.sanitizer import sanitize_metadata
from app.classifiers.base import WebsiteMetadata

ALLOWED_SCHEMES = {"https", "http"}
ALLOWED_CONTENT = ("text/html", "application/xhtml+xml")


class FetchError(Exception):
    pass


class MetadataFetcher:
    def __init__(
        self,
        timeout_s: float = 8.0,
        connect_timeout_s: float = 3.0,
        max_bytes: int = 1_000_000,
        max_redirects: int = 3,
        user_agent: str = "website-filter/1.0",
    ):
        self.timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s)
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                max_redirects=self.max_redirects,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*;q=0.8"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch(self, domain: str) -> WebsiteMetadata | None:
        # Prefer HTTPS, fall back to HTTP once
        for scheme in ("https", "http"):
            try:
                md = await self._fetch_one(f"{scheme}://{domain}/", domain)
                if md is not None:
                    return md
            except SSRFError:
                return None
            except FetchError:
                continue
        return None

    async def _fetch_one(self, url: str, domain: str) -> WebsiteMetadata | None:
        parsed = urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise FetchError("unsupported protocol")
        host = parsed.hostname or ""
        await resolve_and_validate(host)  # raises SSRFError on private/internal

        client = await self._client_get()
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise FetchError(f"http {resp.status_code}")
                ctype = resp.headers.get("content-type", "").lower()
                if ctype and not any(t in ctype for t in ALLOWED_CONTENT):
                    raise FetchError(f"unsupported content-type {ctype}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(65536):
                    total += len(chunk)
                    if total > self.max_bytes:
                        break
                    chunks.append(chunk)
                html = b"".join(chunks).decode("utf-8", errors="ignore")
                if not html.strip():
                    raise FetchError("empty body")
                final_url = str(resp.url)
        except SSRFError:
            raise
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(str(e))

        raw = parse_metadata(html[: self.max_bytes], final_url, domain)
        raw = sanitize_metadata(raw)
        return WebsiteMetadata(
            domain=domain,
            url=final_url,
            title=raw["title"],
            description=raw["description"],
            keywords=raw["keywords"],
            headings=raw["headings"],
            og_title=raw["og_title"],
            og_description=raw["og_description"],
            schema_description=raw["schema_description"],
        )
