from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WebsiteMetadata:
    domain: str
    url: str = ""
    title: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    og_title: str = ""
    og_description: str = ""
    schema_description: str = ""

    def to_prompt_json(self) -> dict:
        return {
            "domain": self.domain,
            "title": self.title[:300],
            "description": self.description[:500],
            "keywords": self.keywords[:20],
            "headings": self.headings[:20],
            "opengraph_title": self.og_title[:300],
            "opengraph_description": self.og_description[:500],
            "schema_description": self.schema_description[:500],
        }


@dataclass
class DecisionResult:
    related: bool
    confidence: float
    model: str
    model_version: str
    latency_ms: float
    error: str | None = None

    def is_reliable(self) -> bool:
        return self.error is None

    def to_json(self) -> dict:
        return {
            "related": self.related,
            "confidence": self.confidence,
            "model": self.model,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class DecisionModel(ABC):
    @abstractmethod
    async def classify(self, metadata: WebsiteMetadata) -> DecisionResult:
        ...
