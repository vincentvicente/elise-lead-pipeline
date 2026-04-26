"""Tests for the email generation pipeline (M4).

Covers:
- Proof-point selector decisions
- Insights extraction
- Hallucination detection (numbers + entities + time phrases)
- Prompt rendering shape
- email.generate_email() with mocked Claude
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from elise_leads.enrichers.base import ApiLogEntry
from elise_leads.generation import (
    email as email_mod,
    hallucination,
    insights,
    llm_client,
    proof_points,
    prompts,
)
from elise_leads.generation.proof_points import select as select_proof_point
from elise_leads.scoring.rubric import LeadScore


# ============================================================================
# Proof-point selector
# ============================================================================
class TestProofPointSelector:
    def test_top10_nmhc_selects_equity_residential(self) -> None:
        sel = select_proof_point(
            lead_company="Greystar",
            nmhc={"matched": True, "rank": 1},
            news=None,
            census=None,
        )
        assert sel.id == "equity_residential"
        assert "Top 10" in sel.rationale

    def test_ma_news_selects_equity_residential(self) -> None:
        sel = select_proof_point(
            lead_company="Some Co",
            nmhc={"matched": False},
            news={"signal_keywords": {"high": ["acquired"]}},
            census=None,
        )
        assert sel.id == "equity_residential"

    def test_expansion_signal_selects_asset_living(self) -> None:
        sel = select_proof_point(
            lead_company="X",
            nmhc=None,
            news={"signal_keywords": {"medium_high": ["new property"]}},
            census=None,
        )
        assert sel.id == "asset_living"

    def test_student_keyword_selects_landmark(self) -> None:
        sel = select_proof_point(
            lead_company="University Housing Partners",
            nmhc=None,
            news=None,
            census=None,
        )
        assert sel.id == "landmark_student"

    def test_high_renter_density_selects_after_hours(self) -> None:
        sel = select_proof_point(
            lead_company="X",
            nmhc=None,
            news=None,
            census={"acs": {"renter_pct": 0.72}},
        )
        assert sel.id == "after_hours"

    def test_default_falls_back_to_nmhc_top_50_proof(self) -> None:
        sel = select_proof_point(
            lead_company="Random LLC",
            nmhc={"matched": False},
            news=None,
            census=None,
        )
        assert sel.id == "nmhc_top_50"


# ============================================================================
# Insights extractor
# ============================================================================
class TestInsights:
    def test_score_headline_first_bullet(self) -> None:
        bullets = insights.extract(
            lead_company="X",
            nmhc=None,
            wiki=None,
            news=None,
            census=None,
            walkscore=None,
            fred=None,
            score_tier="Hot",
            score_total=82,
        )
        assert bullets[0].startswith("Lead score: 82/100")

    def test_nmhc_top10_company_bullet(self) -> None:
        bullets = insights.extract(
            lead_company="Greystar",
            nmhc={"matched": True, "rank": 1, "units_managed": 822_897},
            wiki=None,
            news=None,
            census=None,
            walkscore=None,
            fred=None,
            score_tier="Hot",
            score_total=92,
        )
        assert any("NMHC Top 10" in b and "822,897" in b for b in bullets)

    def test_insights_capped_at_5_bullets(self) -> None:
        # Provide as many signals as possible; should cap at 5
        bullets = insights.extract(
            lead_company="Greystar",
            nmhc={"matched": True, "rank": 1, "units_managed": 800_000},
            wiki={
                "company_page": {"title": "Greystar"},
                "company_scale_extracted": {"value": 800_000, "unit": "units"},
            },
            news={
                "articles": [
                    {
                        "title": "Greystar acquires Alliance",
                        "source": "WSJ",
                        "published_at": "2026-04-22T00:00:00Z",
                    }
                ]
            },
            census={"acs": {"renter_pct": 0.68}},
            walkscore={"walk_score": 92, "walk_description": "Walker's Paradise"},
            fred={"vacancy_rate_pct": 8.0},
            score_tier="Hot",
            score_total=95,
        )
        assert len(bullets) <= 5

    def test_no_signals_still_returns_score_bullet(self) -> None:
        bullets = insights.extract(
            lead_company="X",
            nmhc=None,
            wiki=None,
            news=None,
            census=None,
            walkscore=None,
            fred=None,
            score_tier="Cold",
            score_total=30,
        )
        assert len(bullets) == 1
        assert "Cold" in bullets[0]


# ============================================================================
# Hallucination detection
# ============================================================================
class TestHallucination:
    def _facts_with(self, *items) -> list:
        """Build a facts list of (key, value, source, conf) tuples."""
        return [
            (f"k{i}", v, "test_source", 0.95) for i, v in enumerate(items)
        ]

    def test_clean_email_passes(self) -> None:
        body = (
            "Hi Sarah,\n\nNoticed your portfolio. EliseAI helps with leasing.\n\n"
            "Worth a chat?\n\nBest,\n[SDR Name]"
        )
        check = hallucination.detect(
            body=body,
            verified_facts=self._facts_with("Greystar manages 800,000 units"),
            lead_company="Greystar",
            proof_point_id="nmhc_top_50",
            has_recent_news=False,
        )
        assert check.passed
        assert check.severe_count == 0

    def test_unverified_number_flagged(self) -> None:
        # 25,000 is not in facts and not in product proof points
        body = "Companies like yours typically see 25,000 fewer hours of leasing labor."
        check = hallucination.detect(
            body=body,
            verified_facts=[],
            lead_company="Greystar",
            proof_point_id="nmhc_top_50",
            has_recent_news=False,
        )
        assert check.has_severe
        assert any(i.category == "unverified_number" for i in check.issues)

    def test_known_product_number_allowed(self) -> None:
        # $14M is a canonical product proof point
        body = "Equity Residential saved $14M in payroll savings."
        check = hallucination.detect(
            body=body,
            verified_facts=[],
            lead_company="Greystar",
            proof_point_id="equity_residential",
            has_recent_news=False,
        )
        assert check.passed

    def test_invented_customer_flagged(self) -> None:
        # "Sterling Capital Holdings" is not in facts or proof points
        body = (
            "We helped Sterling Capital Holdings cut their leasing costs."
        )
        check = hallucination.detect(
            body=body,
            verified_facts=[],
            lead_company="Greystar",
            proof_point_id="nmhc_top_50",
            has_recent_news=False,
        )
        # Could be flagged as unverified_org
        assert check.has_severe

    def test_time_phrase_warning_only(self) -> None:
        body = "I saw last week that you launched a new property."
        check = hallucination.detect(
            body=body,
            verified_facts=[],
            lead_company="Greystar",
            proof_point_id="nmhc_top_50",
            has_recent_news=False,
        )
        # Should produce a warning-severity issue, not severe
        time_issues = [i for i in check.issues if i.category == "time_phrase"]
        assert len(time_issues) >= 1
        assert all(i.severity == "warning" for i in time_issues)


# ============================================================================
# Prompt rendering
# ============================================================================
class TestPrompts:
    def test_user_prompt_contains_required_sections(self) -> None:
        out = prompts.render_user_prompt(
            lead_name="Sarah Johnson",
            lead_company="Greystar",
            lead_property="123 Main St, Austin, TX",
            facts=[("renter_pct", 0.68, "census_acs_2022", 0.95)],
            score_total=92,
            score_tier="Hot",
            top_reasons=["NMHC #1", "M&A news"],
            recommended_proof_point_id="equity_residential",
            recommended_proof_point_quote="Equity saved $14M.",
        )
        assert "<lead>" in out
        assert "<verified_facts>" in out
        assert "<lead_score>" in out
        assert "<recommended_proof_point" in out
        assert "Sarah Johnson" in out
        assert "0.95" in out

    def test_low_confidence_fact_gets_note(self) -> None:
        out = prompts.render_fact("scale", "800k units", "wikipedia", 0.70)
        assert "do NOT cite specific numbers" in out

    def test_high_confidence_fact_no_note(self) -> None:
        out = prompts.render_fact("renter_pct", 0.68, "census_acs_2022", 0.95)
        assert "do NOT cite" not in out


# ============================================================================
# email.generate_email() — mocked LLM
# ============================================================================
class TestEmailGenerator:
    @pytest.fixture
    def fake_score(self) -> LeadScore:
        return LeadScore(
            total=92,
            tier="Hot",
            breakdown={"company_scale": 25},
            reasons=["[Company Scale] NMHC Top 10"],
        )

    @pytest.fixture
    def fake_proof(self) -> proof_points.ProofPointSelection:
        return proof_points.ProofPointSelection(
            id="equity_residential",
            quote="Equity Residential saved $14M.",
            rationale="NMHC Top 10",
        )

    @pytest.mark.asyncio
    async def test_clean_response_returns_llm_draft(
        self, fake_score, fake_proof
    ) -> None:
        # Mock returns a clean, fact-grounded draft
        clean_xml = (
            "<subject>Quick question, Sarah</subject>\n"
            "<body>Hi Sarah,\n\n"
            "Saw the news about Greystar's portfolio expansion. "
            "Equity Residential saved $14M with EliseAI.\n\n"
            "Worth a quick chat?\n\nBest,\n[SDR Name]</body>"
        )

        mock_response = llm_client.ClaudeResponse(
            raw_text=clean_xml,
            subject="Quick question, Sarah",
            body=(
                "Hi Sarah,\n\n"
                "Saw the news about Greystar's portfolio expansion. "
                "Equity Residential saved $14M with EliseAI.\n\n"
                "Worth a quick chat?\n\nBest,\n[SDR Name]"
            ),
            model="claude-sonnet-4-6",
            api_log=ApiLogEntry(
                api_name="claude:claude-sonnet-4-6",
                started_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                duration_ms=2400,
                http_status=200,
                success=True,
            ),
        )

        with patch.object(
            llm_client, "call_claude", new=AsyncMock(return_value=mock_response)
        ):
            draft = await email_mod.generate_email(
                lead_name="Sarah Johnson",
                lead_email="sarah.johnson@greystar.com",
                lead_company="Greystar",
                lead_property="123 Main St, Austin, TX",
                lead_city="Austin",
                score=fake_score,
                facts=[("nmhc_rank", 1, "nmhc_top_50_2024", 0.95)],
                proof=fake_proof,
                has_recent_news=True,
            )

        assert draft.source == "llm:claude-sonnet-4-6"
        assert "[SDR Name]" in draft.body
        assert draft.proof_point_used == "equity_residential"
        assert draft.hallucination_check["passed"] is True
        assert len(draft.api_logs) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_template_when_all_llm_fails(
        self, fake_score, fake_proof
    ) -> None:
        # Mock raises every time → exhausts both Sonnet & Haiku
        with patch.object(
            llm_client,
            "call_claude",
            new=AsyncMock(side_effect=RuntimeError("API down")),
        ):
            draft = await email_mod.generate_email(
                lead_name="Sarah Johnson",
                lead_email="sarah.johnson@greystar.com",
                lead_company="Greystar",
                lead_property="123 Main St",
                lead_city="Austin",
                score=fake_score,
                facts=[],
                proof=fake_proof,
                has_recent_news=False,
            )

        assert draft.source == "template_fallback"
        assert "[SDR Name]" in draft.body
        # The proof point's quote should still be referenced
        assert "Equity Residential" in draft.body
        # Warnings include the fallback notice
        assert any("template" in w.lower() for w in draft.warnings)

    @pytest.mark.asyncio
    async def test_severe_hallucination_triggers_regeneration(
        self, fake_score, fake_proof
    ) -> None:
        """First call returns hallucinated draft, second call returns clean."""
        bad = llm_client.ClaudeResponse(
            raw_text="<subject>S</subject><body>Hi, we helped Made-Up Holdings save $50M\n\nBest,\n[SDR Name]</body>",
            subject="S",
            body="Hi, we helped Made-Up Holdings save $50M\n\nBest,\n[SDR Name]",
            model="claude-sonnet-4-6",
            api_log=ApiLogEntry(
                api_name="claude:claude-sonnet-4-6",
                started_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                duration_ms=2000,
                http_status=200,
                success=True,
            ),
        )
        good = llm_client.ClaudeResponse(
            raw_text="<subject>X</subject><body>Hi Sarah,\n\nEquity Residential saved $14M.\n\nWorth a chat?\n\nBest,\n[SDR Name]</body>",
            subject="X",
            body="Hi Sarah,\n\nEquity Residential saved $14M.\n\nWorth a chat?\n\nBest,\n[SDR Name]",
            model="claude-sonnet-4-6",
            api_log=ApiLogEntry(
                api_name="claude:claude-sonnet-4-6",
                started_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                duration_ms=2000,
                http_status=200,
                success=True,
            ),
        )

        with patch.object(
            llm_client,
            "call_claude",
            new=AsyncMock(side_effect=[bad, good]),
        ):
            draft = await email_mod.generate_email(
                lead_name="Sarah Johnson",
                lead_email="sarah@greystar.com",
                lead_company="Greystar",
                lead_property="123 Main St",
                lead_city="Austin",
                score=fake_score,
                facts=[],
                proof=fake_proof,
                has_recent_news=False,
            )

        assert draft.source == "llm:claude-sonnet-4-6"
        # Second attempt was the clean one — should have logged 2 API calls
        assert len(draft.api_logs) == 2
