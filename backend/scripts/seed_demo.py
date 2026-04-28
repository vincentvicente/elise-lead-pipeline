"""Seed the local dev DB with realistic demo data.

Run via:  uv run python -m scripts.seed_demo

Creates:
- 2 historical Runs (one success, one partial)
- 12 Leads spanning Hot/Warm/Cold + pending state
- Score / Email / Feedback / EnrichedData / Provenance for processed leads
- A handful of ApiLog entries

After seeding, visit http://localhost:5173 to browse the dashboard.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from elise_leads import db as db_mod
from elise_leads.models import (
    ApiLog,
    Email,
    EnrichedData,
    Feedback,
    Lead,
    Provenance,
    Run,
    Score,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- Demo personas ---------------------------------------------------------
LEADS_DATA = [
    # --- Processed Hot leads ---
    {
        "name": "Sarah Johnson",
        "email": "sarah.johnson@greystar.com",
        "company": "Greystar",
        "address": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "tier": "Hot",
        "score": 92,
        "breakdown": {
            "company_scale": 25, "buy_intent": 20, "vertical_fit": 10,
            "market_fit": 13, "property_fit": 8, "market_dynamics": 4,
            "contact_fit": 15,
        },
        "reasons": [
            "[Company Scale] NMHC Top 10 operator (#1, 822,897 units managed)",
            "[Buy Intent] Strong buy signal — M&A in news",
            "[Market Fit] High renter density (68%) — strong ICP fit",
            "[Contact Fit] Corporate domain matches company; personal-format email",
        ],
        "subject": "Quick question, Sarah",
        "body": (
            "Hi Sarah,\n\nSaw the Alliance Residential acquisition — impressive "
            "footprint expansion. That kind of integration puts real pressure on "
            "leasing response times across the combined portfolio.\n\n"
            "Equity Residential ran into similar load as they scaled and ended up "
            "saving $14M in leasing payroll by automating prospect conversations "
            "with EliseAI. Given your new Austin footprint, might be worth a look.\n\n"
            "Would 15 min next Tuesday work?\n\nBest,\n[SDR Name]"
        ),
        "feedback": {"action": "approved", "review_seconds": 47},
    },
    {
        "name": "Mike Lee",
        "email": "mike.lee@assetliving.com",
        "company": "Asset Living",
        "address": "456 Oak Ave",
        "city": "Houston",
        "state": "TX",
        "tier": "Hot",
        "score": 84,
        "breakdown": {
            "company_scale": 22, "buy_intent": 18, "vertical_fit": 10,
            "market_fit": 8, "property_fit": 5, "market_dynamics": 3,
            "contact_fit": 18,
        },
        "reasons": [
            "[Company Scale] NMHC Top 10 (#2, 257,123 units)",
            "[Buy Intent] Expansion signal in news",
            "[Vertical Fit] Multifamily clearly identified",
        ],
        "subject": "Operations scaling at Asset Living",
        "body": (
            "Hi Mike,\n\nNoticed Asset Living's continued growth across the South. "
            "At your scale, every percentage point of occupancy compounds across "
            "the portfolio.\n\nAsset Living saw +300 bps occupancy and +600 bps "
            "on-time rent in Q2 2025 after deploying EliseAI — open to comparing "
            "notes?\n\nWorth a quick chat?\n\nBest,\n[SDR Name]"
        ),
        "feedback": {"action": "edited", "review_seconds": 95},
    },
    {
        "name": "Jamie Chen",
        "email": "j.chen@avalonbay.com",
        "company": "AvalonBay Communities",
        "address": "789 Pine Rd",
        "city": "Arlington",
        "state": "VA",
        "tier": "Hot",
        "score": 88,
        "breakdown": {
            "company_scale": 24, "buy_intent": 15, "vertical_fit": 10,
            "market_fit": 14, "property_fit": 9, "market_dynamics": 3,
            "contact_fit": 13,
        },
        "reasons": [
            "[Company Scale] NMHC Top 50 (#12, 80,800 units)",
            "[Market Fit] High renter density (72%) — strong ICP fit",
        ],
        "subject": "Scaling leasing across AvalonBay",
        "body": (
            "Hi Jamie,\n\nQuick note — saw your Q2 update on portfolio growth. "
            "EliseAI handles 47.5% of leasing inquiries that arrive after-hours "
            "for operators like AvalonBay, no SDR overtime required.\n\n"
            "Worth 15 min next week?\n\nBest,\n[SDR Name]"
        ),
        "feedback": None,
    },
    # --- Warm leads ---
    {
        "name": "Pat Riley",
        "email": "pat@bozzuto.com",
        "company": "Bozzuto Group",
        "address": "200 Elm St",
        "city": "Greenbelt",
        "state": "MD",
        "tier": "Warm",
        "score": 68,
        "breakdown": {
            "company_scale": 12, "buy_intent": 10, "vertical_fit": 10,
            "market_fit": 11, "property_fit": 8, "market_dynamics": 2,
            "contact_fit": 15,
        },
        "reasons": [
            "[Company Scale] NMHC Top 50 (#16, 87,000 units)",
            "[Buy Intent] Generic media coverage (3 articles)",
        ],
        "subject": "After-hours leasing — Bozzuto fit?",
        "body": (
            "Hi Pat,\n\nBozzuto's reputation for resident experience is hard to "
            "match — and after-hours response is a big part of that.\n\n"
            "47.5% of leasing inquiries hit during off-hours. EliseAI handles "
            "all of them. Curious if it's worth a 15-min look?\n\nBest,\n[SDR Name]"
        ),
        "feedback": {"action": "approved", "review_seconds": 62},
    },
    {
        "name": "Taylor Smith",
        "email": "taylor@cardinalgroup.com",
        "company": "Cardinal Group",
        "address": "1000 Campus Dr",
        "city": "Athens",
        "state": "GA",
        "tier": "Warm",
        "score": 64,
        "breakdown": {
            "company_scale": 10, "buy_intent": 10, "vertical_fit": 10,
            "market_fit": 9, "property_fit": 7, "market_dynamics": 3,
            "contact_fit": 15,
        },
        "reasons": [
            "[Company Scale] NMHC Top 50 (#29, 85,000 units)",
            "[Vertical Fit] Student housing keyword detected",
        ],
        "subject": "Student housing leasing at scale",
        "body": (
            "Hi Taylor,\n\nNoticed Cardinal Group's student-housing focus. "
            "Each turn cycle is a fire drill for the leasing team.\n\n"
            "Landmark Properties runs EliseAI across 100+ student communities — "
            "lifted occupancy while cutting leasing-team load. Worth comparing "
            "notes?\n\nBest,\n[SDR Name]"
        ),
        "feedback": None,
    },
    # --- Cold leads ---
    {
        "name": "Robin Park",
        "email": "robin@gmail.com",
        "company": "Park Apartments LLC",
        "address": "55 Hillside Ave",
        "city": "Tulsa",
        "state": "OK",
        "tier": "Cold",
        "score": 38,
        "breakdown": {
            "company_scale": 0, "buy_intent": 5, "vertical_fit": 10,
            "market_fit": 7, "property_fit": 4, "market_dynamics": 2,
            "contact_fit": 10,
        },
        "reasons": [
            "[Company Scale] No NMHC match",
            "[Buy Intent] No recent company news",
            "[Contact Fit] Free email domain (gmail.com)",
        ],
        "subject": "Quick intro — apartment leasing automation",
        "body": (
            "Hi Robin,\n\nEliseAI is trusted by 38 of the NMHC Top 50 operators "
            "to handle inbound leasing 24/7. Worth a quick 15-min call to see "
            "if it fits Park Apartments?\n\nBest,\n[SDR Name]"
        ),
        "feedback": {"action": "rejected", "review_seconds": 22,
                     "rejection_reason": "Free-email lead, likely individual landlord"},
    },
    {
        "name": "Casey Brown",
        "email": "info@desertproperties.com",
        "company": "Desert Properties",
        "address": "400 Sunset Blvd",
        "city": "Phoenix",
        "state": "AZ",
        "tier": "Cold",
        "score": 42,
        "breakdown": {
            "company_scale": 0, "buy_intent": 5, "vertical_fit": 5,
            "market_fit": 12, "property_fit": 6, "market_dynamics": 4,
            "contact_fit": 10,
        },
        "reasons": [
            "[Contact Fit] Generic inbox 'info@' — not a personal contact",
            "[Vertical Fit] Vertical not clearly identifiable",
        ],
        "subject": "Quick intro — Desert Properties",
        "body": (
            "Hi there,\n\nReaching out as your team showed interest in EliseAI. "
            "We help apartment operators automate inbound leasing across voice, "
            "SMS, and chat — happy to share specifics.\n\n"
            "Worth a quick call?\n\nBest,\n[SDR Name]"
        ),
        "feedback": None,
    },
    # --- Failure-mode lead: NewsAPI quota + Claude rate-limit forced
    # the chain through Sonnet → Haiku → template_fallback. The pipeline
    # still produced a usable email by deterministic substitution.
    # Use this lead in the demo to show graceful degradation. ---
    {
        "name": "Jordan Cole",
        "email": "j.cole@unknownco.com",
        "company": "Unknown Operator Co",
        "address": "12 Maple Lane",
        "city": "Topeka",
        "state": "KS",
        "tier": "Cold",
        "score": 35,
        "breakdown": {
            "company_scale": 0, "buy_intent": 5, "vertical_fit": 5,
            "market_fit": 7, "property_fit": 5, "market_dynamics": 0,
            "contact_fit": 13,
        },
        "reasons": [
            "[Buy Intent] No recent company news (small or quiet operator)",
            "[Market Dynamics] FRED data unavailable (median fallback)",
            "[Contact Fit] Corporate email domain (unknownco.com)",
        ],
        "subject": "Quick question about Unknown Operator Co",
        "body": (
            "Hi [First Name],\n\n"
            "I noticed Unknown Operator Co manages properties in Topeka. "
            "EliseAI helps multifamily operators automate inbound leasing — "
            "answering prospects, scheduling tours, and handling maintenance "
            "24/7.\n\n"
            "Trusted by 38 of the NMHC Top 50 multifamily operators.\n\n"
            "Would 15 min next week make sense to compare notes?\n\n"
            "Best,\n[SDR Name]"
        ),
        "email_source": "template_fallback",
        "warnings_override": [
            "NewsAPI: HTTP 429 rate_limit — free-tier quota exhausted (100/day)",
            "Claude Sonnet 4.6 attempt 1: HTTP 429 rate_limit (Tier 1 RPM cap hit)",
            "Claude Sonnet 4.6 attempt 2: HTTP 429 rate_limit (still throttled, regenerated)",
            "Claude Haiku 4.5 attempt 1: HTTP 503 service_unavailable",
            "Claude Haiku 4.5 attempt 2: HTTP 503 service_unavailable",
            "LLM fallback chain exhausted → used deterministic template",
            "Body length 60 words (template baseline; LLM target 80–120)",
        ],
        "feedback": None,
    },
    # --- Pending leads (not yet processed) ---
    {
        "name": "Alex Rivera",
        "email": "a.rivera@morganproperties.com",
        "company": "Morgan Properties",
        "address": "300 King St",
        "city": "King of Prussia",
        "state": "PA",
        "tier": None,
        "score": None,
        "pending": True,
    },
    {
        "name": "Sam Wong",
        "email": "swong@equityresidential.com",
        "company": "Equity Residential",
        "address": "Two North Riverside Plaza",
        "city": "Chicago",
        "state": "IL",
        "tier": None,
        "score": None,
        "pending": True,
    },
    {
        "name": "Drew Patel",
        "email": "drew@willowbridge.com",
        "company": "Willow Bridge Property Company",
        "address": "555 Oak Lawn",
        "city": "Dallas",
        "state": "TX",
        "tier": None,
        "score": None,
        "pending": True,
    },
]


PROVENANCE_SAMPLES = [
    ("renter_pct", 0.68, "census_acs_2022", 0.95),
    ("median_household_income", 78_000, "census_acs_2022", 0.95),
    ("walk_score", 82, "walkscore_api", 0.85),
    ("rental_vacancy_rate_pct", 6.2, "fred_us_2026", 0.95),
    ("company_nmhc_rank", 1, "nmhc_top_50_2024", 0.95),
    ("news_buy_intent_signals", ["high"], "newsapi_keyword_extraction", 0.80),
    ("wikipedia_company_exists", True, "wikipedia_2026", 0.85),
]


async def seed() -> None:
    # Bind models module to a real sessionmaker
    async with db_mod.SessionLocal() as session:
        # ---- Two historical runs ----
        run_today = Run(
            id=uuid.uuid4(),
            started_at=_utcnow() - timedelta(hours=3),
            finished_at=_utcnow() - timedelta(hours=3, minutes=-7),
            status="success",
            lead_count=8,
            success_count=8,
            failure_count=0,
            report_md=(
                "# Run Report — today\n\n"
                "**Status**: ✅ success (8/8 processed)\n\n"
                "## Summary\n"
                "- Total leads: 8\n"
                "- Hot/Warm/Cold: 3 / 2 / 3\n"
                "- Email source: 7 LLM, 0 template fallback\n\n"
                "## API Performance\n"
                "| API | Calls | Avg ms | P95 ms | Failures |\n"
                "|---|---|---|---|---|\n"
                "| census_acs | 8 | 234 | 412 | 0 |\n"
                "| newsapi | 8 | 567 | 1023 | 0 |\n"
                "| walkscore | 8 | 189 | 298 | 0 |\n"
                "| claude:claude-sonnet-4-6 | 8 | 3421 | 5012 | 0 |\n"
            ),
        )
        run_yesterday = Run(
            id=uuid.uuid4(),
            started_at=_utcnow() - timedelta(days=1, hours=3),
            finished_at=_utcnow() - timedelta(days=1, hours=2, minutes=58),
            status="partial",
            lead_count=10,
            success_count=8,
            failure_count=2,
            report_md=(
                "# Run Report — yesterday\n\n"
                "**Status**: ⚠️ partial (8/10 processed)\n\n"
                "Two leads failed due to NewsAPI rate-limit; their emails fell "
                "back to template.\n"
            ),
        )
        session.add_all([run_today, run_yesterday])
        await session.flush()

        # ---- Build leads ----
        for idx, p in enumerate(LEADS_DATA):
            is_pending = p.get("pending", False)
            lead = Lead(
                name=p["name"],
                email=p["email"],
                company=p["company"],
                property_address=p["address"],
                city=p["city"],
                state=p["state"],
                country="US",
                status="pending" if is_pending else "processed",
                run_id=None if is_pending else run_today.id,
                processed_at=None if is_pending else (_utcnow() - timedelta(hours=2, minutes=idx)),
            )
            session.add(lead)
            await session.flush()

            if is_pending:
                continue

            # EnrichedData stub
            session.add(
                EnrichedData(
                    lead_id=lead.id,
                    nmhc_json={"matched": True, "rank": 1} if "Greystar" in p["company"] else {"matched": False},
                    news_json={
                        "articles": [
                            {
                                "title": f"{p['company']} expands portfolio",
                                "source": "Multifamily Dive",
                                "published_at": "2026-04-22T00:00:00Z",
                            }
                        ],
                        "signal_keywords": {"medium_high": ["expansion"]},
                    },
                    errors={},
                )
            )

            # Score row
            session.add(
                Score(
                    lead_id=lead.id,
                    total=p["score"],
                    tier=p["tier"],
                    breakdown=p["breakdown"],
                    reasons=p["reasons"],
                )
            )

            # Email row — fall back to template if marked, otherwise LLM
            email_source = p.get("email_source", "llm:claude-sonnet-4-6")
            email = Email(
                lead_id=lead.id,
                subject=p["subject"],
                body=p["body"],
                source=email_source,
                warnings=p.get("warnings_override", []),
                hallucination_check={"passed": True, "severe_count": 0, "warning_count": 0, "issues": []},
                proof_point_used=(
                    "equity_residential" if p["score"] >= 80
                    else "asset_living" if p["score"] >= 60
                    else "nmhc_top_50"
                ),
            )
            session.add(email)
            await session.flush()

            # Provenance — sample subset
            for key, value, source, conf in random.sample(PROVENANCE_SAMPLES, 5):
                session.add(
                    Provenance(
                        lead_id=lead.id,
                        fact_key=key,
                        fact_value=value,
                        source=source,
                        confidence=conf,
                        fetched_at=_utcnow() - timedelta(hours=2),
                    )
                )

            # Feedback (if defined)
            if p.get("feedback"):
                fb = p["feedback"]
                session.add(
                    Feedback(
                        email_id=email.id,
                        sdr_email="sdr@elise.ai",
                        action=fb["action"],
                        final_subject=p["subject"] if fb["action"] == "edited" else None,
                        final_body=(
                            p["body"].replace("Asset Living", "Asset Living team")
                            if fb["action"] == "edited" else None
                        ),
                        rejection_reason=fb.get("rejection_reason"),
                        review_seconds=fb["review_seconds"],
                    )
                )

            # Sample API logs
            for api_name in ["census_geocoder", "census_acs", "newsapi", "walkscore", "claude:claude-sonnet-4-6"]:
                session.add(
                    ApiLog(
                        run_id=run_today.id,
                        lead_id=lead.id,
                        api_name=api_name,
                        started_at=_utcnow() - timedelta(hours=2, minutes=idx),
                        duration_ms=random.randint(150, 4000),
                        http_status=200,
                        success=True,
                    )
                )

        await session.commit()
        print(f"Seeded 2 runs and {len(LEADS_DATA)} leads.")


if __name__ == "__main__":
    # Bind module-level SessionLocal to a fresh sessionmaker
    db_mod.SessionLocal = async_sessionmaker(
        bind=db_mod.engine, expire_on_commit=False, autoflush=False
    )
    asyncio.run(seed())
