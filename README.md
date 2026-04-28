# EliseAI Lead Pipeline

Production-shaped MVP for inbound-lead enrichment, ICP scoring, and outreach drafting — built for the **EliseAI GTM Engineer take-home** (April 2026).

> 🎬 **Looking for the demo?** See [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) for the 4-minute storyboard.
> 📐 **Looking for the design?** See [PART_A](./PART_A_Technical_Design.md) (technical spec) and [ROLLOUT_PLAN.md](./ROLLOUT_PLAN.md) (sales-org rollout plan).

---

## What it does

Takes a 7-field inbound lead (name, email, company, address, city, state, country), runs it through 7 public-API enrichers, scores it on a 6-dimension ICP rubric, and drafts an outreach email — with a 4-layer hallucination defense and a complete dashboard for the SDR feedback loop.

```
CSV upload  ─┐
Webhook  ─── ┼─→  Lead (status='pending')
Direct API ──┘                │
                              ▼
                  ┌────────────────────────┐
                  │ Enrichment (parallel)  │ ← 7 APIs: Census Geocoder · Census ACS
                  │  ↓                     │   · NewsAPI · Wikipedia · WalkScore
                  │ Scoring (6 dims, 100pt)│   · FRED · NMHC Top 50 (local)
                  │  ↓                     │
                  │ Email gen (LLM)        │ ← Claude Sonnet 4.6 → Haiku → template
                  │  ↓                     │   (4-layer hallucination defense)
                  │ Persist + Provenance   │
                  └────────────┬───────────┘
                               ▼
                       SDR reviews on dashboard
                       → approve / edit / reject
                       → diff + review_seconds captured
```

## Architecture at a glance

```
┌──────────────────────────────┐
│  GitHub Actions cron (9am)   │  also: manual trigger from /runs
└──────────────┬───────────────┘
               │ writes
               ▼
   ┌────────────────────────────────────────────┐
   │  Postgres (Neon) / SQLite (local)          │
   │  runs · leads · enriched · scores · emails │
   │  feedback · provenance · api_logs · alerts │
   └────────────────────────────────────────────┘
        ▲                                     ▲
        │ feedback                            │ reads
        │                                     │
   ┌────┴──────────────┐         ┌────────────┴────────┐
   │  FastAPI (Render) │◄── HTTP─│  React (Vercel)     │
   │  10 REST endpoints│         │  7 dashboard pages   │
   │  CSV/webhook in   │         │  one-click approve   │
   │  feedback out     │         │  source attribution  │
   └───────────────────┘         └──────────────────────┘
                                          │ alerts
                                          ▼
                                 ┌──────────────────┐
                                 │  Resend → SDR    │
                                 │  immediate/throttled│
                                 └──────────────────┘
```

Detailed schemas + data flow in [PART_A §3](./PART_A_Technical_Design.md).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · structlog · tenacity |
| Frontend | Vite · React 18 · TypeScript · Tailwind · TanStack Query · Recharts |
| Database | Neon Postgres (prod) / SQLite (local dev), switchable via SQLAlchemy URL |
| LLM | Anthropic Claude Sonnet 4.6 (primary) → Haiku 4.5 (fallback) → deterministic template |
| Cron | GitHub Actions (9am UTC daily) |
| Alerting | Resend (immediate / throttled-1h dedup) |
| Tests | pytest · pytest-asyncio · respx · 129 tests, ~99% pipeline coverage |

## Quick start (local)

### Prereqs
- Python 3.11–3.13
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- (Optional) API keys for Census, NewsAPI, WalkScore, FRED, Anthropic, Resend — the dashboard works without them; only the actual pipeline run needs them.

### Backend

```bash
cd backend
cp .env.example .env                      # then optionally fill in API keys
uv sync                                    # install deps (~30s)
uv run alembic upgrade head                # create SQLite schema
uv run python -m scripts.seed_demo         # 2 runs + 11 leads of demo data
uv run uvicorn elise_leads.api.main:app --reload
# → http://localhost:8000/docs (Swagger UI)
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Try the production entry point

```bash
cd backend
uv run python -m scripts.simulate_crm_webhook
# Posts 3 mock Salesforce/HubSpot/Zapier inbound webhooks
# → see http://localhost:5173/leads?status=pending
```

### Run the daily pipeline manually

```bash
cd backend
uv run python -m elise_leads.cron
```

### Tests

```bash
cd backend
uv run pytest                              # 129 tests, ~1s
uv run pytest tests/unit/test_rubric.py    # 9 golden cases for the scoring rubric
```

## Project structure

```
.
├── PART_A_Technical_Design.md     ← Full technical spec
├── PART_B_Rollout_Plan.md         ← Original v2 rollout doc (audit trail)
├── ROLLOUT_PLAN.md                ← Polished standalone rollout plan
├── DEMO_SCRIPT.md                 ← 4-min demo storyboard
├── backend/
│   ├── elise_leads/
│   │   ├── enrichers/             ← 7 API enrichers + concurrent orchestrator
│   │   ├── scoring/               ← 6-dimension rubric (PART_A §10)
│   │   ├── generation/            ← Email gen + 4-layer hallucination defense
│   │   ├── alerting/              ← Resend client + dedup + MD report
│   │   ├── api/                   ← FastAPI routers + Pydantic schemas
│   │   ├── models/                ← 9 SQLAlchemy ORM models
│   │   ├── pipeline.py            ← Per-lead orchestration
│   │   └── cron.py                ← Run lifecycle + alerts
│   ├── alembic/                   ← Migrations
│   ├── tests/                     ← 129 tests
│   └── scripts/
│       ├── seed_demo.py           ← Demo data
│       └── simulate_crm_webhook.py← Production-entry-point demo
├── frontend/
│   ├── src/
│   │   ├── pages/                 ← 7 routes (Overview/Inbox/Leads/Runs/Upload + 2 detail)
│   │   ├── components/            ← KPICard / ScoreBreakdown / ProvenancePanel /
│   │   │                            EmailEditor (with diff modal) / charts/
│   │   └── api/                   ← TanStack Query hooks + TS types mirroring backend
│   └── ...
├── infra/
│   └── docker-compose.yml         ← Local Postgres if not using SQLite
└── .github/workflows/cron.yml     ← Daily 9am UTC pipeline
```

## Key features

- **Provenance tracking**: every fact passed to the LLM is tagged with `source` + `confidence`. The UI shows them as colored badges (green ≥ 0.85 = citable specific number, amber = topic-only). [PART_A §11.2](./PART_A_Technical_Design.md)
- **4-layer hallucination defense**: prompt-level grounding rules + post-gen number/entity verification + auto-regeneration + UI source attribution. [PART_A §11](./PART_A_Technical_Design.md)
- **Tier-based review depth**: Hot 100% review · Warm 50% · Cold 10%, mapped to Inbox/Card/Table dashboard modes. Powers the rollout-plan KPI **verification burden < 2 min/email**. [PART_B §4.3](./PART_B_Rollout_Plan.md)
- **Closed feedback loop**: every approve/edit/reject captured with `review_seconds` and the original-vs-final diff — directly feeds prompt iteration in Phase 2. [PART_B §4](./PART_B_Rollout_Plan.md)
- **Three input paths**: dashboard CSV upload (manual/RevOps), webhook (Salesforce/HubSpot/Zapier production entry), direct REST API. Same `Lead.status='pending'` anchor downstream.
- **Graceful degradation**: any enricher can fail → median fallback; LLM can fail → template fallback. SDR is never blocked. Demonstrated by the seeded `Jordan Cole` lead with `email_source='template_fallback'`.

## Scoring rubric (v2)

```
Total = 100 pts

Company-side  (55) — strongest signals; fixed v1's geography over-weighting
  ├─ Company Scale     25  (NMHC Top 50 list + Wikipedia + News volume/quality)
  ├─ Buy Intent        20  (News keyword tiers: M&A / expansion / funding / generic)
  └─ Vertical Fit      10  (5 housing sub-verticals + senior/commercial = hard Cold)

Geography     (30)
  ├─ Market Fit        15  (Census renter-pct, median income)
  ├─ Property Fit      10  (WalkScore + Census median rent)
  └─ Market Dynamics    5  (FRED vacancy + rent YoY)

Contact-side  (15) — fixed dead "role keyword" rule from v1
  ├─ Corporate domain   5  (vs gmail/yahoo/etc.)
  ├─ Domain ↔ company   5  (sarah@greystar.com matches "Greystar"; advisor domains -ve)
  └─ Prefix shape       5  (firstname.lastname > single token > generic inbox)

Tier:  ≥75 Hot · 55–74 Warm · <55 Cold
Disqualifiers: senior-living / commercial real estate / non-US/CA → hard Cold
```

9 golden test cases anchor the rubric — see [PART_A §10.5](./PART_A_Technical_Design.md) and `backend/tests/fixtures/golden_cases.py`.

## Cost

Take-home scale (50 leads/batch, 30 days dashboard usage):

| Item | Cost |
|---|---|
| Neon / Render / Vercel / GitHub Actions / Resend | $0 (free tiers) |
| Census / Wikipedia / WalkScore / FRED / NewsAPI free | $0 |
| Claude Sonnet 4.6 (50 × $0.015) | $0.75 |
| Claude Haiku (hallucination check, ~$0.001 × 50) | $0.05 |
| **Total** | **~$0.80** |

Scaling beyond 500 leads/day: enable prompt caching (-88% input cost), Claude Batch API (-50%), Redis cache. See [PART_A §16](./PART_A_Technical_Design.md).

## Daily cron in GitHub Actions

`.github/workflows/cron.yml` schedules the pipeline at **09:00 UTC daily** and
also exposes a manual trigger via the Actions tab (`workflow_dispatch`).

By default the workflow detects missing secrets and **skips the run with a
warning** — so a fresh fork doesn't fail every day in your inbox. To enable
real daily runs, add these repo secrets (Settings → Secrets → Actions):

| Secret | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (Neon free tier works) |
| `ANTHROPIC_API_KEY` | Claude API key |
| `CENSUS_API_KEY` | U.S. Census ACS key (free, instant) |
| `NEWS_API_KEY` | NewsAPI free tier key |
| `WALKSCORE_API_KEY` | WalkScore API key (24–48 h approval) |
| `FRED_API_KEY` | FRED API key (free, instant) |
| `RESEND_API_KEY` | Resend transactional email key |
| `ALERT_EMAIL` | Recipient address for pipeline alerts |

Plus the repo *variable* `ALERT_FROM_ADDRESS` (e.g.
`EliseAI Pipeline <onboarding@resend.dev>`).

`DATABASE_URL` and `ANTHROPIC_API_KEY` are the minimum required; the others
enable individual enrichers — a missing key just disables that one enricher,
and the median-fallback path kicks in.

## Status

```
M1 Project skeleton + DB models     ✅  5 tests
M2 7 enrichers + orchestrator       ✅ 29 tests
M3 Scoring rubric + 9 golden cases  ✅ 34 tests
M4 Email + 4-layer hallucination    ✅ 21 tests
M5 Cron + alerting + pipeline       ✅ 17 tests
M6 FastAPI 10 endpoints             ✅ 23 tests (incl. webhooks)
M7 React dashboard (7 pages)        ✅ build clean
M8 Demo polish (webhook + seed +    ✅ 129 total
   demo script + Today's progress)
─────────────────────────────────────────────
                                     129 tests passing
```

## License

Internal take-home submission. Not for redistribution.
