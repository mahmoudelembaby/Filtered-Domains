"""Core orchestrator v1: override -> cache(Redis, then SQLite) -> metadata -> Jev -> policy."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import time

from app.utils.domain import normalize_domain
from app.cache.redis_cache import Cache
from app.database.repository import Repository
from app.metadata.fetcher import MetadataFetcher
from app.classifiers.jev import JevModel
from app.classifiers.base import DecisionResult
from app.policy.engine import PolicyEngine
from app.metrics import Metrics


@dataclass
class ClassificationResponse:
    domain: str
    decision: str
    related: bool
    confidence: float
    model: str
    fallback_used: bool
    cache_hit: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Orchestrator:
    def __init__(
        self, cache: Cache, repo: Repository, fetcher: MetadataFetcher,
        jev: JevModel, policy: PolicyEngine, metrics: Metrics,
        allow_ttl: int, block_ttl: int, review_ttl: int,
    ):
        self.cache = cache
        self.repo = repo
        self.fetcher = fetcher
        self.jev = jev
        self.policy = policy
        self.metrics = metrics
        self.ttls = {"ALLOW": allow_ttl, "BLOCK": block_ttl, "REVIEW": review_ttl}

    async def classify(self, raw_domain: str) -> ClassificationResponse:
        t0 = time.perf_counter()
        domain = normalize_domain(raw_domain)

        # 1. Manual override (Redis fast copy, else SQLite)
        ov = await self.cache.get_override(domain)
        if ov is None:
            row = await self.repo.get_override(domain)
            if row and not _expired(row.get("expires_at")):
                ov = {"decision": row["decision"]}
                await self.cache.set_override(domain, ov)
        if ov:
            decision = "ALLOW" if ov["decision"] == "MANUAL_ALLOW" else "BLOCK"
            latency = (time.perf_counter() - t0) * 1000.0
            await self.repo.log_event(_event(domain, "manual", "1.0", True, decision, 1.0, latency))
            self.metrics.observe(cache_hit=False, jev_called=False, decision=decision, latency_ms=latency)
            return ClassificationResponse(domain, decision, decision == "ALLOW", 1.0, "manual", False, False)

        # 2. Cache: Redis, then SQLite backfill
        cached = await self.cache.get_decision(domain)
        if cached and not _expired(cached.get("expires_at")):
            latency = (time.perf_counter() - t0) * 1000.0
            await self.repo.log_event(_event(domain, cached.get("model", "?"),
                                             cached.get("model_version", "?"), True,
                                             cached["decision"], cached.get("confidence", 0.0), latency))
            self.metrics.observe(cache_hit=True, jev_called=False, decision=cached["decision"], latency_ms=latency)
            return ClassificationResponse(domain, cached["decision"], bool(cached.get("related")),
                                          float(cached.get("confidence", 0.0)),
                                          cached.get("model", "?"), False, True)
        if cached is None:
            row = await self.repo.get_website(domain)
            if row and not _expired(row.get("expires_at")):
                payload = {
                    "domain": domain, "decision": row["decision"], "related": bool(row["related"]),
                    "confidence": row["confidence"], "model": row["model"],
                    "model_version": row["model_version"], "policy_version": row["policy_version"],
                    "classified_at": row["classified_at"], "expires_at": row["expires_at"],
                }
                await self.cache.set_decision(domain, payload, _ttl_left(row["expires_at"]))
                latency = (time.perf_counter() - t0) * 1000.0
                await self.repo.log_event(_event(domain, row["model"], row["model_version"],
                                                 True, row["decision"], row["confidence"], latency))
                self.metrics.observe(cache_hit=True, jev_called=False, decision=row["decision"], latency_ms=latency)
                return ClassificationResponse(domain, row["decision"], bool(row["related"]),
                                              row["confidence"], row["model"], False, True)

        # 3. Metadata
        metadata = await self.fetcher.fetch(domain)
        if metadata is None:
            result = DecisionResult(False, 0.0, self._model_name(), self.jev.model_version,
                                    (time.perf_counter() - t0) * 1000.0, error="METADATA_UNAVAILABLE")
            return await self._finish(domain, result, t0, jev_called=False)

        # 4. Jev only (v1 — no Laya)
        result = await self.jev.classify(metadata)
        return await self._finish(domain, result, t0, jev_called=True)

    def _model_name(self) -> str:
        return "jev" if self.jev._use_api() else "jev-heuristic"

    async def _finish(self, domain: str, result: DecisionResult, t0: float, jev_called: bool) -> ClassificationResponse:
        pd = self.policy.decide(result)
        ttl = self.ttls.get(pd.decision, self.ttls["REVIEW"])
        now = datetime.now(timezone.utc)
        payload = {
            "domain": domain, "decision": pd.decision, "related": result.related,
            "confidence": result.confidence, "model": result.model,
            "model_version": result.model_version, "policy_version": self.policy.policy_version,
            "classified_at": now.isoformat(), "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
        }
        await self.cache.set_decision(domain, payload, ttl)
        await self.repo.upsert_website(payload)
        latency = (time.perf_counter() - t0) * 1000.0
        await self.repo.log_event(_event(domain, result.model, result.model_version,
                                         False, pd.decision, result.confidence, latency))
        self.metrics.observe(cache_hit=False, jev_called=jev_called, decision=pd.decision, latency_ms=latency)
        return ClassificationResponse(domain, pd.decision, result.related, result.confidence,
                                      result.model, False, False)


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        now = datetime.now(timezone.utc)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= now
    except Exception:
        return True


def _ttl_left(expires_at: str) -> int:
    try:
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return max(60, int((exp - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        return 1800


def _event(domain: str, model: str, mv: str, hit: bool, decision: str, conf: float, lat: float) -> dict:
    return {"domain": domain, "model": model, "model_version": mv, "cache_hit": hit,
            "fallback_used": 0, "decision": decision, "confidence": conf,
            "latency_ms": lat, "created_at": _now_iso()}
