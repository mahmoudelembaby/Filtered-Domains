from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.cache.redis_cache import Cache
from app.database.db import init_db
from app.database.repository import Repository
from app.metadata.fetcher import MetadataFetcher
from app.classifiers.jev import JevModel
from app.policy.engine import PolicyEngine
from app.classifiers.orchestrator import Orchestrator
from app.metrics import metrics
from app.api.routes import router

logging.basicConfig(level=settings.log_level.upper(),
                    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}')
log = logging.getLogger("website-filter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.sqlite_path)
    cache = Cache(settings.redis_url)
    await cache.connect()
    repo = Repository(settings.sqlite_path)
    fetcher = MetadataFetcher(
        timeout_s=settings.fetch_timeout_s,
        connect_timeout_s=settings.fetch_connect_timeout_s,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
        user_agent=settings.fetch_user_agent,
    )
    jev = JevModel(api_url=settings.jev_api_url, api_key=settings.jev_api_key,
                   model_version=settings.jev_model_version,
                   timeout_ms=settings.jev_timeout_ms, mode=settings.jev_mode)
    policy = PolicyEngine(settings.allow_threshold, settings.block_threshold,
                          settings.policy_version)
    app.state.settings = settings
    app.state.cache = cache
    app.state.repo = repo
    app.state.fetcher = fetcher
    app.state.jev = jev
    app.state.policy = policy
    app.state.metrics = metrics
    app.state.orchestrator = Orchestrator(
        cache, repo, fetcher, jev, policy, metrics,
        settings.allow_ttl, settings.block_ttl, settings.review_ttl,
    )
    log.info("startup complete jev_mode=%s redis=%s sqlite=%s",
             "api" if jev._use_api() else "heuristic", settings.redis_url, settings.sqlite_path)
    yield
    try:
        await fetcher.aclose()
    except Exception:
        pass
    await cache.close()


def create_app() -> FastAPI:
    app = FastAPI(title="website-filter v1", lifespan=lifespan)
    app.include_router(router)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prom():
        return metrics.prometheus()

    return app


app = create_app()
