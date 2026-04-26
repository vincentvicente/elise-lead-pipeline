# Demo Script — EliseAI Lead Pipeline

A 4-minute storyboard for the take-home demonstration video, plus a 5–8
minute "Architecture & Rollout" follow-on so the full submission lands
inside the 5–15 min window the PDF allows.

> Borrows the linear narrative shape of compact Sheet-style demos:
> setup → action → results → tier coverage → failure path → production
> entry point. Every minute of the demo sits on something concrete on
> screen, no abstract slides.

---

## Pre-record checklist

- [ ] Backend running: `cd backend && uv run uvicorn elise_leads.api.main:app --reload`
- [ ] Frontend running: `cd frontend && npm run dev`
- [ ] DB seeded with 2 runs + 11 leads: `uv run python -m scripts.seed_demo`
- [ ] Browser at `http://localhost:5173/`
- [ ] Terminal split: one tab in `backend/`, ready to run the simulator
- [ ] Quiet recording environment, 1080p min, screen + voice

---

## Demo storyboard (4 min)

### Scene 1 · Overview — 30s

**Action**
1. Open `http://localhost:5173/`
2. Pause briefly on the KPI row
3. Pause briefly on Today's pipeline tile

**Voiceover**
> "This is the dashboard for an inbound-lead pipeline I built for the
> EliseAI take-home. Top of the page: today's KPIs — 7 leads processed,
> 42% Hot, 50% approval rate from the SDR team, average review time
> under a minute. The strip below shows today's tier breakdown plus
> what's still pending and the last cron run's health. The 7-day trend
> and tier donut are below. This is what a sales lead would open every
> morning."

### Scene 2 · Inbox + Hot lead detail — 90s

**Action**
1. Click **Inbox** in the sidebar
2. Note the lead list is sorted by score descending — Sarah Johnson @
   Greystar at the top with a Hot badge
3. Click Sarah's row
4. Quickly scan the 4 insights bullets at the top
5. Open the score breakdown collapse — point at Company Scale 25/25 +
   Buy Intent 20/20
6. Read 2-3 lines of the email
7. Open "Source attribution" collapse, point at the green confidence
   badges (≥0.85) vs amber ones

**Voiceover**
> "On the inbox, leads are sorted by score so the Hot ones surface
> first. Sarah Johnson at Greystar — score 92 out of 100. Insights up
> top: NMHC #1 operator, recent acquisition news, high renter market.
>
> Score breakdown shows where the points came from — 6 dimensions
> covering company-side, geography, and contact. The reasons are plain
> English so the SDR can trust it.
>
> The email itself is grounded in verified facts only. Each fact has a
> source and a confidence — green badges ≥ 0.85 are citable specific
> numbers, amber ones can be referenced as topic but not figure. The
> green banner at the top confirms the post-generation hallucination
> check passed."

### Scene 3 · One-click feedback loop — 30s

**Action**
1. Lightly edit one phrase in the email body
2. Notice the button changes to "Save & Approve"
3. Click "View Changes" — the diff modal opens
4. Close the modal
5. Click "Save & Approve" — see the green confirmation
6. Scroll down to Feedback history — new row appears with action="edited"

**Voiceover**
> "When the SDR makes a small edit, the workflow captures the original
> and the final, automatically computes the diff, and stores both. The
> review-time timer measures verification burden — that's the rollout
> KPI we want under 2 minutes per email. The Phase 2 of the rollout
> plan runs entirely on this feedback data."

### Scene 4 · Failure path: template fallback — 45s

**Action**
1. Click **Leads** in the sidebar
2. Filter by tier = Cold
3. Click the row for "Jordan Cole @ Unknown Operator Co"
4. Point at the email source label — `template_fallback`
5. Read the warnings list ("LLM unavailable — used deterministic template")
6. Note the email body still has all the right substitutions

**Voiceover**
> "Now the failure case. This lead — Jordan Cole — hit the cold path:
> NewsAPI quota was exhausted, then Claude was rate-limited, then the
> Haiku fallback also failed. The pipeline still produced an email,
> just from a deterministic template. The SDR can see exactly that
> with the `template_fallback` source label and the warning. Nothing
> got dropped, the SDR isn't blocked, and the alert system fired the
> Resend email so we know to investigate. This is what 4-layer
> fallback looks like in practice."

### Scene 5 · Production entry point: webhook — 45s

**Action**
1. Switch to a terminal in `backend/`
2. Run `uv run python -m scripts.simulate_crm_webhook`
3. Watch 3 webhooks fire — output shows source labels (Salesforce,
   HubSpot, Zapier) and `lead_id` for each
4. Switch back to dashboard — go to **Leads** filtered by status=pending
5. Show the 3 new leads from RPM Living, BH Management, Willow Bridge
6. Hover one: cite the `source` field would carry which CRM fired it

**Voiceover**
> "Production input is a webhook, not the CSV upload. Here's a script
> that mimics three CRMs — Salesforce, HubSpot, Zapier — POSTing inbound
> leads. The endpoint is generic so any system that fires webhooks
> can integrate. Three webhooks, three new pending leads, ready for
> the next cron tick. Same downstream pipeline as CSV upload — single
> Lead.status='pending' anchor.
>
> The CSV upload in the dashboard is the manual fallback for
> RevOps/Marketing batch imports."

---

## Architecture & rollout follow-on (4–6 min)

After the demo, screenshare:

1. **PART_A_Technical_Design.md §3 Architecture diagram** — explain the
   separated pipeline + dashboard + Postgres model and why FastAPI +
   GH Actions cron + Render/Vercel/Neon (1 min)

2. **PART_A §10 Scoring Rubric v2** — show the 55/30/15 weight split
   and call out the explicit shift from v1 (which over-weighted geography).
   Mention senior/commercial hard disqualifiers (1 min)

3. **PART_A §11 Hallucination defense (4 layers)** — walk through L1
   provenance → L2 prompt → L3 post-gen check → L4 UI source attribution
   (1 min)

4. **PART_B Phase 2 rollout** — explain how the dashboard's one-click
   approve directly powers the verification-burden KPI, and how the
   tier-based review depth (Hot 100% / Warm 50% / Cold 10%) maps to
   the inbox/card/table modes (1 min)

5. **`pytest tests/`** in terminal — 125 passing tests flash by.
   Mention the 9 golden cases that anchor the rubric (30s)

6. **Open `infra/.github/workflows/cron.yml`** — show the daily 9am UTC
   cron + secrets wiring. Mention deployment readiness without doing
   actual deploy (PDF doesn't require it) (30s)

---

## Closing — 30s

> "To summarize the take-home: the deliverable is a production-shaped
> MVP that takes lead inputs through 7 enrichment APIs, scores against
> EliseAI's actual ICP using NMHC + Wikipedia + News + Census + WalkScore +
> FRED, generates outreach emails grounded in source-attributed facts
> through a 4-layer hallucination defense, and ships a complete dashboard
> for the SDR feedback loop that powers the rollout plan's Phase 2.
>
> Code is in the repo, README has the setup. PART_A and PART_B are
> the design docs in both Chinese and English. Thanks for watching."

---

## Stretch material (only if running short on time)

- **Trigger run** button on /runs — kicks off pipeline live, shows the
  3-second polling auto-update as status flips from `running` to
  `success` / `partial`
- **Run detail page** — render the auto-generated MD report, show the
  per-API performance table (avg/p95/failures)
- **`/docs` Swagger UI** — quick flash of the 10 REST endpoints
  (uploads / webhooks / runs / leads / feedback / metrics)

---

## After recording

- [ ] Trim opening pause + closing dead air
- [ ] Add 2-second cuts between scenes (no slow fades)
- [ ] Speed up Scene 5 webhook script run if it dragged
- [ ] Volume-normalize voice
- [ ] Export 1080p 30fps, target 60-100 MB
- [ ] Upload to Loom or YouTube (unlisted) and paste link in submission
