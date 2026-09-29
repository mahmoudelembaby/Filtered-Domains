import pytest
import tempfile, os
from app.cache.redis_cache import Cache
from app.database.db import init_db
from app.database.repository import Repository
from app.metadata.fetcher import MetadataFetcher
from app.classifiers.jev import JevModel
from app.classifiers.base import WebsiteMetadata
from app.policy.engine import PolicyEngine
from app.classifiers.orchestrator import Orchestrator
from app.metrics import Metrics


class StaticFetcher(MetadataFetcher):
    def __init__(self, md: WebsiteMetadata | None):
        super().__init__()
        self._md = md
    async def fetch(self, domain: str):
        return self._md


def _deps(md, tmp):
    cache = Cache("")  # in-memory
    repo = Repository(tmp)
    jev = JevModel(mode="heuristic")
    policy = PolicyEngine(0.90, 0.90, "1.0")
    return Orchestrator(cache, repo, StaticFetcher(md), jev, policy, Metrics(), 86400, 21600, 1800)


@pytest.mark.asyncio
async def test_orchestrator_caches_second_hit():
    tmp = os.path.join(tempfile.mkdtemp(), "t.db")
    await init_db(tmp)
    md = WebsiteMetadata(domain="github.com", title="GitHub code hosting",
                         description="software development platform", keywords=["programming"])
    orch = _deps(md, tmp)
    r1 = await orch.classify("github.com")
    assert r1.cache_hit is False and r1.decision == "ALLOW"
    r2 = await orch.classify("github.com")
    assert r2.cache_hit is True and r2.decision == "ALLOW"


@pytest.mark.asyncio
async def test_manual_override_wins():
    tmp = os.path.join(tempfile.mkdtemp(), "t2.db")
    await init_db(tmp)
    md = WebsiteMetadata(domain="github.com", title="GitHub", description="software")
    orch = _deps(md, tmp)
    await orch.repo.set_override({"domain": "github.com", "decision": "MANUAL_BLOCK",
                                  "created_by": "it", "reason": "test",
                                  "created_at": "2026-01-01T00:00:00+00:00", "expires_at": None})
    r = await orch.classify("github.com")
    assert r.decision == "BLOCK"


@pytest.mark.asyncio
async def test_metadata_failure_is_review_not_block():
    tmp = os.path.join(tempfile.mkdtemp(), "t3.db")
    await init_db(tmp)
    orch = _deps(None, tmp)
    r = await orch.classify("example.com")
    assert r.decision == "REVIEW"
