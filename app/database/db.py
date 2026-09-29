"""SQLite persistence: websites + manual_overrides + classification_events."""
from __future__ import annotations
import os
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS websites (
  domain TEXT PRIMARY KEY,
  decision TEXT NOT NULL,
  related INTEGER NOT NULL,
  confidence REAL NOT NULL,
  model TEXT NOT NULL,
  model_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  classified_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manual_overrides (
  domain TEXT PRIMARY KEY,
  decision TEXT NOT NULL,
  created_by TEXT DEFAULT '',
  reason TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  expires_at TEXT
);
CREATE TABLE IF NOT EXISTS classification_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL,
  model TEXT NOT NULL,
  model_version TEXT NOT NULL,
  cache_hit INTEGER NOT NULL,
  fallback_used INTEGER NOT NULL DEFAULT 0,
  decision TEXT NOT NULL,
  confidence REAL NOT NULL,
  latency_ms REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_domain ON classification_events(domain);
CREATE INDEX IF NOT EXISTS idx_events_created ON classification_events(created_at);
"""


async def init_db(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
