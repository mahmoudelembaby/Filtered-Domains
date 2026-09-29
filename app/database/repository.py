from __future__ import annotations
import aiosqlite


class Repository:
    def __init__(self, path: str):
        self.path = path

    # ---- websites ----
    async def get_website(self, domain: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM websites WHERE domain=?", (domain,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def upsert_website(self, entry: dict) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO websites(domain,decision,related,confidence,model,model_version,
                   policy_version,classified_at,expires_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(domain) DO UPDATE SET
                   decision=excluded.decision, related=excluded.related,
                   confidence=excluded.confidence, model=excluded.model,
                   model_version=excluded.model_version, policy_version=excluded.policy_version,
                   classified_at=excluded.classified_at, expires_at=excluded.expires_at""",
                (entry["domain"], entry["decision"], int(entry["related"]),
                 entry["confidence"], entry["model"], entry["model_version"],
                 entry["policy_version"], entry["classified_at"], entry["expires_at"]),
            )
            await db.commit()

    # ---- overrides ----
    async def get_override(self, domain: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM manual_overrides WHERE domain=?", (domain,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def set_override(self, entry: dict) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO manual_overrides(domain,decision,created_by,reason,created_at,expires_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(domain) DO UPDATE SET decision=excluded.decision,
                   created_by=excluded.created_by, reason=excluded.reason,
                   created_at=excluded.created_at, expires_at=excluded.expires_at""",
                (entry["domain"], entry["decision"], entry.get("created_by", ""),
                 entry.get("reason", ""), entry["created_at"], entry.get("expires_at")),
            )
            await db.commit()

    async def delete_override(self, domain: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM manual_overrides WHERE domain=?", (domain,))
            await db.commit()

    # ---- events ----
    async def log_event(self, ev: dict) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO classification_events(domain,model,model_version,cache_hit,
                   fallback_used,decision,confidence,latency_ms,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (ev["domain"], ev["model"], ev["model_version"], int(ev["cache_hit"]),
                 int(ev.get("fallback_used", 0)), ev["decision"], ev["confidence"],
                 ev["latency_ms"], ev["created_at"]),
            )
            await db.commit()

    async def get_reviews(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM websites WHERE decision='REVIEW' ORDER BY classified_at DESC LIMIT ?",
                (limit,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
