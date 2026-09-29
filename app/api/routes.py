from __future__ import annotations
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from app.utils.domain import normalize_domain

router = APIRouter()


class ClassifyIn(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


class OverrideIn(BaseModel):
    domain: str
    decision: str  # MANUAL_ALLOW | MANUAL_BLOCK
    reason: str = ""
    created_by: str = ""
    expires_in_sec: int | None = None


class InvalidateIn(BaseModel):
    domain: str | None = None
    all: bool = False


def orchestrator(request: Request):
    return request.app.state.orchestrator


def require_admin(request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")):
    expected = request.app.state.settings.admin_api_key
    if expected and x_admin_key != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True


@router.post("/classify")
async def classify(body: ClassifyIn, request: Request):
    orch = orchestrator(request)
    try:
        res = await orch.classify(body.domain)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "domain": res.domain, "decision": res.decision, "related": res.related,
        "confidence": res.confidence, "model": res.model,
        "fallback_used": res.fallback_used, "cache_hit": res.cache_hit,
    }


@router.get("/domain/{domain}")
async def get_domain(domain: str, request: Request):
    try:
        d = normalize_domain(domain)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    orch = orchestrator(request)
    cached = await orch.cache.get_decision(d)
    if cached:
        return cached
    row = await orch.repo.get_website(d)
    if not row:
        raise HTTPException(status_code=404, detail="unknown domain")
    return row


@router.get("/admin/reviews")
async def reviews(request: Request, limit: int = 50, _=Depends(require_admin)):
    orch = orchestrator(request)
    return await orch.repo.get_reviews(min(limit, 200))


@router.post("/admin/override")
async def set_override(body: OverrideIn, request: Request, _=Depends(require_admin)):
    if body.decision not in ("MANUAL_ALLOW", "MANUAL_BLOCK"):
        raise HTTPException(status_code=422, detail="decision must be MANUAL_ALLOW|MANUAL_BLOCK")
    try:
        d = normalize_domain(body.domain)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    orch = orchestrator(request)
    now = datetime.now(timezone.utc).isoformat()
    expires = None
    if body.expires_in_sec:
        from datetime import timedelta
        expires = (datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_sec)).isoformat()
    entry = {"domain": d, "decision": body.decision, "created_by": body.created_by,
             "reason": body.reason, "created_at": now, "expires_at": expires}
    await orch.repo.set_override(entry)
    await orch.cache.set_override(d, {"decision": body.decision})
    await orch.cache.invalidate(d)
    return {"ok": True, "domain": d, "decision": body.decision}


@router.delete("/admin/override/{domain}")
async def delete_override(domain: str, request: Request, _=Depends(require_admin)):
    try:
        d = normalize_domain(domain)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    orch = orchestrator(request)
    await orch.repo.delete_override(d)
    await orch.cache.delete_override(d)
    await orch.cache.invalidate(d)
    return {"ok": True}


@router.post("/admin/cache/invalidate")
async def invalidate(body: InvalidateIn, request: Request, _=Depends(require_admin)):
    orch = orchestrator(request)
    if body.all:
        n = await orch.cache.invalidate(all=True)
        return {"ok": True, "invalidated": n}
    if body.domain:
        try:
            d = normalize_domain(body.domain)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        n = await orch.cache.invalidate(d)
        return {"ok": True, "invalidated": n}
    raise HTTPException(status_code=422, detail="provide domain or all:true")


@router.get("/admin/metrics")
async def admin_metrics(request: Request, _=Depends(require_admin)):
    return request.app.state.metrics.snapshot()
