# Part A — Inbound Lead Enrichment Tool
## Requirements & Technical Design

> Production-shaped MVP for the EliseAI GTM Engineer take-home.
> Companion: [PART_B](./PART_B_Rollout_Plan.md) (rollout plan), [README](./README.md) (quick start), [DEMO_SCRIPT](./DEMO_SCRIPT.md) (video storyboard).

---

## 1. Problem Statement

EliseAI's SDR team handles a high volume of inbound leads daily. Each lead enters with only basic fields:

- **Person**: name, email, company
- **Building**: property address, city, state, country

SDRs manually research, prioritize, and draft personalized intros — 15–30 min per lead. This tool automates the upstream process and delivers a **production-shaped MVP with a human-feedback loop**.

## 2. Input/Output Specification

### 2.1 Input Fields

7 fields per PDF Context section: `name, email, company, property_address, city, state, country`

> **PDF inconsistency**: Context section shows 7 fields, Deliverables shows 6 (no Country). This tool implements 7 per Context; Country drives geographic routing (US/CA vs others).

### 2.2 Input Channel

| Channel | When |
|---|---|
| **Dashboard CSV upload** (primary) | SDR/Marketing uploads CSV via UI → writes Postgres `leads` with status='pending' |
| Test fixture | Local dev `tests/fixtures/leads.csv` |

### 2.3 Output (DB-backed, rendered via Dashboard)

Each lead generates cross-table data:

| Table | Key fields |
|---|---|
| `runs` | id, started_at, finished_at, status, lead_count, success_count, report_md |
| `leads` | id, run_id, name, email, company, address fields, status, processed_at |
| `enriched_data` | lead_id, json blobs per API source, errors |
| `provenance` | lead_id, fact_key, source, confidence, fetched_at, raw_ref |
| `scores` | lead_id, total, tier, breakdown, reasons[] |
| `emails` | id, lead_id, subject, body, source, warnings[] |
| `feedback` | id, email_id, action, final_subject, final_body, review_seconds |
| `api_logs` | run_id, lead_id, api_name, started_at, duration_ms, status, error |
| `alert_history` | alert_key, last_sent, count |

## 3. Architecture

### 3.1 Form-Factor Decision

**Pipeline and Dashboard are separated, sharing Postgres as the single source of truth.**

| Alternative | Adopted | Reason |
|---|---|---|
| Monolith (FastAPI + APScheduler) | ❌ | Web crash kills cron; pipeline competes for web resources |
| **Separated (cron + FastAPI sharing DB)** | ✅ | Crash-resilient, independently debuggable, free GH Actions cron |
| Queue (FastAPI + Redis + Worker) | ❌ | Unnecessary at this scale |

### 3.2 Data Flow

```
GH Actions cron (9am)
        │ writes
        ▼
   Neon Postgres (single source of truth)
        ▲                                   ▲
        │ feedback                          │ reads
   FastAPI server ◄──── HTTP ──── React Dashboard
   (Render)                       (Vercel)
                                          │ triggers
                                          ▼
                                       Resend → alert email
```

### 3.3 Pipeline Flow

```
fetch pending leads
    ↓
Enrichment (parallel): Census / News / Wikipedia / WalkScore / FRED / NMHC
    ↓ each fact → provenance table
Scoring (rule engine, 55/30/15 weights)
    ↓
Insights (rules) ─┬─ Email (LLM with provenance) ─ Hallucination check
                  └─────────────────┬─────────────────┘
                                    ▼
                              Write to DB
```

## 4. Tech Stack

### 4.1 Backend

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| Web | FastAPI |
| HTTP | `httpx` |
| Retry | `tenacity` |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| LLM | `anthropic` |
| Logging | `structlog` |
| Email alerts | `resend` |
| Config | `pydantic-settings` + `.env` |
| Tests | `pytest` + `pytest-asyncio` |
| Cron host | GitHub Actions |

### 4.2 Frontend

| Component | Choice |
|---|---|
| Build | Vite + TypeScript |
| UI | shadcn/ui + Tailwind |
| Data | TanStack Query |
| Routing | React Router |
| Charts | Recharts |
| Forms | React Hook Form + Zod |
| Diff | `react-diff-viewer-continued` |
| Type generation | `openapi-typescript` |

### 4.3 Infrastructure

| Component | Platform | Free tier |
|---|---|---|
| Postgres | Neon | 0.5 GB permanent |
| FastAPI | Render | Free (cold-start 30s) |
| React | Vercel | Unlimited (personal) |
| Cron | GitHub Actions | Unlimited (public repo) |
| Email | Resend | 3000/mo, 100/day |

## 5. Repo Structure

Monorepo layout:

```
elise-lead-pipeline/
├── backend/               # Python: FastAPI + pipeline
│   └── elise_leads/
│       ├── settings.py
│       ├── models/
│       ├── enrichers/     # 7 enrichers (incl. FRED + NMHC new in v2)
│       ├── scoring/
│       ├── generation/    # email + prompts + hallucination
│       ├── alerting/
│       ├── pipeline.py
│       ├── cron.py
│       └── api/
├── frontend/              # React + Vite + TS
│   └── src/
│       ├── pages/         # 7 pages (Overview/Inbox/Leads/etc.)
│       └── components/
├── infra/
│   ├── .github/workflows/ # cron.yml + deploys
│   └── render.yaml
└── docs/
```

## 6. Database Schema

Core tables (SQLAlchemy 2.0 ORM): `runs`, `leads`, `enriched_data`, `provenance`, `scores`, `emails`, `feedback`, `api_logs`, `alert_history`. Schema details are mirrored in the Chinese section §6.

## 7. REST API Endpoints

```
POST   /api/v1/uploads                # CSV upload
POST   /api/v1/runs/trigger           # manual run trigger
GET    /api/v1/runs                   # list
GET    /api/v1/runs/{id}              # detail + MD report
GET    /api/v1/leads                  # list with filters
GET    /api/v1/leads/{id}             # detail + provenance
POST   /api/v1/leads/{id}/feedback    # one-click approve/edit/reject
GET    /api/v1/metrics/overview       # KPIs + chart data
GET    /api/v1/metrics/api-performance
```

OpenAPI auto-generated via FastAPI, TS types via `openapi-typescript`.

## 8. Frontend Specification

### 8.1 Sitemap

```
/             Overview (KPIs + trends + recent runs)
/inbox        SDR review (Inbox + Card mode toggle)
/leads        All leads (Table view with filters)
/leads/:id    Lead detail (enriched + score + email + provenance + feedback history)
/runs         Run history
/runs/:id     Run detail + MD report
/upload       CSV upload + Process now
```

### 8.2 Key Interactions

**Inbox mode** (default): list + detail panel.
**Card mode** ("Focus"): single full-screen lead, keyboard `A`/`R`/`E`/`J`/`K`. ~10 min for 50 leads.
**Email edit**: inline textarea, "Approve" auto-diffs original vs final → writes feedback. "View Changes" opens modal with side-by-side diff.
**Source attribution**: each fact in email body gets a footnote citation showing source.

### 8.3 Real-time

TanStack Query polling at 3s interval (only when run is `running`). No WebSocket.

## 9. Enrichment API Details

| API | Endpoint | Auth | Fields | Confidence |
|---|---|---|---|---|
| Census Geocoder | geocoding.geo.census.gov | none | tract / lat / lon | 0.95 |
| Census ACS | api.census.gov/data/2022/acs/acs5 | free key | renter_pct, income, rent | 0.95 |
| NewsAPI | newsapi.org/v2/everything | key | articles, signal_keywords | 0.85/0.70 |
| Wikipedia | en.wikipedia.org/w/api.php | none (UA req) | summary, scale | 0.70 |
| WalkScore | api.walkscore.com/score | key | walk/transit/bike | 0.85 |
| **FRED** | api.stlouisfed.org/fred | free key | vacancy, rent_yoy | 0.95 |
| **NMHC Top 50** | local JSON | none | rank, units | 0.95 |

### 9.1 Rate Limiting Strategy

| API | Hard limit | Defense |
|---|---|---|
| NewsAPI | 100/day | LRU cache by company + persistent quota tracking |
| Census ACS | unlimited (with key) | LRU cache by tract |
| WalkScore | 5000/day | LRU cache by rounded coordinates |
| Claude | 50 RPM (Tier 1) | Throttle 1.3s/req + tenacity backoff on 429 |
| FRED | 120/min | Cache by state |

## 10. Scoring Rubric v2

### 10.1 Weight Distribution (100 pts)

```
Company-side  (55) ████████████████████████████████████████████████████████
Geography     (30) ██████████████████████████████
Contact-side  (15) ███████████████
```

### 10.2 Dimensions

#### Company Scale (25 pts) — NMHC + Wikipedia + News

- NMHC Top 10: 15 / Top 50: 10
- Wikipedia scale extracted: 5 / page exists: 2
- News count + premium sources: up to 5

#### Buy Intent (20 pts) — News keywords

| Keyword | Score |
|---|---|
| acquired/merger/acquisition | 20 |
| expansion/launched/new property | 18 |
| funding/raised/series | 15 |
| partnership/technology | 12 |
| any company news | 10 |
| no news | 5 |

#### Vertical Fit (10 pts)

| Match | Effect |
|---|---|
| multifamily/student/affordable/military/SFR | +10 |
| **senior/commercial** | **Hard Cold (tier override)** |

#### Market Fit (15 pts)

- Renter % from Census (8 max)
- Median income from Census (7 max)

#### Property Fit (10 pts)

- WalkScore (5 max)
- Median rent from Census (5 max)

#### Market Dynamics (5 pts) — FRED

- State vacancy rate (3 max; high vacancy = more leasing pressure)
- Rent YoY growth (2 max)

#### Contact Fit (15 pts)

- Corporate email domain (5)
- Domain ↔ company name match (5)
- Prefix shape: `first.last` (5) / single (3) / generic inbox (0)

### 10.3 Tier Thresholds

```
Hot:  ≥75
Warm: 55–74
Cold: <55
```

### 10.4 Missing-Data Fallback

**Principle: never penalize missing data. Use median + annotation.**

### 10.5 Validation

Extended golden cases include "company > geography" verification (Asset Living rural → Hot) and "geography ≠ score" verification (Unknown @ Manhattan → Cold).

## 11. Email Generation + Multi-Layer Hallucination Defense

### 11.1 Four Defense Layers

```
L1: Provenance tracking → every fact has source + confidence
L2: Provenance-aware prompt → XML structure + grounding rules
L3: Post-gen check → number/entity verification + auto-regenerate
L4: UI source attribution → SDR can self-verify
```

### 11.2 Layer 2: Prompt Structure

System prompt (~600 tokens): role + product proof points (XML) + rules (must reference only verified_facts; cite specific numbers only if confidence ≥ 0.85; never invent).

User prompt: `<lead>` + `<verified_facts>` (each fact with source/confidence) + `<lead_score>` + `<recommended_proof_point>` + `<instructions>`.

### 11.3 Layer 3: Post-Gen Detection

```python
def detect_hallucination(email, facts):
    issues = []
    # 1. Number verification
    # 2. Entity verification (Claude Haiku for NER)
    # 3. Time phrase check
    return issues

# Severe issue → auto-regenerate (max 2x), then template fallback
```

### 11.4 Fallback Chain

```
L1: tenacity retry same model (3x)
L2: Switch to Haiku 4.5 (same SDK, same prompt)
L4: Template fallback (deterministic string)
```

Each email records `email.source` for traceability.

## 12. Logging & Observability

### 12.1 Three Channels

```
Channel 1: structlog → stdout JSON → GH Actions UI
Channel 2: api_logs table → Dashboard SQL queries
Channel 3: runs.report_md → Dashboard MD render
```

### 12.2 MD Report Template

Auto-generated per run, includes summary, API performance table (avg/p95/failures), notable events. Renders in dashboard `/runs/:id`.

## 13. Alerting

### 13.1 Configuration

```bash
ALERT_EMAIL=alert@example.com
RESEND_API_KEY=re_xxxxx
```

### 13.2 Severity & Cooldown

| Severity | Cooldown | Triggers |
|---|---|---|
| immediate | 0 | Pipeline crash, all leads failed |
| throttled | 1h | >30% failure rate, API quota exhausted |

### 13.3 Email Body

MD-formatted with What/Affected/Action sections, rendered to HTML by Resend.

## 14. Error Handling

| Layer | Failure | Handling |
|---|---|---|
| API | Single API fails | Skip, median fallback for that dimension |
| API | Claude all attempts fail | Haiku → template chain |
| Lead | Single lead exception | Inner try/except, mark failed, continue |
| Pipeline | Top-level exception | Outer try/except, immediate alert |

## 15. Validation Strategy

| Method | When | Output |
|---|---|---|
| Golden cases | CI required | 9 cases covering Hot/Warm/Cold/edge |
| Sensitivity analysis | Pre-release | Weight ±20% tier distribution stability |
| Distribution check | Post-batch | tier ratio ~20/50/30 |
| Production backtest (README) | Post-launch | Spearman corr w/ closed-won/lost |

## 16. Cost & Scaling

### 16.1 Take-home Scale (50 leads/batch + 30 days dashboard)

| Item | Cost |
|---|---|
| Neon / Render / Vercel / GH Actions / Resend | $0 |
| Census / Wikipedia / WalkScore / FRED / NewsAPI free tier | $0 |
| Claude Sonnet (50 × $0.015) | $0.75 |
| Claude Haiku (hallucination check) | $0.05 |
| **Total** | **~$0.80** |

### 16.2 Scaling Path (README)

| Daily volume | Action |
|---|---|
| <500 | Current architecture |
| 500–5k | Enable prompt caching, DB indexes, Neon paid |
| 5k+ | Async + Claude Batch API + Redis |
| 10k+ | Queues + workers, Postgres on RDS, multi-cron |

## 17. Key Decision Log (v2)

| # | Decision | Choice | Reason |
|---|---|---|---|
| 1 | Form factor | FastAPI + React + Postgres separated | Crash-resilient, production-shaped |
| 2 | Database | Neon Postgres + SQLite local via SQLAlchemy | Switchable |
| 3 | Scheduler | GitHub Actions cron | Free, portable |
| 4 | Lead input | Dashboard CSV upload | Single source of truth |
| 5 | Logging | structlog stdout + api_logs table + MD report | Don't reinvent |
| 6 | Alerting | Resend + hardcoded recipient + 2-tier cooldown | MVP simplification |
| 7 | Workflow UX | Inbox + Card + Table tri-mode | Different review tempos |
| 8 | Email edit | Inline + diff modal | Speed + data fidelity |
| 9 | Scoring shift | Company 55 / Geography 30 / Contact 15 | Fix v1 over-weight on geography |
| 10 | Vertical disqualifier | senior/commercial → hard Cold | Strict ICP boundary |
| 11 | Company scale signals | NMHC + Wiki + News combination | Skip SEC/scraping |
| 12 | Hallucination defense | 4-layer (provenance + prompt + check + UI) | LLM is highest risk |
| 13 | LLM model | Sonnet 4.6 primary / Haiku 4.5 fallback | Cost vs quality |

---

*End of Part A document.*
