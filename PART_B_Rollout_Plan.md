# Part B — Rollout Plan (v2)
## 销售团队推广计划 / Sales Org Rollout Plan

> **v2 修订说明**：v1 的 rollout plan 围绕"邮件草稿"展开。v2 由于 Part A 升级为含 dashboard + one-click approve 的完整 MVP，**Phase 2 的反馈循环现在直接由 dashboard 驱动**，verification burden 监控由 `feedback.review_seconds` 字段实时支撑。

---

> **双语文档说明 / Bilingual Note**
> 本文档上半为中文版本，下半为英文版本，内容一一对应。
> Top half is Chinese; bottom half is English equivalent.

---

# 📘 中文版本

## 1. 推广哲学

EliseAI 自家 Education Team 在 *"Change Management Champs: 7 Training Best Practices"* 博客中明确写过他们的变更管理方法论。本计划继承这套方法论，并结合 SaaStr、Apollo、Qualified 等公开 AI SDR 工具 rollout playbook。

两条核心信条：

- **"Start with the Why"**（EliseAI 原话）：SDR 理解了为什么需要这个工具才会配合执行
- **"Tool is 20% of the outcome. Training, ownership, segmentation, and ramp is 80%"**（SaaStr）：本文档花 80% 篇幅在 process

## 2. 五阶段推广（8–10 周，v2 比 v1 多一个 Phase 0）

> **v2 新增 Phase 0**：因为现在有完整 dashboard + Postgres + 部署链路，需要 1 周做基础设施准备。原 v1 的 4 阶段保持不变。

| 阶段 | 周次 | 核心动作 | Exit Gate |
|---|---|---|---|
| **Phase 0 — Infra Setup** ⭐ v2 新加 | Week 0 | Neon Postgres provisioning；Render/Vercel 部署；Resend domain；GH Actions secrets；NMHC Top 50 名单导入；初始 seed data | Dashboard 可访问 + cron job 跑通 1 次 + alert 邮件成功送达 |
| **Phase 1 — Readiness** | Week 1 | 邮件发信配置（SPF/DKIM/DMARC）核对；锁定 1 个 ICP 细分（推荐：NMHC Top 50 内已有 EliseAI 客户画像）作首批试点；上传首批 30–50 条历史 closed leads 做 baseline 跑分 | RevOps Owner 到位 + scoring 分布合理（不过度集中 Cold/Hot） |
| **Phase 2 — Co-pilot** | Week 2–3 | AI 生成邮件全数由 SDR 在 dashboard 审核后发送；**`feedback.review_seconds` 实时监控审核负担**；每日收集 approve/edit/reject 比例；迭代 prompt 与 scoring 阈值 | 品牌/合规通过率 ≥ 95% **且** 平均审核时长 < 2 min/邮件 |
| **Phase 3 — Measured Autonomy** | Week 4–6 | 80% lead 走 AI 工具，20% control group 维持人工；测 reply rate / meetings booked / SQL 转化三项 lift；dashboard `/metrics/overview` 实时对比 | AI 组 meetings/100 contacts 不低于 control |
| **Phase 4 — Scale Decision** | Week 7–8 | Sales Leadership + RevOps Go/No-Go；全员培训；接 Salesforce + Outreach 流程 | Leadership 批准 + 全员训练完成 |

**关键 pitfall**（Apollo 原话）：*"A pilot that saves prospecting time while adding hours of review has not demonstrated ROI."*

→ **v2 对策**：dashboard 直接展示 `review_seconds` 中位数和 P95，阈值 2 分钟超标自动 alert。Tier-based 审核深度（§4.3）从 Phase 2 第一天就启用。

## 3. 干系人与指定负责人

**首 90 天指定负责人：RevOps Engineer**（Landbase playbook 最佳实践）。

| 干系人 | 职责 | 参与阶段 |
|---|---|---|
| **Sales Leadership**（VP Sales）| ICP 校准、scoring 权重审批、Phase 4 Go/No-Go | Phase 0, 1, 4 |
| **SDR Champion**（1–2 名）| 早期日常使用、高频反馈、同侪影响 | Phase 1–4 |
| **RevOps Engineer**（指定负责人）| Salesforce / Outreach 集成、数据一致性、异常处理；**dashboard 数据消费**（Phase 2 起从 dashboard 拉指标）| 首 90 天全程 |
| **GTM Engineer**（候选人 / 工具开发者）| Pipeline 维护、prompt 迭代、scoring 调权；**响应 dashboard 上的 hallucination check 异常** | 全程 |
| **SDR Team**（全员）| Phase 4 起日常使用 dashboard | Phase 4+ |
| **IT / Security** | API key 管理、PII 合规、Resend 域名验证 | Phase 0 |
| **Legal / Compliance** | CAN-SPAM 合规、AI 生成内容披露政策 | Phase 1, 3 |
| **Marketing Ops** | lead 来源归因、CSV 上传协调 | Phase 2+ |

## 4. 成功指标

### 4.1 核心 lift 指标（vs control group）

| 指标 | 目标 | Dashboard 来源 |
|---|---|---|
| Positive reply rate | AI 组 ≥ control | `/metrics/overview` reply rate by tier |
| Meetings/100 contacts | AI 组 ≥ control + 10% | 同上 |
| SQL conversion rate | 两组持平 | 同上 |

### 4.2 运营效率指标

| 指标 | 目标 | Dashboard 来源 |
|---|---|---|
| Message approval rate | Phase 2 末 ≥ 95% | `feedback.action='approved'` 占比 |
| **Verification burden** | **< 2 min/邮件**（中位数）| **`feedback.review_seconds` 直接监控**⭐ |
| Cost per meeting | 较基线 -20% | API + LLM 成本 / 成交 meeting |
| Governance incidents | 月 ≤ 1 起 | hallucination check + manual report |
| **Hallucination check 拦截率** | < 5%（重生成率）| `email.warnings` 含幻觉告警比例 |

### 4.3 Verification Burden 对策：Tier-based 审核深度

| Tier | 审核策略 | Dashboard UI |
|---|---|---|
| Hot (≥75) | SDR 全审 | Inbox 模式默认筛选 |
| Warm (55–74) | 抽审 50% | Card 模式快审 |
| Cold (<55) | 抽审 10% | Bulk approve 通过 Table 视图 |

**v2 Dashboard 直接支持**：Inbox 模式按 tier 排序、Card 模式键盘快捷键、Table 模式批量操作——三种 UI 都能复用，但**节奏匹配 lead 价值**。

## 5. 工具栈集成

EliseAI 公开 GTM Engineer JD（Ashby）确认内部栈包含 Clay / Gong / Google Apps Script / Zapier / Salesforce / Outreach / Python / SQL。本工具 v2 在生态中的定位：

| EliseAI 工具 | 与本工具的关系 |
|---|---|
| **Salesforce** | Phase 4 集成：dashboard 上 approve 后，邮件自动写入 Salesforce Lead 对象 + sequence 触发；scoring 数据写入自定义字段 |
| **Outreach** | Phase 4 集成：approved 邮件自动入 Outreach sequence；按 tier 分配 cadence |
| **Clay** | 互补：Clay 做通用 enrichment；本工具做 EliseAI ICP 专属打分（NMHC + 行业关键词）+ provenance + 邮件生成 |
| **Google Apps Script + Sheet** | 仅作 fallback：万一 dashboard 故障，CSV 可继续从 Sheet 拉 |
| **Gong** | Phase 4 后：Gong 通话记录回流，作为长期 prompt 校准数据源 |

## 6. 风险与缓解

| 风险 | 影响 | 缓解（v2 增强）|
|---|---|---|
| LLM hallucination | 品牌事故 | **4 层防御**（provenance / prompt / post-gen check / UI source）；hallucination check 严重时自动重生成 |
| Scoring ICP drift | 打分逐月失准 | 季度性回顾，从 closed-won cohort 重新校准；dashboard `/metrics` 持续监控 tier 分布 |
| API outage | 邮件缺失 | 三层 fallback（L1 retry / L2 Haiku / L4 template）；Resend alert 立即通知 |
| **Verification burden 超标** | 伪节省 | dashboard `review_seconds` 实时监控；超 2min 中位数触发 throttled alert + tier-based 审核策略 |
| **DB / Cron 故障** ⭐ v2 新加 | 当日 lead 不处理 | GH Actions 自动 retry；监控 alert 立即通知；手动触发按钮兜底 |
| **数据来源置信度不一致** ⭐ v2 新加 | LLM 用了不可靠数据 | provenance 表强制每条事实标 confidence；prompt 限制只能引用 ≥0.85 的具体数字 |
| SDR 抗拒 | 采用率低 | 继承 EliseAI Education Team 7 步法（§7）|

## 7. 培训方式（继承 EliseAI 自家 7 步法）

Phase 4 全员培训直接复用 EliseAI Education Team 公开的 7 步：

1. **Start with Why**：kickoff 讲清"SDR 每条 lead 省 15–30 min 调研 + 不再编造数字"
2. **Communicate what stays the same**：Salesforce 仍是 source of truth，AE 接棒流程不变
3. **Empower champions**：Phase 2 的 SDR Champion 担任内部 demo 人
4. **Mix training formats**：30 min live demo + Loom 录屏（重点演示 dashboard 操作 + Card 模式）+ Notion 文档 + 1:1 shadowing
5. **Solicit feedback**：每周 Slack `#ai-sdr-feedback` 频道 + dashboard 内嵌"Feedback"按钮
6. **Track success indicators**：§4 指标 → weekly dashboard report 自动发到 sales leadership
7. **Accept training is ongoing**：季度 lunch-and-learn 分享 prompt 改进、scoring 调权数据

## 8. 时间线总览

```
Week 0       │ Phase 0: Infra Setup ⭐ (Postgres + 部署 + alert + seed data)
Week 1       │ Phase 1: Readiness (RevOps owner 到位 + baseline 跑分)
Week 2-3     │ Phase 2: Co-pilot (SDR Champion 全审, 监控 review_seconds)
Week 4-6     │ Phase 3: Measured Autonomy (20% control, 测 lift)
Week 7-8     │ Phase 4: Scale Decision (Go/No-Go + 全员培训 + Salesforce/Outreach 集成)
Week 9+      │ 稳定运营 + dashboard 持续监控
Week 13      │ 首次季度 retrospective (基于 closed-won cohort 重调权重)
```

## 9. v2 关键差异（vs v1）

| 项 | v1 | v2 |
|---|---|---|
| Phase 数 | 4（Readiness → Co-pilot → Autonomy → Scale）| **5**（加 Phase 0 Infra Setup）|
| 反馈收集机制 | 模糊（"通过 Slack/forms"）| **Dashboard one-click approve + diff 自动捕获**|
| Verification burden 监控 | 人工统计 | **`feedback.review_seconds` 实时**|
| Tier-based 审核 | 概念 | **三种 UI 模式直接支撑**|
| Hallucination 治理 | "prompt 护栏" | **4 层防御 + 自动重生成 + 监控指标**|
| Risk 列表 | 5 项 | **7 项**（加 DB/Cron 故障 + 数据 confidence）|

---

# 📗 English Version

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

*End of Part B v2 document.*
