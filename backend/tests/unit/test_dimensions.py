"""Per-dimension unit tests covering boundary values.

Each dimension is a pure function — no DB, no HTTP. We feed it
representative payloads and verify both points and reasons.
"""

from __future__ import annotations

from elise_leads.scoring import dimensions


# ============================================================================
# Company Scale
# ============================================================================


def test_company_scale_full_with_top10_nmhc_wiki_news() -> None:
    nmhc = {"matched": True, "rank": 1, "units_managed": 822_897}
    wiki = {
        "company_page": {"summary": "Largest US apartment manager."},
        "company_scale_extracted": {"value": 800_000, "unit": "units"},
    }
    news = {
        "articles": [{}, {}, {}, {}, {}],  # 5 articles
        "premium_count": 2,
    }
    r = dimensions.score_company_scale(nmhc, wiki, news)
    # NMHC top 10 (15) + Wikipedia scale (5) + Strong media (5) = 25
    assert r.points == 25
    assert any("NMHC Top 10" in s for s in r.reasons)
    assert any("Wikipedia indicates" in s for s in r.reasons)


def test_company_scale_top50_only() -> None:
    nmhc = {"matched": True, "rank": 28, "units_managed": 30_000}
    r = dimensions.score_company_scale(nmhc, None, None)
    assert r.points == 10
    assert any("NMHC Top 50" in s for s in r.reasons)


def test_company_scale_unknown_company() -> None:
    """No NMHC, no Wikipedia, no News — small/unknown company."""
    r = dimensions.score_company_scale(
        {"matched": False}, None, None
    )
    assert r.points == 0
    assert r.reasons == []


# ============================================================================
# Buy Intent
# ============================================================================


def test_buy_intent_high_signal_acquisition() -> None:
    news = {
        "articles": [{"title": "Greystar acquires Alliance"}],
        "signal_keywords": {"high": ["Greystar acquires Alliance"]},
    }
    r = dimensions.score_buy_intent(news)
    assert r.points == 20


def test_buy_intent_expansion_signal() -> None:
    news = {
        "articles": [{"title": "X"}],
        "signal_keywords": {"medium_high": ["New property launches"]},
    }
    assert dimensions.score_buy_intent(news).points == 18


def test_buy_intent_no_news_baseline_5() -> None:
    """No news != penalty. Returns the 'small/quiet operator' baseline."""
    r = dimensions.score_buy_intent(None)
    assert r.points == 5
    assert "No recent" in r.reasons[0]


def test_buy_intent_news_no_keywords_returns_10() -> None:
    """Has news but no targeted signals — generic coverage."""
    news = {"articles": [{"title": "X"}], "signal_keywords": {}}
    assert dimensions.score_buy_intent(news).points == 10


# ============================================================================
# Vertical Fit (HARD DISQUALIFIER cases live here)
# ============================================================================


def test_vertical_fit_multifamily_explicit_keyword() -> None:
    r = dimensions.score_vertical_fit("Apartment Investors LLC")
    assert r.points == 10
    assert r.meta["vertical"] == "multifamily"


def test_vertical_fit_neutral_when_no_keyword() -> None:
    r = dimensions.score_vertical_fit("Greystar")  # no obvious keyword
    assert r.points == 5
    assert not r.meta.get("disqualified")


def test_vertical_fit_senior_disqualifier() -> None:
    r = dimensions.score_vertical_fit("Sunrise Senior Living LLC")
    assert r.points == 0
    assert r.meta["disqualified"] is True
    assert r.meta["vertical"] == "senior"


def test_vertical_fit_commercial_disqualifier() -> None:
    r = dimensions.score_vertical_fit("Boston Properties (commercial real estate)")
    assert r.meta["disqualified"] is True
    assert r.meta["vertical"] == "commercial"


def test_vertical_fit_uses_wiki_summary_for_disambiguation() -> None:
    """A neutral-looking name + senior-living wiki summary → disqualifier."""
    r = dimensions.score_vertical_fit(
        "Holiday Retirement",
        wiki_summary="Operator of senior living communities.",
    )
    assert r.meta["disqualified"] is True


# ============================================================================
# Market Fit (Census)
# ============================================================================


def test_market_fit_high_renter_high_income() -> None:
    census = {
        "acs": {"renter_pct": 0.68, "median_household_income": 78_000}
    }
    r = dimensions.score_market_fit(census)
    # 8 (>65% renter) + 7 (>$75k income) = 15
    assert r.points == 15


def test_market_fit_owner_dominant_low_income() -> None:
    census = {"acs": {"renter_pct": 0.30, "median_household_income": 38_000}}
    r = dimensions.score_market_fit(census)
    # 1 + 1 = 2
    assert r.points == 2


def test_market_fit_no_census_uses_median_fallback() -> None:
    r = dimensions.score_market_fit(None)
    assert r.points == 7  # median of 15
    assert r.meta["median_fallback"] is True


def test_market_fit_partial_data_no_fallback() -> None:
    """If we have at least one Census variable, use it (no median fallback)."""
    census = {"acs": {"renter_pct": 0.62, "median_household_income": None}}
    r = dimensions.score_market_fit(census)
    # 5 (50-65% renter) + 0 (no income data) = 5
    assert r.points == 5
    assert not r.meta.get("median_fallback")


# ============================================================================
# Property Fit
# ============================================================================


def test_property_fit_walkable_high_rent() -> None:
    walk = {"walk_score": 92, "walk_description": "Walker's Paradise"}
    census = {"acs": {"median_monthly_rent": 1800}}
    # 5 (>80 walk) + 5 (>$1500 rent) = 10
    assert dimensions.score_property_fit(walk, census).points == 10


def test_property_fit_no_data_falls_back() -> None:
    r = dimensions.score_property_fit(None, None)
    assert r.points == 5  # median of 10
    assert r.meta["median_fallback"]


# ============================================================================
# Market Dynamics (FRED)
# ============================================================================


def test_market_dynamics_high_vacancy_high_growth() -> None:
    fred = {"vacancy_rate_pct": 7.5, "rent_yoy_pct": 6.0}
    # 3 + 2 = 5
    assert dimensions.score_market_dynamics(fred).points == 5


def test_market_dynamics_no_fred_falls_back() -> None:
    r = dimensions.score_market_dynamics(None)
    assert r.points == 2  # median of 5 = 2 (integer division)
    assert r.meta["median_fallback"]


# ============================================================================
# Contact Fit
# ============================================================================


def test_contact_fit_corporate_match_personal_format() -> None:
    """Corporate domain + matches company + first.last format → 15."""
    r = dimensions.score_contact_fit("sarah.johnson@greystar.com", "Greystar")
    assert r.points == 15
    assert any("Personal-format" in s for s in r.reasons)


def test_contact_fit_corporate_match_single_token() -> None:
    """Corporate + match + single-word prefix → 5+5+3 = 13."""
    r = dimensions.score_contact_fit("sarah@greystar.com", "Greystar")
    assert r.points == 13


def test_contact_fit_corporate_consultant_personal() -> None:
    """Domain looks like advisor: lower domain-match score."""
    r = dimensions.score_contact_fit(
        "j.smith@example-advisors.com", "Greystar"
    )
    # 5 (corporate) + 2 (consultant) + 5 (personal) = 12
    assert r.points == 12


def test_contact_fit_free_email_single_token() -> None:
    r = dimensions.score_contact_fit("sarah@gmail.com", "Greystar")
    # 0 (free) + 0 (no match check on free) + 3 (single token) = 3
    assert r.points == 3
    assert any("Free email" in s for s in r.reasons)


def test_contact_fit_generic_inbox() -> None:
    """leasing@greystar.com is a functional inbox — penalize prefix score."""
    r = dimensions.score_contact_fit("leasing@greystar.com", "Greystar")
    # 5 (corporate) + 5 (match) + 0 (generic) = 10
    assert r.points == 10
    assert any("Generic inbox" in s for s in r.reasons)


def test_contact_fit_invalid_email() -> None:
    r = dimensions.score_contact_fit("not-an-email", "Greystar")
    assert r.points == 0
