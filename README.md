# Filtered-Domains — website relevance filter v1 (Jev-only, no Docker)

Decides whether a website is relevant to at least one legitimate business function
(AI/Data, IT, HR, Marketing, Sales, Medical, Finance, Management, Research, Operations, …).
No per-department rules. Output is global: `ALLOW` / `BLOCK` / `REVIEW`.

- `RELATED` + high confidence → `ALLOW`
- `NOT_RELATED` + high confidence → `BLOCK`
- Low confidence, fetcher failure, or Jev error → `REVIEW` (fail-safe, never forced to BLOCK)

## Stack

Python 3.11+ / FastAPI / httpx / Redis (optional, in-memory fallback) / SQLite / Gradio UI.
AI: Jev TypeSafe System One only (`POST https://api.typesafe.ai/v1/systemone`,
`model: jev-latest`, one `noul` question over the site metadata as `state`).
No Laya fallback in v1. No Docker.

## How classification works

1. Normalize domain → `example.com` (`www.` stripped, subdomains kept).
2. Manual override wins: `MANUAL_BLOCK` → `BLOCK`, `MANUAL_ALLOW` → `ALLOW`.
3. Cache: Redis `website:classification:{domain}`, then SQLite backfill. Hit returns immediately.
4. Metadata fetch (HTTPS-first, SSRF guard, 1 MB / 3-redirect / 8 s limits, HTML-only).
5. Jev `noul`: “Is this website relevant to at least one legitimate business function?”
   State is untrusted data; instructions are fixed, so prompt-injection text in pages is ignored.
   `noul ≥ 0.5` → related, confidence = distance from 0.5.
6. Policy (`allow/block_threshold: 0.90`): related + ≥ threshold → `ALLOW`,
   not-related + ≥ threshold → `BLOCK`, else `REVIEW`.
7. Store Redis (ALLOW 24 h / BLOCK 6 h / REVIEW 30 min) + SQLite, log audit event.

Example: `x.com` returns `REVIEW` with confidence 0.0 because its servers answer
`403 Forbidden` to plain fetches (bot guard) → `METADATA_UNAVAILABLE`, not a Jev verdict.

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then set JEV_API_KEY in .env (never commit it)
# optional: start Redis; without it the app uses in-memory cache automatically
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python ui.py                  # Gradio UI on http://127.0.0.1:7860
```

SQLite is created at `./data/website_filter.db` on startup.

## Config (`.env`)

| Key | Default | Notes |
| --- | --- | --- |
| `JEV_API_URL` | `https://api.typesafe.ai/v1/systemone` | Full endpoint; trailing `/v1` auto-appends `/systemone` |
| `JEV_API_KEY` | — | Bearer key, keep in `.env` only |
| `JEV_MODE` | `api` | `api` = live Jev; `heuristic` = offline keyword stand-in (`model=jev-heuristic`) |
| `ALLOW_THRESHOLD` / `BLOCK_THRESHOLD` | `0.90` | Tune on a labeled dataset |
| `ALLOW_TTL` / `BLOCK_TTL` / `REVIEW_TTL` | `86400` / `21600` / `1800` | Seconds |
| `ADMIN_API_KEY` | `changeme` | Sent as `X-Admin-Key` on `/admin/*`; empty = open (dev only) |
| `REDIS_URL` / `SQLITE_PATH` | `redis://localhost:6379/0` / `./data/website_filter.db` | |

## API

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/classify `
  -ContentType 'application/json' -Body '{"domain":"github.com"}'
# → {"domain":"github.com","decision":"ALLOW","related":true,"confidence":0.96,
#    "model":"jev","fallback_used":false,"cache_hit":false}

Invoke-RestMethod http://127.0.0.1:8000/domain/github.com
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/metrics   # Prometheus text
```

Admin (header `X-Admin-Key`):

- `GET /admin/reviews?limit=50` — queued `REVIEW` domains
- `POST /admin/override` — `{"domain":"x.com","decision":"MANUAL_BLOCK","reason":"..."}`
- `DELETE /admin/override/{domain}`
- `POST /admin/cache/invalidate` — `{"domain":"x.com"}` or `{"all":true}`
- `GET /admin/metrics` — JSON hit rates, review rate, p50/p95/p99

The Gradio UI (`ui.py`) exposes the same in three tabs: Classify / Lookup / Admin.

## Tests + eval

```powershell
$env:PYTHONPATH='.'; pytest -q   # 12 tests: domain, policy, SSRF, parser, Jev schema, orchestrator
$env:PYTHONPATH='.'; python evaluation/evaluate.py evaluation/dataset_example.csv
```

## Layout

`app/config.py`, `app/utils/domain.py`, `app/classifiers/{base,jev,orchestrator}.py`,
`app/metadata/{fetcher,parser,sanitizer}.py`, `app/security/ssrf.py`,
`app/cache/redis_cache.py`, `app/database/{db,repository}.py`,
`app/policy/engine.py`, `app/metrics.py`, `app/api/routes.py`, `app/main.py`,
`ui.py`, `evaluation/`, `tests/`
