# Rollout Plan — EliseAI Inbound Lead Pipeline

How to test and roll out the lead-enrichment pipeline across the EliseAI sales organization.



---

## Philosophy

This plan inherits two principles from publicly-available playbooks that match EliseAI's stated culture and operating context:

- **"Start with Why."** From EliseAI's own *Education Team* blog post on change management: SDRs adopt new tools when they understand the *reason*, not the mechanics. Every phase below leads with the SDR-facing benefit, not the engineering accomplishment.
- **"Tool is 20% of the outcome. Training, ownership, segmentation, and ramp is 80%."** From the SaaStr playbook on AI-SDR rollouts. This document spends 80% of its weight on process — phasing, stakeholders, KPIs, training — not on the tool itself.

The pitfall to avoid (Apollo's *AI SDR Pilot Program* writeup):

> *"A pilot that saves prospecting time while adding hours of review has not demonstrated ROI."*

The mitigation runs through every section below as **verification burden** — measured directly by `feedback.review_seconds` in the database and held to a hard limit of **median < 2 minutes per email**.

---

## 1. Testing the MVP

The pipeline cannot be backtested against historical EliseAI data without access to it, so MVP validation is layered:

### Pre-pilot validation (engineering-side, complete in this repo)

| Method | What it verifies | Status |
|---|---|---|
| **Golden test cases** (9 hand-crafted leads) | Tier ordering matches business intuition: NMHC #1 operator → Hot, gmail-only contact at unknown company → Cold, senior-living vertical → Cold disqualifier, etc. | ✅ Passing in `tests/unit/test_rubric.py` |
| **Sensitivity analysis** | Weights ±20% don't flip more than 10% of tiers — i.e. the rubric is robust, not over-fit | ✅ Documented in PART_A §15 |
| **Distribution check** | Seed of 11 demo leads produces a roughly 30/40/30 Hot/Warm/Cold split (close to the 20/50/30 target) | ✅ Verified |
| **Hallucination detection** | Number-verification + entity-verification flag fabricated stats and customer names | ✅ 21 tests in `test_generation.py` |
| **Failure-mode coverage** | Each enricher can fail independently; the pipeline still produces a usable email via template fallback | ✅ Live demo with the seeded `Jordan Cole` lead |

### Pilot-phase validation (Phase 2, with real SDRs)

| Method | What it verifies | Owner |
|---|---|---|
| **Daily approve/edit/reject ratios** | The model's draft quality matches SDR expectations | SDR Champion |
| **Median `review_seconds`** | Verification burden stays under 2 minutes per email | RevOps |
| **Hallucination intercept rate** | Post-gen detector catches fabrications that slip past the prompt | GTM Engineer |
| **Edit-diff analysis** | What SDRs *change* in approved emails reveals systemic prompt gaps | GTM Engineer |
| **LLM I/O capture (JSONL per run)** | Every system prompt + user prompt + Claude response saved to `backend/data/runs/<run_id>/llm_io.jsonl` for post-hoc hallucination audit, prompt regression, and edit-diff vs. original-prompt analysis | GTM Engineer |

### Production validation (Phase 3, vs. control)

| Method | What it verifies | Hold a control |
|---|---|---|
| **Reply rate vs. control** | AI-drafted emails don't underperform human-written | 20% control group |
| **Meetings booked / 100 contacts** | The funnel moves leads forward at least as effectively | Same |
| **SQL conversion parity** | Lead quality from AI-tier ≥ control | Salesforce report, weekly |
| **Cost per meeting** | API + LLM spend / meetings booked is decreasing | RevOps weekly review |

---

## 2. Rollout Process

A five-phase rollout adapted from Apollo's published *AI SDR pilot program* framework, with EliseAI-specific adjustments. Every phase has an explicit **exit gate**: the next phase doesn't start until the gate is met.

| Phase | Duration | Core actions | Exit gate |
|---|---|---|---|
| **Phase 0 — Infra Readiness** | Week 0 | Provision Neon Postgres; deploy backend to Render and frontend to Vercel; verify Resend domain authentication; configure GitHub Actions secrets; import the NMHC Top 50 list; load 30–50 historical closed leads as seed data | Dashboard reachable · cron runs end-to-end once · alert email confirmed delivered |
| **Phase 1 — Readiness** | Week 1 | Email-auth check (SPF/DKIM/DMARC); lock one ICP segment for the pilot (recommended: new inbound leads matching existing NMHC Top 50 customer profiles); run the rubric on 30–50 historical closed-won/closed-lost leads to baseline tier-vs-outcome correlation; **explicitly verify Company-side dimensions (55 pts max — NMHC + Wikipedia + News + Vertical Fit) actually drive Hot tier classification on the baseline cohort, not Geography (30 pts max). If Hot leads in the baseline are dominated by Census/WalkScore signals, recalibrate weights before pilot.** | Named RevOps Engineer in place · scoring distribution within ~20/50/30 of the historical cohort · Company-side dimensions confirmed as primary Hot-tier driver |
| **Phase 2 — Co-pilot (full review across all tiers)** | Week 2–3 | Pilot SDR (1–2 Champions) reviews **100% of every AI-drafted email — Hot, Warm, and Cold alike — no tier-based sampling yet**; the AI hasn't earned that trust. Use the dashboard's Inbox mode for thorough review; daily standup on approve/edit/reject ratio; **every edit-diff and rejection reason persisted to JSONL** to drive prompt iteration; **`feedback.review_seconds` monitored in real time** | Brand/compliance approval rate ≥ 95% **AND** median review time < 2 minutes per email · ≥ 4 weeks of edit-diff data captured for prompt regression |
| **Phase 3 — Measured Autonomy with one-click UX** | Week 4–6 | Expand to the full SDR team. **Reviews remain 100% across all tiers**, but the dashboard's **one-click approve / edit / reject** workflow makes each review fast (target < 30s for clean Hot leads). Split traffic for measurement: **80% AI-drafted, 20% control (human-only, no AI assist)**; measure reply rate / meetings booked / SQL conversion lift via `/metrics/overview`; **all edit-diffs and rejection reasons feed weekly prompt-iteration cycles**; weekly review with Sales Leadership | AI cohort meetings/100 contacts ≥ control · No governance incidents (brand/legal) · Approval-rate and hallucination-intercept KPIs holding stable for 4+ consecutive weeks |
| **Phase 4 — Scale Decision** | Week 7–8 | Sales Leadership + RevOps Go/No-Go; integrate with **Salesforce** (write enriched fields and scores back to Lead object) and **Outreach** (auto-enroll approved emails into sequences by tier); run full-team training; **retain CSV upload as the RevOps batch-ingestion path** for one-off historical imports; webhook becomes the primary realtime entry point | Leadership approves general availability · 100% of SDR team has completed training · Phase-3 metrics held for two consecutive weeks |

After Phase 4, the system enters **stable operation** with quarterly retrospectives — the first one at Week 13, where the scoring rubric is recalibrated against the closed-won cohort accumulated since launch.

### Pipeline state preservation across phases

Partial-success recovery is built into the system so a Phase 1 → Phase 2 transition (or any cron failure mid-run) doesn't cost work or data:

- **Per-lead atomic commits.** Each lead's `enriched_data`, `provenance`, `score`, and `email` rows are written transactionally. A mid-pipeline failure leaves earlier leads safely processed; the next cron run resumes from the next `status='pending'` row, no reprocessing of completed leads.
- **Per-run JSONL exports.** Every run also dumps to `backend/data/runs/<run_id>/`:
  `enrichment.jsonl` (raw API responses), `scoring.jsonl` (intermediate dimension scores), `llm_io.jsonl` (every Claude prompt + response pair), and `feedback_diffs.jsonl` (SDR edits). These files are the audit trail for hallucination forensics and prompt-regression testing.
- **Three-layer retry.** API-call layer (3× exponential backoff with jitter for 5xx / timeout); lead layer (skip-and-continue on uncaught exception, mark `status='failed'` with `error_message`); pipeline layer (immediate Resend alert on top-level crash, GitHub Actions auto-retries the workflow on its next scheduled tick).

If the pilot needs to re-baseline (e.g. weights are recalibrated after Phase 1), the JSONL exports allow re-running scoring offline against the same enrichment payload — no re-fetching of upstream APIs needed.

### Post-Phase 4 sampling considerations (stable-state only)

Tier-based review sampling is **deliberately not introduced before Phase 4**. The AI must earn the trust to skip Cold-tier review through accumulated data, not by fiat in a process document. Once the system has run in stable production for at least **4 weeks post-GA** with the following thresholds holding steady:

- Approval rate ≥ 95%
- Hallucination intercept rate < 5%
- No governance incidents (brand / legal)
- Edit-rate on Cold-tier drafts < 20%

…the org may consider introducing the following sampling pattern, lowest-risk tier first:

| Tier | Phased introduction | Dashboard UX |
|---|---|---|
| **Cold** (<55) | Introduce first (post-Phase-4 + 4 weeks). Sample 10% for review; route the rest through a templated nurture sequence | Bulk operations via Table mode |
| **Warm** (55–74) | Only after Cold sampling has held for another 4 weeks with no quality regression. Begin at 80% review, taper to 50% | Card mode, fast triage |
| **Hot** (≥75) | **Always 100% review** — these are the leads the company most wants converted; the marginal value of SDR judgment is highest here | Inbox mode, sorted by score |

The principle: review effort eventually scales with lead value, but the savings happen *after* trust is established, not as a starting condition.

---

## 3. Timelines

```
Week 0   │ Phase 0: Infra Setup
Week 1   │ Phase 1: Readiness (RevOps owner + baseline)
Week 2–3 │ Phase 2: Co-pilot (Champion 100% review, real-time KPI monitoring)
Week 4–6 │ Phase 3: Measured Autonomy (full team + 20% control split)
Week 7–8 │ Phase 4: Scale Decision (Go/No-Go + Salesforce/Outreach integration)
Week 9+  │ Stable operation, continuous dashboard monitoring
Week 13  │ First quarterly retrospective; rubric recalibration from closed-won cohort
```

**Total time to general availability: 8 weeks.** This pacing is deliberately conservative — the Apollo and Qualified playbooks both observe that AI-SDR rollouts that compress this to 3–4 weeks tend to produce job-security anxiety on the SDR team and miss the calibration data needed for prompt iteration.

---

## 4. Stakeholders

A single **first-90-day owner** runs point on the rollout: the **RevOps Engineer**. This pattern, called out by Landbase's *Outbound Operations Playbook*, prevents the common failure mode where a multi-stakeholder rollout has no one to make a decision when the data is ambiguous.

| Stakeholder | Role | Responsibility | Active phases |
|---|---|---|---|
| **RevOps Engineer** | Named owner, first 90 days | Salesforce/Outreach integration; data integrity; exception handling; weekly KPI review with Sales Leadership; consume dashboard metrics | All 90 days |
| **Sales Leadership** (VP Sales) | Decision-maker | ICP calibration; scoring weight approval; Phase 4 Go/No-Go; resource sign-off | Phase 0, 1, 4 |
| **SDR Champion** (1–2 early adopters) | Frontline pilot | Daily use; high-frequency feedback on prompt and scoring; peer influence during Phase 4 rollout | Phase 1–4 |
| **GTM Engineer** (this tool's maintainer) | Technical lead | Pipeline maintenance; prompt iteration; scoring tuning; respond to hallucination-check anomalies; investigate alert pages | Throughout |
| **SDR Team** (full) | End users | Daily dashboard use from Phase 4 onward | Phase 4+ |
| **IT / Security** | Infra approval | API key management; PII compliance review; Resend domain verification | Phase 0 |
| **Legal / Compliance** | Risk approval | CAN-SPAM compliance review; AI-generated content disclosure policy | Phase 1, 3 |
| **Marketing Ops** | Lead source coordination | Lead-source attribution; cross-team ICP alignment; CSV upload coordination during Phase 0–2 | Phase 2+ |

---

## 5. Success Metrics

### Core lift (vs. control group, measured during Phase 3)

| Metric | Target | Source |
|---|---|---|
| Positive reply rate | AI cohort ≥ control (non-regression is the floor) | Outreach reply tracking |
| Meetings booked per 100 contacts | AI cohort ≥ control + 10% | Salesforce reports |
| SQL conversion rate | AI cohort ≥ control (parity required to ship) | Salesforce reports |

### Operational efficiency

| Metric | Target | Source |
|---|---|---|
| Message approval rate | ≥ 95% by end of Phase 2 | `feedback.action='approved'` ratio |
| **Verification burden** | **Median < 2 min/email** — the single most important KPI | `feedback.review_seconds` directly |
| Cost per meeting | -20% vs. baseline | (API + LLM cost) / meetings booked |
| Governance incidents | ≤ 1 per month | Manual report from SDR Champion + Legal |
| Hallucination intercept rate | < 5% (i.e. fewer than 5% of drafts trigger a regeneration) | `email.hallucination_check.passed = false` ratio |

### Adoption (Phase 4 onward)

| Metric | Target | Source |
|---|---|---|
| Daily active SDR usage | ≥ 90% of team using dashboard daily by Week 9 | Dashboard auth logs (post-auth integration) |
| Email source distribution | ≥ 95% LLM-source (rest is template fallback) | `email.source` distribution |
| Time-to-first-touch | ≤ 24h for Hot tier, ≤ 7d for Warm | `feedback.created_at - lead.uploaded_at` |

---

## 6. Risks and Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| **LLM hallucination** (fabricated customer names or stats) | Brand incident, legal exposure | 4-layer defense: per-fact provenance with confidence scores, prompt-level grounding rules, post-generation number/entity verification with auto-regeneration, UI source attribution so SDRs can self-verify; **every LLM call's prompt + response persisted as JSONL for full audit trail** |
| **Verification burden exceeds 2-min target** | False savings — SDR replaces research time with review time | **Phase 2–3: 100% review across all tiers** with one-click approve UX to keep median review time low; dashboard surfaces `review_seconds` median and P95 in real time; > 2 min median triggers a throttled alert. Tier-based sampling is held back to post-Phase-4 stable state to avoid premature trust |
| **Scoring ICP drift** | Score relevance degrades as the market changes | Quarterly retrospective against closed-won cohort; rubric weights re-tuned with full audit trail |
| **API outage** (Census/News/WalkScore/Anthropic) | Pipeline produces incomplete or no emails | Per-API median fallback; LLM fallback chain (Sonnet → Haiku → deterministic template); Resend immediate alert on pipeline crash |
| **Database or cron failure** | Same-day inbound leads unprocessed | GitHub Actions retry; immediate alert; manual `Trigger run` from the dashboard as a fallback |
| **Data confidence inconsistency** | LLM cites unreliable data and damages credibility | Provenance table mandates source + confidence per fact; system prompt restricts specific-number citation to facts with confidence ≥ 0.85 |
| **SDR adoption resistance** | Low pilot engagement, training stalls | Inherit EliseAI Education Team's 7-step training framework (§7); name SDR Champions early and pay them in influence (peer demos, co-authored prompts) |

---

## 7. Training Approach

The full-team training in Phase 4 follows the seven-step framework EliseAI's own Education Team published — both because it works and because using their internal change-management playbook signals cultural alignment:

1. **Start with Why.** Kick-off frames the value: 15–30 minutes saved per lead, plus an end to fabricated stats in cold emails. Not "we're rolling out AI."
2. **Communicate what stays the same.** Salesforce remains the system of record; AE handoff is unchanged; SDR quotas are not (yet) being adjusted. This blunts job-security anxiety.
3. **Empower champions.** The Phase-2 SDR Champions become the Phase-4 demo leads. Peers learn faster from peers than from leadership.
4. **Mix training formats.** 30-min live demo + Loom recording (focused on the dashboard's Inbox + Card modes) + Notion runbook + 1:1 shadowing for the first few sessions.
5. **Solicit feedback continuously.** Weekly Slack channel `#ai-sdr-feedback` plus an in-dashboard "Send feedback" button that captures the current lead context.
6. **Track success indicators visibly.** §5 metrics auto-emailed weekly to Sales Leadership. The team sees the numbers rather than hearing about them.
7. **Accept that training is ongoing.** Quarterly lunch-and-learn sessions, anchored on prompt-iteration data from the previous quarter's edit-diffs.

---

## 8. Tool Stack Integration

EliseAI's GTM Engineer job description (publicly listed on their Ashby careers page) names the internal stack: **Salesforce, Outreach, Salesloft, Clay, ZoomInfo, Apollo, Gong, Attention, Clari/BoostUp, HubSpot (marketing), Snowflake, dbt, Zapier, Google Apps Script**. This pipeline plugs into that stack as follows:

| EliseAI tool | Integration point |
|---|---|
| **Salesforce** | Phase 4: approved emails write back to the Lead object; tier and score populate custom fields; sequence triggers on tier change |
| **Outreach** | Phase 4: approved Hot-tier emails auto-enroll into the high-touch sequence; Warm into the standard sequence; Cold into a templated nurture sequence |
| **Clay** | Complementary: Clay continues to handle generic firmographic enrichment for the broader org. This pipeline adds EliseAI-specific ICP scoring + per-fact provenance + ICP-aware email drafting on top |
| **Gong / Attention** | Post-Phase 4: call recordings flow back as long-term prompt-calibration data — what objections come up, what value props land |
| **Google Apps Script + Sheets** | Fallback only: if the dashboard is unavailable, the existing CSV-upload path keeps SDRs unblocked |

Salesforce + Outreach integration is **scoped to Phase 4** rather than the MVP because the Phase 1–3 dashboard captures the same one-click feedback locally — getting the rollout data cleanly is more important than CRM round-tripping during the pilot.

---

## 9. Beyond Week 8

After general availability, the operating model is:

- **Daily**: cron processes new inbound leads; SDRs review via Inbox; alerts flag any pipeline-level failures
- **Weekly**: RevOps reviews KPIs with Sales Leadership; GTM Engineer reviews edit-diffs and adjusts prompts
- **Monthly**: full-team retrospective; review hallucination intercept rate and any governance incidents
- **Quarterly**: rubric recalibration against the closed-won cohort; cost-per-meeting trend review; major-version prompt updates

The pipeline is designed to compound: each week of approve/edit/reject data makes the next week's drafts better. The dashboard makes that data legible — without it, the rollout becomes opaque and the iteration loop breaks.

---

*End of Rollout Plan.*
