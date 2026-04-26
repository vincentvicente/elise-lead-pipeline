# Part A — Inbound Lead Enrichment Tool
## 需求与技术设计文档（v2）/ Requirements & Technical Design (v2)

> **v2 修订说明**：v1 是 take-home 脚本形态。v2 升级到 production-shaped MVP——FastAPI 后端 + React Dashboard + Postgres 持久化 + 完整观测体系 + 多层 LLM 幻觉防御。

---

> **双语文档说明 / Bilingual Note**
> 本文档上半为中文版本，下半为英文版本，内容一一对应。
> Top half is Chinese; bottom half is English equivalent.

---

# 📘 中文版本

## 1. 问题定义

EliseAI 销售团队（SDR）每天处理大量 inbound leads。每条 lead 进入 CRM 时仅含基础信息：

- **Person（联系人）**：姓名、邮箱、公司
- **Building（物业）**：物业地址、城市、州、国家

SDR 手工调研、判定优先级、撰写个性化开场邮件，单条耗时 15–30 分钟。本工具自动化这一流程，并交付**含人工反馈闭环**的 production-shaped MVP。

## 2. 输入输出规范

### 2.1 输入字段

7 字段对齐 PDF Context 段：`name, email, company, property_address, city, state, country`

> **PDF 字段不一致处理**：Context 段 7 字段、Deliverables 段 6 字段（缺 Country）。本工具按 Context 段实现，Country 用于地理路由（US/CA vs others）。

### 2.2 输入载体

| 载体 | 何时使用 |
|---|---|
| **Dashboard CSV 上传**（主）| SDR / Marketing 在前端上传 CSV → 写入 Postgres `leads` 表 status='pending' |
| 测试 fixture | 本地开发时 `tests/fixtures/leads.csv` |

### 2.3 输出（数据库 + Dashboard 渲染）

每条 lead 处理后产生跨表数据：

| 表 | 关键字段 |
|---|---|
| `runs` | id, started_at, finished_at, status, lead_count, success_count, report_md |
| `leads` | id, run_id, name, email, company, property_address, ..., status, processed_at |
| `enriched_data` | lead_id, census_json, news_json, wiki_json, walkscore_json, fred_json, nmhc_json, errors |
| `provenance` | lead_id, fact_key, source, confidence, fetched_at, raw_ref |
| `scores` | lead_id, total, tier, breakdown_json, reasons[] |
| `emails` | id, lead_id, subject, body, source (model name / template_fallback), warnings[] |
| `feedback` | id, email_id, sdr_email, action (approved/edited/rejected), final_subject, final_body, review_seconds, rejection_reason |
| `api_logs` | run_id, lead_id, api_name, started_at, duration_ms, http_status, success, error_type |
| `alert_history` | alert_key, last_sent, count |

## 3. 整体架构

### 3.1 形态决策

**核心选择**：Pipeline 与 Dashboard 完全分离，共享 Postgres 作为单一真实源。

| 备选 | 是否采用 | 原因 |
|---|---|---|
| 单体（FastAPI + APScheduler）| ❌ | Web crash → cron 也停；pipeline 占 web 资源 |
| **分离（cron + FastAPI 共享 DB）**| ✅ | 抗 crash、可独立调试、cron 用 GH Actions 免费 |
| 队列（FastAPI + Redis + Worker）| ❌ | 当前 scope 不需要 |

### 3.2 数据流

```
┌──────────────────────────────┐
│  GitHub Actions cron (9am)   │
│  python -m elise_leads.cron  │
└──────────────┬───────────────┘
               │ 写
               ▼
   ┌────────────────────────────────────────────┐
   │  Neon Postgres                              │
   │  runs / leads / enriched / scores / emails  │
   │  / feedback / provenance / api_logs / alerts│
   └────────────────────────────────────────────┘
        ▲                                   ▲
        │ 写反馈                             │ 读
        │                                   │
   ┌────┴──────────────┐         ┌──────────┴────────┐
   │  FastAPI server   │◄────────│  React Dashboard  │
   │  (Render)          │  HTTP   │  (Vercel)          │
   │  - REST API        │         │  - 5 主页 + 2 详情 │
   │  - upload CSV      │         │  - one-click approve│
   │  - trigger run     │         │  - charts          │
   └───────────────────┘         └────────────────────┘
                                            │ 触发邮件 alert
                                            ▼
                                    ┌──────────────────┐
                                    │  Resend          │
                                    │  → SDR 邮箱       │
                                    └──────────────────┘
```

### 3.3 Pipeline 内部流水线

```
fetch pending leads
        │
        ▼
┌─────────────────────────┐
│ Enrichment (parallel)    │
│  ├─ Census Geocoder      │
│  ├─ Census ACS           │
│  ├─ NewsAPI              │
│  ├─ Wikipedia            │
│  ├─ WalkScore            │
│  ├─ FRED                 │ ← v2 新加
│  └─ NMHC list 匹配        │ ← v2 新加（本地静态）
└──────────┬───────────────┘
           │ 每个事实落入 provenance 表
           ▼
┌─────────────────────────┐
│ Scoring (规则引擎)       │
│  v2 权重: 55/30/15       │
└──────────┬───────────────┘
           │
   ┌───────┼───────────────────┐
   ▼       ▼                    ▼
Insights  Email                 Hallucination check
(rules)  (LLM with provenance)  (regenerate if severe)
   │       │                    │
   └───────┴────────────────────┘
                │
                ▼
        Write to DB
```

## 4. 技术栈

### 4.1 后端

| 组件 | 选择 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | |
| Web | FastAPI | 自动 OpenAPI、async 友好 |
| HTTP | `httpx` | async 兼容（未来扩展） |
| 重试 | `tenacity` | 指数退避 + jitter |
| ORM | SQLAlchemy 2.0 (async) | SQLite ↔ Postgres 切换零成本 |
| Migrations | Alembic | 版本化 schema |
| LLM | `anthropic` | Claude SDK |
| 日志 | `structlog` | 结构化 JSON |
| 邮件 alert | `resend` | 现代 API、3000/月免费 |
| 配置 | `pydantic-settings` + `.env` | |
| 测试 | `pytest` + `pytest-asyncio` | |
| 任务运行 | GitHub Actions cron | |

### 4.2 前端

| 组件 | 选择 |
|---|---|
| 构建 | Vite + TypeScript |
| UI | shadcn/ui + Tailwind |
| 数据 | TanStack Query |
| 路由 | React Router |
| 图表 | Recharts |
| 表单 | React Hook Form + Zod |
| Diff | `react-diff-viewer-continued` |
| 类型生成 | `openapi-typescript`（从 FastAPI OpenAPI 自动生成 TS）|

### 4.3 基础设施

| 组件 | 平台 | 免费额度 |
|---|---|---|
| Postgres | Neon | 0.5 GB 永久免费 |
| FastAPI | Render | 免费层（cold-start 30s）|
| React | Vercel | 无限制（个人）|
| Cron | GitHub Actions | 公开 repo 无限制 |
| 邮件 | Resend | 3000/月、100/天 |

## 5. 仓库结构

**Monorepo**，单仓库三大目录：

```
elise-lead-pipeline/
├── backend/
│   ├── elise_leads/
│   │   ├── __init__.py
│   │   ├── settings.py            # pydantic-settings 配置
│   │   ├── models/                # SQLAlchemy 模型
│   │   │   ├── run.py
│   │   │   ├── lead.py
│   │   │   ├── enriched.py
│   │   │   ├── score.py
│   │   │   ├── email.py
│   │   │   ├── feedback.py
│   │   │   ├── provenance.py
│   │   │   ├── api_log.py
│   │   │   └── alert.py
│   │   ├── enrichers/
│   │   │   ├── base.py            # Protocol + 装饰器
│   │   │   ├── census.py          # Geocoder + ACS
│   │   │   ├── news.py
│   │   │   ├── wikipedia.py
│   │   │   ├── walkscore.py
│   │   │   ├── fred.py            # v2 新加
│   │   │   └── nmhc.py            # v2 新加（本地静态）
│   │   ├── data/
│   │   │   └── nmhc_top_50.json   # 静态名单
│   │   ├── scoring/
│   │   │   ├── rubric.py          # 权重 + 规则
│   │   │   └── dimensions.py      # 各子维度纯函数
│   │   ├── generation/
│   │   │   ├── email.py           # 主入口 + fallback chain
│   │   │   ├── prompts.py         # SYSTEM_PROMPT
│   │   │   ├── proof_points.py    # 规则化 proof point 选择
│   │   │   ├── insights.py        # 规则化洞察抽取
│   │   │   └── hallucination.py   # post-gen 检测
│   │   ├── alerting/
│   │   │   ├── rules.py
│   │   │   └── client.py          # Resend 包装
│   │   ├── pipeline.py            # 串起来
│   │   ├── cron.py                # cron 入口
│   │   └── api/
│   │       ├── main.py            # FastAPI app
│   │       ├── deps.py            # 依赖注入
│   │       └── routers/
│   │           ├── uploads.py
│   │           ├── runs.py
│   │           ├── leads.py
│   │           ├── feedback.py
│   │           └── metrics.py
│   ├── alembic/
│   ├── tests/
│   │   ├── fixtures/
│   │   │   ├── leads.csv
│   │   │   └── golden_cases.py
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── api/                   # 自动生成的 TS 类型
│   │   ├── pages/
│   │   │   ├── Overview.tsx
│   │   │   ├── Inbox.tsx
│   │   │   ├── LeadDetail.tsx
│   │   │   ├── Leads.tsx
│   │   │   ├── Runs.tsx
│   │   │   ├── RunDetail.tsx
│   │   │   └── Upload.tsx
│   │   ├── components/
│   │   │   ├── KPICard.tsx
│   │   │   ├── EmailEditor.tsx
│   │   │   ├── DiffModal.tsx
│   │   │   ├── ScoreBreakdown.tsx
│   │   │   ├── ProvenanceFootnotes.tsx
│   │   │   └── ...
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── infra/
│   ├── .github/workflows/
│   │   ├── cron.yml               # 每天 9am 触发 pipeline
│   │   ├── backend-deploy.yml
│   │   └── frontend-deploy.yml
│   ├── render.yaml                # Render 部署配置
│   └── docker-compose.yml         # 本地开发 Postgres
│
├── docs/
│   └── plans/
│
├── PART_A_Technical_Design.md
├── PART_B_Rollout_Plan.md
└── README.md
```

## 6. 数据库 Schema

核心表（SQLAlchemy 2.0 风格）：

```python
class Run(Base):
    id: UUID = Column(UUID, primary_key=True, default=uuid4)
    started_at: datetime
    finished_at: datetime | None
    status: str             # 'running' / 'success' / 'crashed' / 'partial'
    lead_count: int
    success_count: int
    failure_count: int
    report_md: str | None   # 自动生成的 MD 报告
    
    leads: list["Lead"] = relationship()

class Lead(Base):
    id: UUID
    run_id: UUID | None     # 待处理时为 None
    name: str
    email: str
    company: str
    property_address: str
    city: str
    state: str
    country: str
    status: str             # 'pending' / 'processing' / 'processed' / 'failed'
    processed_at: datetime | None
    uploaded_at: datetime

class EnrichedData(Base):
    lead_id: UUID (FK)
    census_json: JSONB | None
    news_json: JSONB | None
    wiki_json: JSONB | None
    walkscore_json: JSONB | None
    fred_json: JSONB | None
    nmhc_json: JSONB | None
    errors: JSONB           # {"census": "geocoder failed", ...}

class Provenance(Base):
    """每条事实的来源和置信度"""
    id: UUID
    lead_id: UUID
    fact_key: str           # "renter_pct" / "company_units_managed" / ...
    fact_value: JSONB
    source: str             # "census_acs_2022" / "newsapi_2026-04-22"
    confidence: float       # 0.0–1.0
    fetched_at: datetime
    raw_ref: str | None     # 链接回 raw API response

class Score(Base):
    lead_id: UUID
    total: int              # 0-100
    tier: str               # 'Hot' / 'Warm' / 'Cold'
    breakdown: JSONB        # {"company_scale": 25, "buy_intent": 20, ...}
    reasons: JSONB          # ["High renter density (68%)...", ...]

class Email(Base):
    id: UUID
    lead_id: UUID
    subject: str
    body: str
    source: str             # 'llm:claude-sonnet-4-6' / 'llm:claude-haiku-4-5' / 'template_fallback'
    warnings: JSONB         # 校验告警
    hallucination_check: JSONB  # post-gen 检测结果
    created_at: datetime

class Feedback(Base):
    id: UUID
    email_id: UUID
    sdr_email: str
    action: str             # 'approved' / 'edited' / 'rejected'
    final_subject: str | None
    final_body: str | None
    rejection_reason: str | None
    review_seconds: int     # 监控 verification burden
    created_at: datetime

class ApiLog(Base):
    id: BigInt
    run_id: UUID
    lead_id: UUID | None
    api_name: str           # 'census' / 'newsapi' / 'claude'
    started_at: datetime
    duration_ms: int
    http_status: int | None
    success: bool
    error_type: str | None
    error_detail: str | None

class AlertHistory(Base):
    alert_key: str (PK)
    severity: str           # 'immediate' / 'throttled'
    last_sent: datetime
    count: int
```

## 7. REST API 端点

```
POST   /api/v1/uploads                  # CSV 上传 → leads.status='pending'
POST   /api/v1/runs/trigger             # 手动触发 pipeline (后台任务)
GET    /api/v1/runs                     # 列表 + 状态
GET    /api/v1/runs/{id}                # 详情 + MD report
GET    /api/v1/leads                    # 列表（query: tier/status/run_id/page）
GET    /api/v1/leads/{id}               # 详情 + enriched + score + email + provenance
POST   /api/v1/leads/{id}/feedback      # 写 feedback（approve/edit/reject）
GET    /api/v1/metrics/overview         # 首页 KPI + chart 数据
GET    /api/v1/metrics/api-performance  # API 性能历史
```

OpenAPI 由 FastAPI 自动生成（`/docs` Swagger UI），前端用 `openapi-typescript` 生成 TS 类型。

## 8. 前端页面规格

### 8.1 Sitemap

```
/                  Overview (KPI + 趋势 + 最近 runs)
/inbox             SDR 审核（Inbox + Card 模式切换）
/leads             All Leads (Table 视图 + 筛选)
/leads/:id         Lead Detail (enriched + score + email + provenance + feedback)
/runs              Run 历史
/runs/:id          Run 详情 + MD report
/upload            CSV 上传 + Process now 按钮
```

### 8.2 关键交互

**Inbox 模式（默认）**：左侧 lead 列表 + 右侧详情 + 操作区。

**Card 模式（"Focus mode"）**：单条全屏 + 键盘快捷键 `A`/`R`/`E`/`J`/`K`。50 条快审 10 分钟。

**邮件编辑**：Inline textarea 直接改 → "Approve" 自动 diff 原版与最终版 → 写 feedback 表。点 "View Changes" 弹 modal 显示双栏 diff。

**Source Attribution**：邮件正文里每个事实自动加 footnote 标号，下方列出来源（"NewsAPI / WSJ, 3 days ago"）。

### 8.3 实时更新

TanStack Query polling，3 秒一次（仅 running run）。无 WebSocket。

## 9. Enrichment API 详情

| API | Endpoint | Auth | 抽取字段 | Confidence |
|---|---|---|---|---|
| Census Geocoder | geocoding.geo.census.gov | 无 | tract / state / county / lat / lon | 0.95 |
| Census ACS | api.census.gov/data/2022/acs/acs5 | 免费 key | renter_pct, median_income, median_rent, density | 0.95 |
| NewsAPI | newsapi.org/v2/everything | 需 key | articles[], signal_keywords[] | 0.85（主流来源）/ 0.70（其他）|
| Wikipedia | en.wikipedia.org/w/api.php | 无（需 UA）| company_summary, scale_extracted_via_regex | 0.70 |
| WalkScore | api.walkscore.com/score | 需 key | walk/transit/bike scores | 0.85 |
| **FRED** | api.stlouisfed.org/fred | 需 key（免费）| state_vacancy_rate, rent_yoy | 0.95 |
| **NMHC Top 50** | 本地 JSON | 无 | rank, units_managed | 0.95 |

### 9.1 Rate Limiting 策略

| API | 硬限制 | 防护 |
|---|---|---|
| NewsAPI | 100/day | 按 company name LRU 缓存 + 配额持久化追踪 + 安全余量 5 |
| Census ACS | 实际无限（带 key）| 按 tract LRU 缓存 |
| WalkScore | 5000/day | 按坐标四舍五入缓存 |
| Claude | 50 RPM (Tier 1) | 主动限速 1.3s/req + tenacity 指数退避 |
| FRED | 120 req/min | 按 state 缓存 |

## 10. Scoring Rubric v2

### 10.1 权重总览（100 分）

```
Company-side  (55) ████████████████████████████████████████████████████████
Geography     (30) ██████████████████████████████
Contact-side  (15) ███████████████
```

### 10.2 各维度细则

#### Company Scale（25 分）—— 用 NMHC + Wikipedia + News

```python
def score_company_scale(enriched) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    
    # NMHC Top 50 命中（最高 15 分）
    if nmhc := match_nmhc(enriched.lead.company):
        if nmhc["rank"] <= 10:
            score += 15
            reasons.append(f"NMHC Top 10 (#{nmhc['rank']}, {nmhc['units_managed']:,} units)")
        else:
            score += 10
            reasons.append(f"NMHC Top 50 (#{nmhc['rank']})")
    
    # Wikipedia 解析（最高 5 分）
    if wiki_scale := extract_scale_from_wiki(enriched.wiki):
        score += 5
        reasons.append(f"Wiki indicates: {wiki_scale}")
    elif enriched.wiki and enriched.wiki.get("exists"):
        score += 2
        reasons.append("Has Wikipedia presence")
    
    # News 数量与权威度（最高 5 分）
    score += score_news_profile(enriched.news)
    
    return min(score, 25), reasons
```

#### Buy Intent（20 分）—— 关键词分级

| 关键词 | 含义 | 分数 |
|---|---|---|
| acquired / merger / acquisition | M&A | 20 |
| expansion / launched / new property / groundbreaking | 新楼盘 | 18 |
| funding / raised / series | 融资 | 15 |
| partnership / technology | 技术开放 | 12 |
| 任意公司新闻 | 存在 | 10 |
| 无新闻 | — | 5 |

#### Vertical Fit（10 分）—— 子垂直匹配

```python
VERTICAL_KEYWORDS = {
    "multifamily": ["apartment", "multifamily", "residential"],     # +10
    "student": ["student", "campus", "university", "college"],      # +10
    "affordable": ["affordable", "lihtc", "section 8"],             # +10
    "military": ["military", "fort", "base", "naval"],              # +10
    "sfr": ["single family", "build to rent", "btr"],               # +10
    "senior": ["senior", "55+", "active adult"],                    # 命中即硬降 Cold
    "commercial": ["office", "retail", "industrial", "commercial"]  # 命中即硬降 Cold
}
```

**关键**：senior / commercial 命中是**硬性 disqualifier**（直接 tier=Cold），不是负分加权。

#### Market Fit（15 分）—— Census

| 信号 | 来源 | 分数映射 |
|---|---|---|
| 租户占比 | Census `B25008` | >65% → 8 / 50–65% → 5 / 35–50% → 3 / <35% → 1 |
| 中位收入 | Census `B19013` | >$75k → 7 / $55–75k → 5 / $40–55k → 3 / <$40k → 1 |

#### Property Fit（10 分）

| 信号 | 来源 | 分数映射 |
|---|---|---|
| WalkScore | WalkScore API | >80 → 5 / 60–80 → 4 / 40–60 → 2 / <40 → 1 |
| 中位租金 | Census `B25064` | >$1500 → 5 / $1000–1500 → 3 / <$1000 → 1 |

#### Market Dynamics（5 分）—— FRED

| 信号 | 来源 | 分数映射 |
|---|---|---|
| 区域空置率 | FRED `RRVRUSQ156N` | >7% → 3 / 5–7% → 2 / <5% → 1（高空置 = 更需要工具） |
| 租金 YoY | FRED CPI Rent | 增长 > 5% → 2 / >0% → 1 / 负 → 0 |

#### Contact Fit（15 分）

| 信号 | 来源 | 分数映射 |
|---|---|---|
| Corporate domain | email | 非 gmail/yahoo/etc → 5 / 否 → 0 |
| Domain ↔ company match | email + company | 匹配 → 5 / 顾问域 → 2 / 不匹配 → 0 |
| Prefix shape | email prefix | "first.last" → 5 / 单字 → 3 / generic（info/contact/leasing@）→ 0 |

### 10.3 Tier 阈值

```
Hot   : 75+
Warm  : 55–74
Cold  : <55
```

### 10.4 数据缺失兜底

**原则不变**：缺失给中位分 + 标注，**永不惩罚**。

### 10.5 验证

Golden cases（v2 扩展）：

```python
GOLDEN_CASES = [
    ("Greystar Austin",        Hot,  min=85),
    ("Asset Living rural",     Hot,  min=70),    # 验证 company > geo
    ("Unknown @ Manhattan",    Cold, max=50),    # 验证不被地理迷惑
    ("Senior living Co",       Cold, reason="non-ICP vertical"),
    ("Commercial real estate", Cold, reason="non-ICP vertical"),
    ("Toronto large operator", Hot,  reason="CA in scope"),
    ("Berlin operator",        Cold, reason="non-US/CA"),
    ("Gmail.com lead",         Cold, max=55),
    ("Missing Census data",    Warm, reason="median fallback"),
]
```

## 11. Email 生成 + 多层幻觉防御

### 11.1 防御四层

```
L1: Provenance Tracking         → 每条事实带 source/confidence
L2: Provenance-Aware Prompt     → XML 结构 + grounding rules
L3: Post-Gen Hallucination Check → 数字/实体核查 + 重生成
L4: UI Source Attribution       → SDR 看到来源能自验
```

### 11.2 Layer 2：Provenance-Aware System Prompt

System prompt 核心结构（~600 tokens）：

```
You are an SDR at EliseAI...

<product>
  <proof_point id="equity">$14M payroll savings at Equity Residential</proof_point>
  <proof_point id="asset">+300bps occupancy at Asset Living</proof_point>
  <proof_point id="afterhours">47.5% of leasing messages arrive after-hours</proof_point>
  <proof_point id="nmhc">38 of NMHC Top 50 use EliseAI</proof_point>
</product>

<rules>
  - 80–120 words, 3 short paragraphs
  - Reference ONLY facts in <verified_facts> from user message
  - Cite specific numbers ONLY if confidence ≥ 0.85
  - Never invent customers, statistics, or events
  - If a fact is marked "do not cite specific numbers", obey
  - Tone: professional, warm, no jargon
</rules>

<output_format>
<subject>...</subject>
<body>...</body>
</output_format>
```

### 11.3 User Prompt 示例

```xml
<lead>
  Name: Sarah Johnson
  Company: Greystar
  Property: 123 Main St, Austin, TX
</lead>

<verified_facts>
  <fact source="nmhc_top_50_2024" confidence="0.95">
    Greystar ranked #1 with 822,897 units managed.
  </fact>
  <fact source="newsapi_2026-04-22" confidence="0.85">
    Headline (3 days ago): "Greystar acquires Alliance Residential".
    Source: Wall Street Journal.
  </fact>
  <fact source="census_acs_2022" confidence="0.95">
    Property tract: 68% renter-occupied, $72k median income.
  </fact>
  <fact source="wikipedia_2026-04-24" confidence="0.70">
    Greystar described as the largest US apartment manager.
    NOTE: Confidence < 0.85, do NOT cite specific numbers from this source.
  </fact>
</verified_facts>

<lead_score>
  Score: 92/100 (Hot)
  Top signals: NMHC #1, M&A news, Hot market
</lead_score>

<recommended_proof_point>
  equity (Equity Residential $14M payroll savings — fits large operator profile)
</recommended_proof_point>

<instructions>
  Use ONLY verified_facts above. Use the recommended proof point.
  Do NOT mix multiple proof points or invent additional facts.
</instructions>
```

### 11.4 Layer 3：Post-Gen Hallucination Detection

```python
def detect_hallucination(email: Email, facts: list[Fact]) -> list[str]:
    issues = []
    text = (email.subject + " " + email.body).lower()
    
    fact_text = " ".join(_serialize_fact(f) for f in facts).lower()
    
    # 1. 数字核查
    numbers = extract_numbers(text)
    for n in numbers:
        if not _number_appears_in(n, fact_text, KNOWN_OK_NUMBERS):
            issues.append(f"Unverified number: '{n}'")
    
    # 2. 实体核查（公司名、人名）
    entities = extract_entities(text)  # 用 Claude Haiku 抽取
    for e in entities["organizations"]:
        if e.lower() not in fact_text and e.lower() not in KNOWN_OK_TERMS:
            issues.append(f"Unverified org: '{e}'")
    
    # 3. 时间表述核查
    if has_recent_time_phrase(text) and not has_recent_news(facts):
        issues.append("Time reference without supporting recent fact")
    
    return issues
```

**KNOWN_OK_TERMS** 是预定义的 EliseAI 自家信息（Equity Residential、Asset Living、NMHC、产品名等）。

**严重 issue（Unverified number / org）→ 自动重生成**（最多 2 次），仍失败 → 模板兜底。

### 11.5 Fallback Chain

```
L1: tenacity retry 同模型 (3 次)
       ↓ 失败
L2: 切 Haiku 4.5 (同 SDK 同 prompt)
       ↓ 失败 / 仍幻觉
L4: 模板兜底（确定性字符串）
```

每封邮件记录 `email.source` 字段，dashboard 可见。

## 12. 日志与观测

### 12.1 三通道日志

```
通道 1: structlog → stdout JSON
        └─ GitHub Actions 自动捕获，UI 可查看
        
通道 2: api_logs 表 (Postgres)
        └─ Dashboard 查询，画 metrics 图

通道 3: runs.report_md
        └─ 每次 run 自动生成 MD 摘要，dashboard 渲染
```

### 12.2 MD Report 模板

```markdown
# Run 2026-04-24 09:00 UTC
**Status**: ✅ success (47/50 leads processed)

## Summary
- Total leads: 50
- Hot/Warm/Cold: 12 / 23 / 12
- Failed enrichments: 3 (newsapi quota for last 3)
- Email generation: 47 LLM, 0 template fallback
- Hallucination check: 1 regenerated, all passed final

## API Performance
| API       | Calls | Avg ms | p95 ms | Failures |
|-----------|-------|--------|--------|----------|
| Census    | 50    | 234    | 412    | 0        |
| NewsAPI   | 47    | 567    | 1023   | 3 quota  |
| WalkScore | 50    | 189    | 298    | 0        |
| Claude    | 50    | 3421   | 5012   | 1 regen  |

## Notable events
- 09:23 NewsAPI 95/100 threshold reached
- 09:24 Switched 3 leads to no-news fallback
```

## 13. Alerting

### 13.1 配置

```bash
# .env
ALERT_EMAIL=vincentvicenteqy@outlook.com
RESEND_API_KEY=re_xxxxx
```

### 13.2 触发与冷却

| Severity | 冷却 | 触发例子 |
|---|---|---|
| immediate | 0（不冷却）| Pipeline 整体 crash、所有 lead 失败 |
| throttled | 1 小时 | >30% lead 失败、API quota 耗尽、p95 latency > 阈值 |

### 13.3 邮件正文（MD → HTML）

```markdown
# 🚨 [IMMEDIATE] EliseAI Pipeline Crashed

**Run ID**: run_2026-04-24-0900
**Time**: 2026-04-24 09:03 UTC

## What happened
DatabaseConnectionError: could not connect to Neon Postgres after 30s.

## Affected
50 leads queued, 0 processed.

## Action
- Check Neon status: https://neonstatus.com/
- GH Actions log: [link]
- Manual retry: [Dashboard URL]/runs/manual-trigger
```

## 14. 错误处理

| 层级 | 错误 | 处理 |
|---|---|---|
| API | Geocoder fail | Census + WalkScore 跳过；Market/Property 中位分 |
| API | NewsAPI 超额 | Buy Intent 给中位分；新闻为空 |
| API | Wikipedia missing | 正常情况，相关项 0 分 |
| API | Claude 5xx / RateLimit | tenacity 重试 |
| API | Claude 持续失败 | Haiku fallback |
| API | Haiku 也失败 | 模板兜底 |
| Lead | 单 lead 异常 | 内层 try/except，标 `failed`，继续下一条 |
| Pipeline | 顶层异常 | 外层 try/except，发 immediate alert |

## 15. 验证策略

| 方法 | 何时 | 输出 |
|---|---|---|
| Golden cases (Test) | CI 必跑 | 9 条覆盖 Hot/Warm/Cold/边界 |
| 敏感度分析 | Pre-release | 权重 ±20% 看 tier 分布稳定性 |
| 分布合理性 | 每次大批量跑后 | tier 分布 ~20/50/30 校验阈值 |
| 生产回测（README）| 上线后 | 历史 closed-won/lost 与 score 的 Spearman 相关 |

## 16. 成本与扩容

### 16.1 Take-home 规模（50 lead/批 + 30 天 dashboard 使用）

| 项 | 成本 |
|---|---|
| Neon Postgres | $0 |
| Render FastAPI | $0 |
| Vercel React | $0 |
| GH Actions cron | $0 |
| Resend alerts | $0 |
| Census / Wikipedia / WalkScore / FRED | $0 |
| NewsAPI | $0（免费层）|
| Claude Sonnet 4.6（50 lead × $0.015）| $0.75 |
| Claude Haiku（hallucination 检测，50 × $0.001）| $0.05 |
| **总计** | **~$0.80** |

### 16.2 扩容路径（README）

| 日处理量 | 措施 |
|---|---|
| <500 leads/day | 当前架构即可 |
| 500–5k leads/day | 启 prompt caching；DB 加索引；Neon paid tier |
| 5k+ leads/day | async 并发 + Claude Batch API（50% 折扣）+ Redis 缓存 |
| 10k+ leads/day | 队列 + worker；Postgres 升 RDS；多 cron worker |

## 17. 关键决策日志（v2）

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| 1 | 形态 | FastAPI + React + Postgres 分离 | 抗 crash、production-shaped |
| 2 | 数据库 | Neon Postgres（云）+ SQLite（本地）| 通过 SQLAlchemy 切换 |
| 3 | Scheduler | GitHub Actions cron | 免费、可移植 |
| 4 | Lead 输入 | Dashboard CSV 上传 | 单一真实源 |
| 5 | 日志 | structlog stdout + api_logs 表 + MD report | 不重复造工具 |
| 6 | Alerting | Resend + 写死单收件人 + 两级冷却 | MVP 简化 |
| 7 | 工作流 UI | Inbox + Card + Table 三模式 | 不同节奏需求 |
| 8 | 邮件编辑 | Inline 主 + diff modal | 速度 + 数据完整 |
| 9 | Scoring 重心 | Company 55 / Geography 30 / Contact 15 | 修复 v1 偏地理问题 |
| 10 | Vertical disqualifier | senior/commercial 硬降 Cold | 严格 ICP 边界 |
| 11 | 公司规模信号 | NMHC + Wiki + News 组合 | 不引入 SEC/爬取 |
| 12 | 幻觉防御 | 4 层全做（provenance + prompt + check + UI）| LLM 是最高风险点 |
| 13 | LLM 模型 | Sonnet 4.6 主 / Haiku 4.5 fallback | 成本 vs 质量 |

---

# 📗 English Version

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

*End of Part A v2 document.*
