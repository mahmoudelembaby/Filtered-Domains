# Filtered-Domains — website relevance filter v1 (Jev-only, no Docker)

Decides whether a website is relevant to **at least one legitimate business function**
(AI/Data, IT/Technology, HR, Marketing, Sales, Doctors/Medical, Finance, Management,
Research, Operations, Education, Business). There are **no per-department rules**:
a doctor can reach an AI site, marketing can reach AI tools, sales can reach research.

Final outcomes are global:

| AI verdict | Confidence | Decision | Meaning |
| --- | --- | --- | --- |
| RELATED | ≥ `ALLOW_THRESHOLD` (0.90) | `ALLOW` | Safe to allow |
| NOT_RELATED | ≥ `BLOCK_THRESHOLD` (0.90) | `BLOCK` | Safe to block |
| anything else / error / timeout | — | `REVIEW` | Needs a human; never auto-blocked |

The AI supplies evidence; a deterministic Python policy makes the decision; a human
(IT admin override) always wins.

## 1. Architecture

```text
DOMAIN
  │
  ▼
Normalize Domain  ("https://www.example.com/" → "example.com")
  │
  ▼
Manual BLOCK? ──YES──▶ BLOCK
  │ NO
  ▼
Manual ALLOW? ──YES──▶ ALLOW
  │ NO
  ▼
Redis cache? ──HIT──▶ return stored decision
  │ MISS
  ▼
SQLite backfill? ──HIT (unexpired)──▶ refill Redis, return
  │ MISS
  ▼
Fetch metadata (HTTPS-first, SSRF guard, size/time limits)
  │ None (403/timeout/non-HTML/empty)
  ▼
REVIEW (METADATA_UNAVAILABLE)
  │ metadata ok
  ▼
Jev System One  POST https://api.typesafe.ai/v1/systemone
  │  { model: jev-latest, state: {website_metadata}, questions.relevant: noul }
  ▼
Policy Engine (thresholds) ──▶ ALLOW / BLOCK / REVIEW
  │
  ▼
Store Redis + SQLite, log audit event, return
```

Request path optimizes in this order: cache hit rate → metadata latency →
Jev latency → DB latency. Only uncached, unfetched domains pay for a Jev call.

**v1 scope:** Jev-only (no Laya fallback), Redis + SQLite, no Docker, no background
worker, no per-department ACLs, no firewall writes, no full-site crawling
(metadata tags + headings only).

## 2. Repository layout

```text
app/config.py                     pydantic-settings (.env), thresholds, TTLs, fetcher/Jev tuning
app/utils/domain.py               normalize_domain(), cache_key(), override_key()
app/classifiers/base.py           WebsiteMetadata, DecisionResult, DecisionModel interface
app/classifiers/jev.py            JevModel (System One client + heuristic stand-in)
app/classifiers/orchestrator.py   classify_domain() — override → cache → metadata → Jev → policy
app/metadata/fetcher.py           async httpx fetcher (pooling, timeouts, size/redirect caps)
app/metadata/parser.py            BeautifulSoup extraction (scripts/styles stripped)
app/metadata/sanitizer.py         truncation + control-char stripping
app/security/ssrf.py              hostname + resolved-IP validation, DNS-rebinding guard
app/cache/redis_cache.py          Redis fast cache with in-memory fallback
app/database/db.py                SQLite schema init
app/database/repository.py        websites / manual_overrides / classification_events access
app/policy/engine.py              ALLOW/BLOCK/REVIEW policy + per-decision TTLs
app/metrics.py                    in-memory counters/latencies + Prometheus exposition
app/api/routes.py                 REST routes (public + admin)
app/main.py                       FastAPI app, lifespan wiring, /health, /metrics
ui.py                             Gradio frontend (Classify / Lookup / Admin tabs)
evaluation/evaluate.py            offline Jev scoring script
evaluation/dataset_example.csv    10-row example dataset
tests/                            pytest suite (12 tests)
```

## 3. Requirements

- Python 3.11+ (developed on 3.14), `pip install -r requirements.txt`
- Redis **optional** — if `REDIS_URL` is unreachable the app transparently uses an
  in-memory cache (same TTL semantics, lost on restart)
- A Jev/TypeSafe API key for live mode; without one use `JEV_MODE=heuristic`
- No Docker, no Postgres in v1

## 4. Configuration (`.env`)

Copy `.env.example` → `.env`. `.env` is git-ignored; never commit keys.

| Key | Default | Purpose |
| --- | --- | --- |
| `JEV_API_URL` | `https://api.typesafe.ai/v1/systemone` | Full endpoint. A trailing `/v1` base auto-appends `/systemone` |
| `JEV_API_KEY` | — | `Authorization: Bearer` key for TypeSafe |
| `JEV_MODEL_VERSION` | `1.x` | Display fallback; live responses report the resolved version (e.g. `jev-1.13.0`) |
| `JEV_TIMEOUT_MS` | `5000` | Jev HTTP timeout |
| `JEV_MODE` | `api` | `api` = live Jev only; `heuristic` = offline keyword stand-in (`model=jev-heuristic`) |
| `ALLOW_THRESHOLD` / `BLOCK_THRESHOLD` | `0.90` / `0.90` | Policy cutoffs — validate on your own labeled set before changing |
| `POLICY_VERSION` | `1.0` | Stored per decision; bump when thresholds change |
| `ALLOW_TTL` / `BLOCK_TTL` / `REVIEW_TTL` | `86400` / `21600` / `1800` | Cache seconds (24 h / 6 h / 30 min) |
| `ADMIN_API_KEY` | `changeme` | Required as `X-Admin-Key` on `/admin/*`; empty = open (dev only) |
| `REDIS_URL` | `redis://localhost:6379/0` | Fast cache; falls back to memory when down |
| `SQLITE_PATH` | `./data/website_filter.db` | Created on startup; source of truth + audit |
| `FETCH_TIMEOUT_S` / `FETCH_CONNECT_TIMEOUT_S` | `8.0` / `3.0` | Total / connect timeouts |
| `FETCH_MAX_BYTES` | `1000000` | Body cap (1 MB), streamed |
| `FETCH_MAX_REDIRECTS` | `3` | Redirect limit |
| `FETCH_USER_AGENT` | `website-filter/1.0 (+internal IT use)` | Outbound UA |

## 5. Running

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then put the real JEV_API_KEY in .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python ui.py                  # Gradio UI → http://127.0.0.1:7860 (BACKEND_URL env overrides API host)
```

- API docs: `http://127.0.0.1:8000/docs`
- Gradio calls the API over HTTP, so it works against any reachable backend
  (`$env:BACKEND_URL='http://host:8000'; python ui.py`).

## 6. API reference

### `POST /classify`

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/classify `
  -ContentType 'application/json' -Body '{"domain":"github.com"}'
```

```json
{
  "domain": "github.com",
  "decision": "ALLOW",
  "related": true,
  "confidence": 0.96,
  "model": "jev",
  "fallback_used": false,
  "cache_hit": false
}
```

Invalid domains → `422`. `fallback_used` is always `false` in v1 (no Laya).

### `GET /domain/{domain}`

Returns the stored entry (Redis first, else SQLite) or `404` if never classified.

### `GET /health` · `GET /metrics`

Liveness probe and Prometheus text (`website_filter_requests_total`,
`website_filter_cache_hit_rate`, `website_filter_review_rate`,
`website_filter_p95_latency_ms`).

### Admin (header `X-Admin-Key: <ADMIN_API_KEY>`)

| Method | Path | Body | Effect |
| --- | --- | --- | --- |
| `GET` | `/admin/reviews?limit=50` | — | `REVIEW` rows, newest first (max 200) |
| `POST` | `/admin/override` | `{"domain","decision":"MANUAL_ALLOW\|MANUAL_BLOCK","reason?","created_by?","expires_in_sec?"}` | Persist override, warm override cache, drop decision cache |
| `DELETE` | `/admin/override/{domain}` | — | Remove override + caches |
| `POST` | `/admin/cache/invalidate` | `{"domain":"x.com"}` or `{"all":true}` | Drop Redis entries (SQLite rows stay as history) |
| `GET` | `/admin/metrics` | — | JSON: totals, hit/review rates, avg/p50/p95/p99 latency |

## 7. Classification pipeline (details)

**Normalization** (`app/utils/domain.py`): lowercase, strip scheme/path/port,
drop one `www.` prefix, keep all other subdomains (`mail.example.com` stays),
IDNA + label validation. `localhost`, single-label names, and malformed hosts → `422`.

**Overrides** beat everything: `MANUAL_BLOCK` first, then `MANUAL_ALLOW`, then cache,
then Jev. Overrides persist in SQLite and are mirrored to Redis (`website:override:{domain}`).

**Cache entries** (`website:classification:{domain}`):

```json
{
  "domain": "github.com", "decision": "ALLOW", "related": true, "confidence": 0.96,
  "model": "jev", "model_version": "jev-1.13.0", "policy_version": "1.0",
  "classified_at": "2026-09-29T13:18:54+00:00", "expires_at": "2026-09-30T13:18:54+00:00"
}
```

**Metadata** extracted per fetch: page `<title>`, `meta description/keywords`,
`og:title`, `og:description`, first ~20 `h1–h3` headings, JSON-LD/microdata
description. Scripts, styles, and templates are removed before parsing; every field
is length-capped. Non-HTML content-types, empty bodies, and HTTP ≥ 400 yield no
metadata → `REVIEW (METADATA_UNAVAILABLE)`.

**Jev call** (`app/classifiers/jev.py`): one `noul` question with fixed instructions;
the site metadata travels as `state` data, never as instructions:

```json
{
  "model": "jev-latest",
  "state": {"website_metadata": {"domain": "...", "title": "...", "description": "...",
            "keywords": [...], "headings": [...], "opengraph_title": "...",
            "opengraph_description": "...", "schema_description": "..."}},
  "questions": {"relevant": {"type": "noul",
    "instructions": "Is this website relevant to at least one legitimate business function (...)? ..."}}
}
```

`answers.relevant.noul` (P(yes)) maps to `related = p ≥ 0.5`,
`confidence = p` (or `1 − p`). Transport/401/429/422/5xx and malformed bodies
return a `DecisionResult` with `error` set → policy → `REVIEW`.

## 8. Storage schema (SQLite)

`websites(domain PK, decision, related, confidence, model, model_version,
policy_version, classified_at, expires_at)` — every fresh decision upserts one row.

`manual_overrides(domain PK, decision, created_by, reason, created_at, expires_at)`.

`classification_events(id, domain, model, model_version, cache_hit, fallback_used,
decision, confidence, latency_ms, created_at)` — one row per request, including
cache hits and overrides; the audit trail. No employee browsing data is stored.

## 9. Security

- **SSRF** (`app/security/ssrf.py`): rejects `localhost`, single-label names,
  `*.internal/.local/.lan/.corp/.home/.localhost`; resolves the host and rejects
  if **any** IP is private, loopback, link-local, multicast, reserved, unspecified,
  or cloud-metadata (`169.254.169.254`). Only `http/https`, HTML only.
- **Prompt injection**: page content is parsed as data and sent as `state`;
  the question text is fixed server-side. “Ignore previous instructions” inside a
  page cannot change the question.
- **Admin auth**: `X-Admin-Key` checked on all `/admin/*` when `ADMIN_API_KEY` is set.
- **Secrets**: live keys live in `.env` (ignored). `.env.example` ships empty.

## 10. Observability

In-memory counters + bounded latency ring, exposed as JSON (`/admin/metrics`) and
Prometheus (`/metrics`): totals, `cache_hit_rate`, `jev_request_rate`,
`review_rate`, allow/block/review counts, avg/p50/p95/p99 latency. Every request
also writes a `classification_events` row with model, version, cache-hit flag,
decision, confidence, and latency.

## 11. Evaluation

`evaluation/dataset_example.csv` (`domain,title,description,keywords(|…),headings(|…),
expected=RELATED|NOT_RELATED`) plus `evaluation/evaluate.py`, which scores Jev
offline (no network) and reports accuracy, precision, recall, F1, false-positive/
false-negative rates, review rate, and p50/p95/p99 latency. Grow this to 1,000–5,000
company-labeled domains across AI, tech, medical, research, HR, marketing, sales,
finance, education, entertainment, and ambiguous/multilingual sites before tuning
thresholds — the most important operational metric is the **false-positive blocking
rate** (legitimate sites must not be blocked on uncertainty).

## 12. Tests

```powershell
$env:PYTHONPATH='.'; pytest -q
```

12 tests: domain normalization, policy matrix, SSRF blocks, parser + Jev schema,
orchestrator (cache hit, override precedence, metadata-failure → REVIEW).

## 13. Operational notes

- `x.com` currently classifies `REVIEW`: its edge answers `403` to plain fetches,
  so there is no metadata for Jev. Use `MANUAL_ALLOW` if IT approves, or add a
  rendered-fetch fallback later.
- Cache invalidation clears Redis only; SQLite keeps history and will backfill on
  the next miss — delete the SQLite row too for a fully fresh re-classification.
- Rotate a leaked key by replacing `JEV_API_KEY` in `.env` and restarting uvicorn.
- Retune thresholds only against your labeled set; record the `POLICY_VERSION`.

## 14. Out of scope for v1

Laya fallback, Postgres, Docker, background pre-warming workers, batch inference,
full-page crawling, per-department permissions, firewall enforcement, model
fine-tuning, employee profiling.
