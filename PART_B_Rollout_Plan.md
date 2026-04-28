# Part B — Rollout Plan

> Sales-org rollout plan companion to [PART_A](./PART_A_Technical_Design.md) and [README](./README.md).
> A more polished standalone English version lives at [ROLLOUT_PLAN.md](./ROLLOUT_PLAN.md) — that's the recommended read for evaluators. This file is the original v2 design doc kept for full audit trail.

---

## 1. Philosophy

EliseAI's Education Team has publicly documented their change-management approach in *"Change Management Champs: 7 Training Best Practices"*. This plan inherits that methodology, combined with publicly available AI-SDR-tool rollout playbooks from SaaStr, Apollo, and Qualified.

Two core tenets:

- **"Start with the Why"** (EliseAI's own phrasing)
- **"Tool is 20% of the outcome. Training, ownership, segmentation, and ramp is 80%"** (SaaStr)

## 2. Five-Phase Rollout (8–10 weeks; v2 adds Phase 0)

> **v2 adds Phase 0**: with the v2 architecture (FastAPI + React + Postgres + deploys), 1 week of infra prep is needed before pilot. v1's four phases otherwise unchanged.

| Phase | Weeks | Core Actions | Exit Gate |
|---|---|---|---|
| **Phase 0 — Infra Setup** ⭐ v2 | Week 0 | Neon Postgres provisioning, Render/Vercel deploys, Resend domain, GH Actions secrets, NMHC Top 50 list import, seed data | Dashboard reachable + cron runs once + alert email delivered |
| **Phase 1 — Readiness** | Week 1 | Email auth (SPF/DKIM/DMARC); lock one ICP segment (recommended: leads matching existing NMHC Top 50 EliseAI customer profile); upload 30–50 historical closed leads for baseline scoring | RevOps Owner named + scoring distribution reasonable |
| **Phase 2 — Co-pilot** | Week 2–3 | All AI-generated emails reviewed in dashboard before send; **`feedback.review_seconds` monitored real-time**; daily approve/edit/reject ratio collected; iterate prompt and scoring | Brand/compliance approval ≥ 95% **AND** median review time < 2 min/email |
| **Phase 3 — Measured Autonomy** | Week 4–6 | 80% AI, 20% control; measure reply rate / meetings booked / SQL conversion lift via dashboard `/metrics/overview` | AI cohort meetings/100 contacts ≥ control |
| **Phase 4 — Scale Decision** | Week 7–8 | Leadership + RevOps Go/No-Go; full-team training; Salesforce + Outreach integration | Leadership approves + training complete |

**Critical pitfall** (Apollo): *"A pilot that saves prospecting time while adding hours of review has not demonstrated ROI."*

→ **v2 mitigation**: dashboard directly shows median and P95 of `review_seconds`; > 2 min triggers throttled alert. Tier-based review depth enabled from day 1 of Phase 2.

## 3. Stakeholders & Named Owner

**First-90-day named owner: RevOps Engineer** (per Landbase playbook).

| Stakeholder | Responsibility | Phases |
|---|---|---|
| Sales Leadership (VP Sales) | ICP calibration, scoring weight approval, Phase 4 Go/No-Go | Phase 0, 1, 4 |
| SDR Champion (1–2) | Daily use, high-frequency feedback, peer influence | Phase 1–4 |
| **RevOps Engineer** (named owner) | Salesforce / Outreach integration, data integrity, exception handling; dashboard metrics consumption | All of first 90 days |
| **GTM Engineer** (candidate / tool maintainer) | Pipeline maintenance, prompt iteration, scoring tuning; respond to hallucination-check anomalies on dashboard | Throughout |
| SDR Team (full) | Daily dashboard use from Phase 4 | Phase 4+ |
| IT / Security | API keys, PII compliance, Resend domain verification | Phase 0 |
| Legal / Compliance | CAN-SPAM, AI-generated content disclosure | Phase 1, 3 |
| Marketing Ops | Lead source attribution, CSV upload coordination | Phase 2+ |

## 4. Success Metrics

### 4.1 Core Lift (vs control)

| Metric | Target | Dashboard source |
|---|---|---|
| Positive reply rate | AI ≥ control | `/metrics/overview` |
| Meetings/100 contacts | AI ≥ control + 10% | Same |
| SQL conversion rate | Parity | Same |

### 4.2 Operational Efficiency

| Metric | Target | Source |
|---|---|---|
| Message approval rate | ≥ 95% by end of Phase 2 | `feedback.action='approved'` ratio |
| **Verification burden** | **< 2 min/email median** | **`feedback.review_seconds` directly** ⭐ |
| Cost per meeting | -20% vs baseline | (API + LLM cost) / closed meetings |
| Governance incidents | ≤ 1/month | hallucination-check + manual report |
| **Hallucination interception rate** | < 5% regen rate | `email.warnings` containing hallucination flag |

### 4.3 Verification Burden Mitigation: Tier-Based Review Depth

| Tier | Review strategy | Dashboard UX |
|---|---|---|
| Hot (≥75) | 100% SDR review | Inbox mode (sorted by tier) |
| Warm (55–74) | 50% sampled | Card mode (fast triage) |
| Cold (<55) | 10% sampled / templated sequence | Bulk approve via Table |

v2's three UI modes directly support this — review effort scales with lead value.

## 5. Tool Stack Integration

Per EliseAI's GTM Engineer JD, internal stack includes Clay / Gong / Google Apps Script / Zapier / Salesforce / Outreach / Python / SQL.

| EliseAI Tool | Relationship |
|---|---|
| **Salesforce** | Phase 4 integration: approved emails write to Salesforce Lead + sequence trigger; scoring writes to custom fields |
| **Outreach** | Phase 4 integration: approved emails enrolled into Outreach sequences by tier |
| **Clay** | Complementary: Clay = generic enrichment; this tool = EliseAI-ICP scoring + provenance + email |
| **Google Apps Script + Sheet** | Fallback only: if dashboard outage, CSV continues via Sheet |
| **Gong** | Post-Phase 4: call recordings flow back as prompt calibration data |

## 6. Risks & Mitigation

| Risk | Impact | Mitigation (v2 enhanced) |
|---|---|---|
| LLM hallucination | Brand incident | **4-layer defense** (provenance / prompt / post-gen check / UI source); auto-regenerate on severe issues |
| Scoring ICP drift | Score relevance decays | Quarterly review from closed-won cohort; dashboard `/metrics` continuously monitors tier distribution |
| API outage | Missing emails | 3-layer fallback (L1 retry / L2 Haiku / L4 template); Resend alert |
| **Verification burden exceeds target** | False savings | dashboard `review_seconds` real-time monitoring; > 2 min median triggers throttled alert |
| **DB / Cron failure** ⭐ v2 | Same-day leads unprocessed | GH Actions auto-retry; immediate alert; manual trigger fallback |
| **Data confidence inconsistency** ⭐ v2 | LLM uses unreliable data | Provenance table mandates source/confidence per fact; prompt restricts specific-number citation to confidence ≥ 0.85 |
| SDR resistance | Low adoption | Inherit EliseAI's 7-step training framework (§7) |

## 7. Training Approach (Inherits EliseAI's 7-Step Framework)

1. **Start with Why** — "15–30 min saved per lead + no fabricated numbers"
2. **Communicate what stays the same** — Salesforce remains SoT, AE handoff unchanged
3. **Empower champions** — Phase-2 SDR Champions become Phase-4 demo leads
4. **Mix training formats** — 30-min live demo + Loom (focus: dashboard UX + Card mode) + Notion + 1:1 shadowing
5. **Solicit feedback** — weekly Slack `#ai-sdr-feedback` + in-dashboard "Feedback" button
6. **Track success indicators** — §4 metrics → weekly auto-emailed report to sales leadership
7. **Accept training is ongoing** — quarterly lunch-and-learn with prompt iteration data

## 8. Timeline Overview

```
Week 0       │ Phase 0: Infra Setup ⭐ (Postgres + deploys + alert + seed)
Week 1       │ Phase 1: Readiness (RevOps owner + baseline scoring)
Week 2-3     │ Phase 2: Co-pilot (SDR Champion 100% review, monitor review_seconds)
Week 4-6     │ Phase 3: Measured Autonomy (20% control, measure lift)
Week 7-8     │ Phase 4: Scale Decision (Go/No-Go + training + SFDC/Outreach)
Week 9+      │ Stable operation + continuous dashboard monitoring
Week 13      │ First quarterly retrospective (recalibrate from closed-won cohort)
```

## 9. v2 Key Differences (vs v1)

| Item | v1 | v2 |
|---|---|---|
| Phases | 4 (Readiness → Co-pilot → Autonomy → Scale) | **5** (added Phase 0 Infra) |
| Feedback mechanism | Vague ("via Slack/forms") | **Dashboard one-click approve + auto diff** |
| Verification burden monitoring | Manual stats | **`feedback.review_seconds` real-time** |
| Tier-based review | Concept | **Three UI modes directly support** |
| Hallucination governance | "Prompt guardrails" | **4-layer defense + auto-regeneration + monitoring** |
| Risks listed | 5 | **7** (added DB/cron + data confidence) |

---

*End of Part B document.*
