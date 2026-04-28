# Demo Script — EliseAI Lead Pipeline

A scripted walkthrough tied to the actual seed data on screen. The demo
runs **~4 minutes**, followed by a **3–5 minute architecture & rollout
walkthrough**, landing inside the 5–15 minute window the take-home PDF
allows.

> Every name, number, and click in this script matches what you'll see
> on `http://localhost:5173/` after running `uv run python -m scripts.seed_demo`.

---

## Pre-record state on the dashboard

The seed produces this exact state — verify with a glance before recording:

```
Overview KPIs:
  • Processed today:    8 leads
  • Hot tier %:         37.5 %
  • Approval rate:      50.0 %
  • Avg review time:    0.9 min

Today's pipeline tile:
  • Processed: 8  (3 Hot · 2 Warm · 3 Cold)
  • Pending review: 3
  • Last run health: 8/8 (clean)

Tier donut today:  3 Hot / 2 Warm / 3 Cold
Recent runs:
  • success 8/8 · ~3 hours ago
  • partial 8/10 · 1 day ago

Inbox (sorted by score):
  92 Hot   Sarah Johnson    @ Greystar              ★ main demo lead
  88 Hot   Jamie Chen       @ AvalonBay Communities
  84 Hot   Mike Lee         @ Asset Living
  68 Warm  Pat Riley        @ Bozzuto Group
  64 Warm  Taylor Smith     @ Cardinal Group
  42 Cold  Casey Brown      @ Desert Properties
  38 Cold  Robin Park       @ Park Apartments LLC
  35 Cold  Jordan Cole      @ Unknown Operator Co   ⚠ template_fallback (failure mode)

Pending (3):
  • Alex Rivera   @ Morgan Properties
  • Sam Wong      @ Equity Residential
  • Drew Patel    @ Willow Bridge Property Company
```

---

## Pre-record checklist (5 minutes before recording)

- [ ] Browser at `http://localhost:5173/` zoomed to **110–125%**, hard-refresh with `Cmd+Shift+R`
- [ ] Backend running (`http://localhost:8000/healthz` returns `{"status":"ok"}`)
- [ ] Frontend dev server running (you see the dashboard)
- [ ] Three Chrome tabs prepared in **incognito**:
  - Tab 1: dashboard `localhost:5173/`
  - Tab 2: Swagger `localhost:8000/docs`
  - Tab 3: GitHub `https://github.com/vincentvicente/elise-lead-pipeline`
- [ ] Terminal third-tab pre-positioned with `cd backend` ready, command staged but not executed:
  - `uv run python -m scripts.simulate_crm_webhook`
- [ ] macOS: Do Not Disturb ON · Dock auto-hidden · Slack/WeChat/Mail closed
- [ ] DEMO_SCRIPT.md open on second monitor or phone for cuing
- [ ] Loom Business plan active (5-min limit removed) — recording mode set to **Full Screen**
- [ ] Mic test: say "EliseAI Lead Pipeline Demo" — input meter shows mid-range

---

## Scene 1 · Overview dashboard (30s)

**Action**
1. Land on `localhost:5173/` (Overview is the default route)
2. Pause 1 second on the KPI row — let the four numbers register
3. Drift the cursor down to the **Today's pipeline** card

**Voiceover (~50 words)**
> "This is the dashboard for an inbound lead pipeline I built for the
> EliseAI GTM Engineer take-home. Today's KPIs at the top: 8 leads
> processed, 37.5% Hot tier, 50% approval rate from the SDR team,
> average review time under one minute. The strip below shows today's
> tier breakdown — 3 Hot, 2 Warm, 3 Cold — plus 3 leads still pending
> review. The 7-day trend and tier donut are below."

**Visual targets confirmed**
- KPI numbers visible and readable
- "Today's pipeline" tile shows 3 Hot · 2 Warm · 3 Cold
- Tier donut on right shows the same 3/2/3 split

---

## Scene 2 · Inbox + Sarah Johnson detail (90s)

**Action**
1. Click **Inbox** in the sidebar
2. Pause on the left panel — note the leads are sorted by score, Sarah Johnson at the top with a Hot badge and 92
3. Click **Sarah Johnson** row
4. Right pane: scan the 4 insight bullets at the top
5. Click to expand the **score breakdown** collapse
6. Point cursor at *Company Scale 25/25*, then *Buy Intent 20/20*
7. Read 2–3 lines of the email body (out loud)
8. Click to expand **Source attribution** at the bottom
9. Hover a green confidence badge (≥ 0.85) and an amber one (< 0.85)

**Voiceover (~140 words)**
> "Inbox sorts leads by score so Hot leads surface first. Sarah Johnson
> at Greystar — 92 out of 100. The four insights up top: NMHC number-one
> operator, recent acquisition news, high renter density market, and
> matching corporate-domain email.
>
> The score breakdown shows where the points came from across six
> dimensions. Sarah maxes out Company Scale and Buy Intent — that's the
> NMHC ranking plus the M&A news combined. Geography contributes the
> rest, but it's not what tipped her into Hot.
>
> The email itself is grounded in verified facts only. Each fact has a
> source and a confidence — green badges at 0.95 are citable specific
> numbers, amber ones can be referenced as a topic but not as a figure.
> The green banner at the top confirms the post-generation hallucination
> check passed before the draft reached the SDR."

**Visual targets confirmed**
- Sarah at the top of the Inbox list
- Score 92 / Hot badge visible
- "Hallucination check passed" green banner visible above the email
- Source attribution panel shows confidence numbers (0.95, 0.85, etc.)

---

## Scene 3 · One-click feedback loop (30s)

**Action**
1. In Sarah's email body, lightly edit one phrase — e.g. add a word
2. Note the button changes from "Approve" to **Save & Approve**, and a new **View Changes** button appears
3. Click **View Changes** → diff modal opens
4. Pause 2 seconds on the red/green diff
5. Close the modal
6. Click **Save & Approve** → green confirmation appears
7. Scroll down to the Feedback history list — new row appears with action `edited`

**Voiceover (~50 words)**
> "When the SDR makes any edit, the workflow captures both the original
> and the final draft, computes the diff, and stores both. The review
> timer measures verification burden — the rollout-plan KPI we want
> below 2 minutes per email. Phase 2 of the rollout runs entirely on
> this feedback data."

**Visual targets confirmed**
- Diff modal shows side-by-side red/green
- Feedback history shows the new `edited` row at the top

---

## Scene 4 · Failure path: template fallback (45s)

**Action**
1. Click **Leads** in the sidebar (or scroll the inbox down)
2. Filter by **tier = Cold** if convenient
3. Click **Jordan Cole @ Unknown Operator Co** (score 35 — at the bottom)
4. In the email pane, point at the source label below "Email draft": **`template_fallback`**
5. Read the warnings — "LLM unavailable — used deterministic template"
6. Note the email body still has the right substitutions (company name, city, NMHC reference)

**Voiceover (~80 words)**
> "Now the failure case. Jordan Cole hit the cold path: NewsAPI quota
> was exhausted, then Claude Sonnet was rate-limited, then the Haiku
> fallback also failed. The pipeline still produced a usable email,
> but from a deterministic template instead of an LLM.
>
> The SDR sees exactly that — the source label says `template_fallback`,
> and the warning explains why. Nothing got dropped, the SDR isn't
> blocked, and the alert system fired the Resend email so we know to
> investigate. This is what 4-layer fallback looks like in practice."

**Visual targets confirmed**
- Jordan Cole shows score 35, Cold tier
- Email source displays exactly `template_fallback`
- Warning shows "LLM unavailable — used deterministic template"

---

## Scene 5 · Production entry point: webhook simulator (45s)

**Action**
1. Switch to your terminal (third tab, already cd'd into `backend/`)
2. Run:
   ```bash
   uv run python -m scripts.simulate_crm_webhook
   ```
3. Watch the output — three webhooks fire, output shows source labels (Salesforce / HubSpot / Zapier) and lead_ids
4. Switch back to dashboard browser tab
5. Click **Leads** → filter by **status = pending**
6. Notice the count went from 3 to 6 — the three new rows are **Marcus Tate, Priya Desai, Devin Park**
7. Hover one row briefly to highlight it

**Voiceover (~80 words)**
> "Production input is a webhook, not the CSV upload. Here's a script
> that mimics three CRMs — Salesforce, HubSpot, and Zapier — POSTing
> inbound leads to our public webhook endpoint. The endpoint is generic,
> so any system that fires webhooks can integrate.
>
> Three webhooks, three new pending leads. Same downstream pipeline as
> CSV upload — single `Lead.status='pending'` anchor. The CSV upload in
> the dashboard is the manual fallback for batch imports by RevOps."

**Visual targets confirmed**
- Terminal shows 3× `→ 202 lead_id=...`
- Pending leads page shows total = 6 (was 3)
- New names visible: Marcus Tate, Priya Desai, Devin Park

---

## Architecture & rollout walkthrough (~4 minutes)

After Scene 5, switch to a wider explanatory mode. Open the relevant docs in tabs as you talk:

### A. Architecture (1 min)

Open `PART_A_Technical_Design.md` § 3 in a new tab. Show the architecture diagram. Hit:

> "Pipeline and dashboard are deliberately separated. Cron runs in
> GitHub Actions, writes to Postgres on Neon. FastAPI serves the
> dashboard, React frontend on Vercel. They share the same Postgres
> as the single source of truth. Resend handles outbound alerts.
> The whole thing runs in production on free tiers — total cost
> under one dollar for the take-home scale of 50 leads per batch."

### B. Scoring rubric (1 min)

Scroll to PART_A § 10:

> "The scoring is a 6-dimension rubric, 100 points total, split
> 55-30-15 between company-side, geography, and contact-side. The
> v1 design over-weighted geography — a Manhattan property at an
> unknown company would land Hot just because Manhattan. The v2
> rubric I shipped flips that: a NMHC top-10 operator in a rural
> market still tiers Hot, because company strength dominates."

### C. Hallucination defense (1 min)

PART_A § 11:

> "LLM hallucination is the highest risk in any sales-email AI tool.
> The defense is four layers. Layer 1: every fact passed to the prompt
> has a source and confidence in the database. Layer 2: the prompt
> tells the model to cite specific numbers only above 0.85 confidence.
> Layer 3: a post-generation check verifies every number and named
> entity in the draft against the verified-facts list — anything
> unverified triggers regeneration. Layer 4: the dashboard shows the
> SDR which fact came from where, so they can self-verify before
> approving."

### D. Rollout plan (1 min)

Open `ROLLOUT_PLAN.md` § 2:

> "The rollout is 5 phases over 8 weeks. Phase 0 is one week of infra
> prep. Phase 1 baselines on historical leads. Phase 2 is co-pilot —
> SDR Champions review 100% of every draft. Phase 3 expands to the
> full team with one-click approve UX, still 100% review, plus a 20%
> control group to measure lift. Phase 4 is the Go/No-Go decision and
> Salesforce-Outreach integration. Tier-based review sampling — letting
> SDRs skip Cold tier review — is held back to post-launch stable
> state. The AI has to earn that trust through accumulated data."

### E. Tests + repo (30s)

Switch to terminal, run:
```bash
cd backend && uv run pytest 2>&1 | tail -1
```
Show: `============================= 129 passed ... ==============================`

> "129 tests passing, including 9 golden cases that anchor the
> scoring rubric — every tier ordering decision the rubric makes
> is validated against a hand-crafted lead."

Open GitHub tab — show repo at `vincentvicente/elise-lead-pipeline`.

---

## Closing (30s)

Voiceover, on the GitHub README:
> "To summarize: the deliverable is a production-shaped MVP that takes
> raw inbound leads through 7 enrichment APIs, scores against EliseAI's
> actual ICP using NMHC and the multifamily dataset, generates outreach
> emails grounded in source-attributed facts through a 4-layer
> hallucination defense, and ships a complete dashboard for the SDR
> feedback loop that powers the rollout plan's Phase 2.
>
> Code, tests, and bilingual design docs are all in the repo. Thanks
> for watching."

Stop recording.

---

## Total time budget

| Section | Target |
|---|---|
| Scene 1 — Overview | 30s |
| Scene 2 — Hot lead detail | 90s |
| Scene 3 — Feedback loop | 30s |
| Scene 4 — Template fallback | 45s |
| Scene 5 — Webhook entry | 45s |
| **Demo total** | **4 min** |
| Architecture & rollout walkthrough | 4 min |
| Closing | 30s |
| **Video total** | **~8.5 min** |

---

## Common pitfalls during recording

| Pitfall | Fix |
|---|---|
| Email source shows wrong value (e.g. all `llm:claude-sonnet-4-6`) | Re-run `python -m scripts.seed_demo` — Jordan Cole is the only template_fallback lead |
| Webhook simulator says "Connection refused" | Backend isn't running — `uvicorn elise_leads.api.main:app --reload --port 8000` |
| Pending count doesn't change after webhook | Hard-refresh the browser (`Cmd+Shift+R`); TanStack Query auto-invalidates but cache may need clearing |
| Diff modal shows nothing | You didn't actually edit the email — change at least one character |
| KPIs all show zero | DB was reset but seed didn't run — `python -m scripts.seed_demo` |
| Notification or app icon appears in recording | Re-record from that scene; in future, full DND mode and quit the offending app |
| Tier donut shows different counts than 3/2/3 | A previous demo run added leads with `processed_at = today`. Re-seed to reset. |

---

## Post-recording

- [ ] Trim opening dead air (first 1–2 s) and closing dead air
- [ ] Add chapter markers (Loom Business does this automatically from voiceover)
- [ ] Auto-generated captions ON (proofread the term "EliseAI")
- [ ] Set sharing → Anyone with the link can view
- [ ] Title: `EliseAI GTM Engineer Take-Home — Inbound Lead Pipeline Demo`
- [ ] Description: paste chapters + repo link
- [ ] Copy share link, paste into submission email
