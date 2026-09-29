# website-filter v1 (Jev-only, Redis + SQLite, no Docker)

Global relevance filter: `RELATED` to >=1 business function → `ALLOW`, `NOT_RELATED` → `BLOCK`, low-confidence/failure → `REVIEW`. No per-department rules.

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# optional: start Redis; without it the app uses in-memory cache automatically
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

SQLite file is created at `./data/website_filter.db` on startup.

## API

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/classify `
  -ContentType 'application/json' -Body '{"domain":"github.com"}'

Invoke-RestMethod http://localhost:8000/domain/github.com
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/metrics
```

Admin (send `X-Admin-Key` matching `.env` `ADMIN_API_KEY`):

- `GET /admin/reviews?limit=50`
- `POST /admin/override` `{"domain":"x.com","decision":"MANUAL_BLOCK","reason":"..."}`
- `DELETE /admin/override/{domain}`
- `POST /admin/cache/invalidate` `{"domain":"x.com"}` or `{"all":true}`
- `GET /admin/metrics`

## Jev modes

- `JEV_MODE=heuristic` (default when `JEV_API_URL` empty): offline keyword stand-in, `model=jev-heuristic`. Good for dev/eval.
- `JEV_MODE=api` + `JEV_API_URL` + `JEV_API_KEY`: production call. Prompt separates `system` from `untrusted_metadata`; response `{"decision":"RELATED|NOT_RELATED|UNCERTAIN","confidence":0..1}` (also accepts `{"related":bool,...}` and OpenAI `choices` wrapper).

## Tests + eval

```powershell
$env:PYTHONPATH='.'
pytest -q
python evaluation/evaluate.py evaluation/dataset_example.csv
```

## Layout

`app/config.py`, `app/utils/domain.py`, `app/classifiers/{base,jev,orchestrator}.py`,
`app/metadata/{fetcher,parser,sanitizer}.py`, `app/security/ssrf.py`,
`app/cache/redis_cache.py`, `app/database/{db,repository}.py`,
`app/policy/engine.py`, `app/metrics.py`, `app/api/routes.py`, `app/main.py`
