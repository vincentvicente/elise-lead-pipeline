# Demo Script — EliseAI Lead Pipeline

A scripted walkthrough for the take-home demo video.
Total length: **~9 minutes** (within the 5–15 minute window the PDF allows).

---

## How this video covers the PDF deliverables

| PDF asks | Covered in |
|---|---|
| ① Which public APIs you used and why | **Intro** (0:00–0:30) |
| ② How your workflow enriches, scores, and outputs leads | **Scene 1, 2, 5** |
| ③ Any assumptions made and logic behind them | **Scene 2 + Walkthrough B** |
| ④ How your scoring/outreach helps a sales rep | **Scene 2 + Scene 3** |
| ⑤ Project plan and rollout process | **Walkthrough D** |

---

## Pre-record state on the dashboard

Run `uv run python -m scripts.seed_demo` first. Then verify:

```
Overview KPIs:
  • Processed today:    8 leads
  • Hot tier %:         37.5 %
  • Approval rate:      50.0 %
  • Avg review time:    0.9 min

Tier today:  3 Hot · 2 Warm · 3 Cold
Pending:     3   ← will grow to 6 in Scene 5

Inbox (sorted by score):
  92 Hot   Sarah Johnson    @ Greystar              ★ main demo lead
  88 Hot   Jamie Chen       @ AvalonBay Communities
  84 Hot   Mike Lee         @ Asset Living
  68 Warm  Pat Riley        @ Bozzuto Group
  64 Warm  Taylor Smith     @ Cardinal Group
  42 Cold  Casey Brown      @ Desert Properties
  38 Cold  Robin Park       @ Park Apartments LLC
  35 Cold  Jordan Cole      @ Unknown Operator Co   ⚠ template_fallback (failure mode)
```

---

## Pre-record checklist (5 minutes before recording)

- [ ] Browser at `http://localhost:5173/` zoomed to **110–125%**, hard-refresh `Cmd+Shift+R`
- [ ] Backend running (curl `http://localhost:8000/healthz` → `{"status":"ok"}`)
- [ ] Frontend dev server running
- [ ] Three Chrome tabs prepared in **incognito**:
  - Tab 1: dashboard `localhost:5173/`
  - Tab 2: Swagger `localhost:8000/docs` (optional)
  - Tab 3: GitHub `https://github.com/vincentvicente/elise-lead-pipeline`
- [ ] Terminal Tab C pre-positioned at `cd "/Users/vicentezhu/Desktop/EliseAI task/backend"`
- [ ] macOS: Do Not Disturb ON · Dock auto-hidden · Slack/WeChat/Mail closed
- [ ] DEMO_SCRIPT.md open on second monitor or phone
- [ ] Loom Business · Full Screen mode · mic level mid-range

---

# 🎬 Recording starts here

---

## Intro · Project + APIs (30s) — covers PDF ①

**Action**
- Sit on the Overview page (you haven't shown anything yet)
- Don't click anything — just speak

**Voiceover (~70 words, slow + clear)**
> "Hi, I'm Vincent. This is my take-home for the EliseAI GTM Engineer
> role.
>
> The tool takes a raw inbound lead — just name, email, company, and
> property address — and produces a scored, ready-to-send outreach
> email.
>
> It uses **seven public APIs**: Census Geocoder and Census ACS for
> demographics, NewsAPI for company news, Wikipedia for company
> background, WalkScore for property walkability, FRED for rental
> market signals, and a local NMHC Top 50 list — that's the official
> ranking of the largest US apartment operators, where most of EliseAI's
> existing customers come from.
>
> Plus Claude for the email writing.
>
> Let me show you the dashboard first, then walk through how it works."

> 💡 **Why these APIs**: each one was picked for a specific scoring
> dimension. Census + WalkScore answer "is this a good market?" NewsAPI
> + Wikipedia + NMHC answer "is this a good company?" FRED answers
> "how tight is the rental market right now?"
> All free or free-tier. Total cost per lead ~$0.015 (Claude).

---

## Scene 1 · Overview dashboard (20s) — covers PDF ②

**Action**
1. You're already on the Overview page
2. Slowly point at the four KPI cards
3. Drift cursor down to the **Today's pipeline** card

**Voiceover (~50 words)**
> "Top of the dashboard: today's KPIs.
>
> 8 leads processed. About 37% scored as Hot tier. Approval rate from
> the SDR team is 50%. Average review time is under one minute.
>
> Below that — today's split: 3 Hot, 2 Warm, 3 Cold. Plus 3 leads
> still waiting to be processed.
>
> The 7-day trend and tier donut are below."

---

## Scene 2 · Hot lead detail (90s) — covers PDF ②③④

**Action**
1. Click **Inbox** in sidebar
2. Pause — point at the score-sorted list (Sarah Johnson at top, score 92, Hot badge)
3. Click **Sarah Johnson**
4. Read the 4 insight bullets at the top
5. Click to expand the **score breakdown** collapse
6. Hover *Company Scale 25/25* and *Buy Intent 20/20*
7. Read 2–3 lines of the email body out loud
8. Scroll down, click to expand **Source attribution**
9. Hover one green confidence badge (≥ 0.85), one amber (< 0.85)

**Voiceover (~150 words, two paragraphs — pause between them)**
> "Inbox sorts leads by score. Sarah Johnson at Greystar is at the top.
> 92 out of 100, Hot tier.
>
> The four insights at the top tell the SDR what matters: Greystar is
> the number-one operator on the NMHC Top 50, with 800,000 units
> managed. There's a recent acquisition in the news. The property is
> in a high-renter-density market. And the email is from a corporate
> domain that matches the company.
>
> The score breakdown shows where the 92 points came from — six
> dimensions across company, geography, and contact.
>
> Now — **the assumption behind this rubric**: 55 of the 100 points
> go to company signals — scale, buy intent, and vertical fit. Only
> 30 points to geography. The first version of this rubric weighted
> geography too heavily. A small operator with a Manhattan property
> would land Hot just because Manhattan. The fix: company strength
> dominates. Sarah scores 92 because Greystar is huge and active,
> not because Austin is hot.
>
> Then the email itself. Every fact has a source and a confidence
> score. Green badges at 0.95 mean 'safe to cite specific numbers.'
> Amber badges below 0.85 mean 'mention the topic, but not the
> figure.' The green banner above the email confirms the
> hallucination check passed before the SDR ever saw it.
>
> **What this saves the SDR**: a manual research pass like this is
> typically 15 to 30 minutes per lead. The tool does it in 30 seconds."

---

## Scene 3 · One-click feedback loop (30s) — covers PDF ④

**Action**
1. In Sarah's email body, lightly edit one phrase — e.g. add or change a word
2. Note the button changes from "Approve" to **Save & Approve**, plus a new **View Changes** button
3. Click **View Changes** → diff modal opens
4. Pause 2 seconds on the red/green diff
5. Close modal
6. Click **Save & Approve** → green confirmation
7. Scroll down to Feedback history — new row appears with action `edited`

**Voiceover (~50 words)**
> "When the SDR edits the email, the tool captures both versions —
> original and final — plus the diff and how long the review took.
>
> Two reasons this matters. One: every edit becomes data we use to
> improve the prompt. Two: review time tells us whether we're
> actually saving the SDR time, not just shifting work."

---

## Scene 4 · Failure case: template fallback (45s) — covers PDF ②③

**Action**
1. Click **Leads** in sidebar (or scroll down in Inbox)
2. Click **Jordan Cole @ Unknown Operator Co** (score 35, the bottom of the list)
3. Point at the source label below "Email draft": **`template_fallback`**
4. Point at the amber **Generation trail** panel — read 2–3 lines aloud
5. Show the email body — it still has the right substitutions

**Voiceover (~80 words)**
> "Now the failure case. Jordan Cole hit the worst path.
>
> The yellow box shows exactly what happened: NewsAPI hit its 429
> rate limit. Then Claude Sonnet was rate-limited twice. Then Haiku
> failed twice with 503. The whole LLM fallback chain was exhausted.
>
> So the system fell back to a deterministic template. The SDR still
> gets a usable email — it has the company name, the city, our
> NMHC reference. Nothing got dropped. The SDR isn't blocked. And
> the alert system fired so we know to investigate.
>
> **The assumption here**: any one piece of the pipeline can fail,
> but the SDR should never get nothing. Four-layer fallback is how
> we hold that promise."

---

## Scene 5 · Production input: webhook simulator (45s) — covers PDF ②

**Action**
1. Switch to terminal Tab C (already at `backend/`)
2. Paste and run:
   ```bash
   uv run python -m scripts.simulate_crm_webhook
   ```
3. Watch output — three webhooks fire, source labels visible
4. Switch back to dashboard
5. Click **Leads** → filter by **status = pending**
6. Notice count went from 3 to 6 — the new rows are **Marcus Tate, Priya Desai, Devin Park**

**Voiceover (~80 words)**
> "In production, leads don't come from CSV uploads — they come from
> the CRM. When someone fills out a form on the EliseAI site,
> Salesforce or HubSpot fires a webhook to our tool.
>
> Here's a script that mimics three CRMs — Salesforce, HubSpot, and
> Zapier — sending us inbound leads.
>
> Three webhooks fire. Three new pending leads. Same downstream
> pipeline as the CSV upload. The CSV is just the manual fallback for
> RevOps batch imports.
>
> The takeaway: this tool drops into any sales stack that fires
> webhooks. Salesforce, HubSpot, Zapier, even raw form submissions."

---

# 🛠 Architecture & rollout walkthrough (~4 min)

After Scene 5, switch to a wider explanatory mode. Open the relevant docs in tabs as you talk.

---

## A. Architecture (1 min) — covers PDF ②

Open `PART_A_Technical_Design.md` § 3 in a tab. Show the architecture diagram.

**Voiceover (~110 words)**
> "The architecture has two halves that share a single Postgres
> database.
>
> On one side, a daily cron runs in GitHub Actions — pulls new pending
> leads, runs them through the pipeline, writes the results back. On
> the other side, a FastAPI backend with a React dashboard, deployed
> on Render and Vercel. They share the same Neon Postgres. Resend
> handles outbound alerts when something fails.
>
> Two notes on this deployment.
>
> One — for the take-home demo I used Render, Vercel, and Neon free
> tiers. Total cost is about one dollar per batch of 50 leads. For
> actual EliseAI production, the same code drops onto AWS inside
> your VPC: change the database URL to RDS, swap GitHub Actions for
> EventBridge, point the React build at S3 plus CloudFront. The
> architecture is portable; nothing about the tool is locked to a
> specific cloud.
>
> Two — only DevOps touches any of this. SDRs just open a browser URL.
> Their daily experience is the dashboard you saw earlier — no
> terminal, no setup, no deploy. The complexity stays on the
> engineering side."

---

## B. Scoring rubric + assumptions (1 min) — covers PDF ③④

Scroll to PART_A § 10.

**Voiceover**
> "The scoring is a six-dimension rubric, 100 points total, weighted
> 55-30-15.
>
> Company-side gets 55 points: 25 for company scale — that's the NMHC
> ranking — 20 for buy intent from news, and 10 for vertical fit.
> Geography gets 30 points: market fit, property fit, market dynamics.
> Contact-side gets 15 points: corporate domain, domain matches
> company name, and email prefix shape.
>
> **Three assumptions baked into this**:
>
> One — multifamily housing is EliseAI's core market. So if the
> company name has 'senior living' or 'commercial real estate' in it,
> we score it as Cold automatically. Out of scope.
>
> Two — EliseAI serves the US and Canada. Anywhere else gets capped at
> Cold tier with a 'manual review' note.
>
> Three — when an API fails to return data, we use the median score
> for that dimension instead of zero. We don't penalize a great lead
> just because the Census API timed out.
>
> Nine golden test cases verify the rubric — every tier-ordering
> decision is anchored to a specific test case."

---

## C. Hallucination defense (1 min) — covers PDF ②③

Scroll to PART_A § 11.

**Voiceover**
> "LLM hallucination is the highest risk in any sales-email AI tool.
> Inventing a customer name or a fake statistic is a brand incident.
>
> The defense is four layers.
>
> Layer one: every fact passed to the prompt has a source and a
> confidence score in the database — that's the provenance table.
>
> Layer two: the system prompt tells the model to cite specific
> numbers only when the fact's confidence is above 0.85.
>
> Layer three: after the LLM responds, a post-generation check
> verifies every number and every named entity in the draft against
> the verified-facts list. Anything unverified triggers a
> regeneration, up to two retries.
>
> Layer four: the dashboard shows the SDR which fact came from where,
> so they can self-verify before approving.
>
> If all of that fails — like in Jordan Cole's case — the system falls
> through to a deterministic template instead of shipping garbage."

---

## D. Rollout plan (1 min) — covers PDF ⑤

Open `ROLLOUT_PLAN.md` § 2.

**Voiceover**
> "The rollout plan is five phases over eight weeks.
>
> Phase 0, week zero, is one week of infra prep: provision Neon,
> deploy backend and frontend, configure secrets.
>
> Phase 1, week one, runs the rubric on 30 to 50 historical closed
> deals to baseline how well the scoring agrees with real outcomes.
>
> Phase 2, weeks two and three, is co-pilot mode — one or two SDR
> Champions review **100% of every email**, no sampling. Every edit
> they make becomes data to improve the prompt.
>
> Phase 3, weeks four to six, expands to the full SDR team using a
> one-click approve interface, still 100% review. Plus a 20% control
> group to measure lift versus human-only emails.
>
> Phase 4, weeks seven and eight, is the Go/No-Go decision plus
> Salesforce and Outreach integration.
>
> **Important assumption**: tier-based review sampling — letting SDRs
> skip Cold tier emails — is held back until after launch is stable
> for at least four weeks. The AI has to earn that trust through
> data, not by fiat in a process document."

---

## E. Tests + repo (30s)

Switch to a terminal, paste:
```bash
cd "/Users/vicentezhu/Desktop/EliseAI task/backend" && uv run pytest 2>&1 | tail -1
```

Show: `============================= 129 passed in 3.17s ==============================`

**Voiceover**
> "129 backend tests, all passing. Including 9 golden cases that
> anchor the scoring rubric — every tier decision is validated
> against a hand-crafted lead."

Switch to GitHub tab — show the repo at `vincentvicente/elise-lead-pipeline`.

---

## Closing (30s)

Voiceover, on the GitHub README:
> "To wrap up.
>
> The deliverable is a production-shaped MVP: it takes raw inbound
> leads through 7 public APIs, scores them on EliseAI's actual ICP,
> and drafts outreach emails grounded in source-attributed facts —
> with a four-layer guard against hallucination.
>
> The dashboard captures the SDR feedback loop that powers Phase 2 of
> the rollout plan.
>
> Code, tests, and design docs are all in the repo.
>
> Thanks for watching."

Stop recording.

---

## Total time budget

| Section | Target |
|---|---|
| Intro (APIs + why) | 30s |
| Scene 1 — Overview | 20s |
| Scene 2 — Hot lead detail | 90s |
| Scene 3 — Feedback loop | 30s |
| Scene 4 — Template fallback | 45s |
| Scene 5 — Webhook entry | 45s |
| **Demo total** | **4 min 20s** |
| Walkthrough A — Architecture (incl. demo-vs-production note) | 75s |
| Walkthrough B — Scoring + assumptions | 60s |
| Walkthrough C — Hallucination defense | 60s |
| Walkthrough D — Rollout plan | 60s |
| Walkthrough E — Tests + repo | 30s |
| Closing | 30s |
| **Video total** | **~9 min 15s** |

---

## Pronunciation tips for tricky words

| Word | How to say it |
|---|---|
| EliseAI | "uh-LEES AI" (like "police" without the P) |
| NMHC | "N-M-H-C" (spell out each letter) |
| Greystar | "GRAY-star" |
| AvalonBay | "AV-uh-lon BAY" |
| Bozzuto | "bo-ZOO-toe" |
| Resend | "RE-send" (not "ree-send") |
| Render / Vercel | "REN-der" / "ver-SELL" |
| Anthropic | "an-THROP-ic" |
| Sonnet | "SON-it" (rhymes with "bonnet") |
| Haiku | "HIGH-koo" |

---

## Common pitfalls during recording

| Pitfall | Fix |
|---|---|
| Pending count shows wrong number | Run the full reset (Stop uvicorn → `rm -f elise.db && alembic upgrade && seed_demo` → restart uvicorn → `Cmd+Shift+R` browser) |
| Email source shows wrong value | Re-seed; Jordan Cole is the only `template_fallback` lead |
| Webhook simulator says "Connection refused" | Backend isn't running |
| Diff modal shows nothing | You didn't actually edit the email — change at least one character |
| KPIs all show zero | DB was reset but seed didn't run |
| Notification or app icon appears in recording | Re-record from that scene; full DND mode and quit the offending app |

---

## Post-recording

- [ ] Trim opening dead air (first 1–2 s) and closing dead air
- [ ] Add chapter markers (Loom Business does this automatically from voiceover)
- [ ] Auto-generated captions ON (proofread the term "EliseAI")
- [ ] Set sharing → Anyone with the link can view
- [ ] Title: `EliseAI GTM Engineer Take-Home — Inbound Lead Pipeline Demo`
- [ ] Description: paste chapters + repo link
- [ ] Copy share link, paste into submission email
