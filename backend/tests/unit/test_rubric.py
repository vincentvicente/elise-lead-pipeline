"""End-to-end tests for the v2 scoring rubric.

Each golden case is a (lead, enriched payload) → expected tier mapping
that exercises one specific behavior of the rubric. Failures here mean
the v2 weights don't produce sensible tiering for a documented scenario.
"""

from __future__ import annotations

import pytest

from elise_leads.scoring import rubric
from tests.fixtures.golden_cases import GOLDEN_CASES


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.name for c in GOLDEN_CASES])
def test_golden_case(case) -> None:
    result = rubric.score(case.lead, case.enriched)

    assert result.tier == case.expected_tier, (
        f"[{case.name}] expected tier={case.expected_tier} "
        f"got tier={result.tier}, total={result.total}\n"
        f"breakdown={result.breakdown}\n"
        f"reasons={result.reasons[:5]}"
    )

    if case.expected_total_min is not None:
        assert result.total >= case.expected_total_min, (
            f"[{case.name}] total={result.total} < min={case.expected_total_min}"
        )
    if case.expected_total_max is not None:
        assert result.total <= case.expected_total_max, (
            f"[{case.name}] total={result.total} > max={case.expected_total_max}"
        )

    if case.expected_disqualified:
        assert result.disqualified
        assert result.disqualifier_reason is not None
    else:
        # Non-disqualified cases should not flag a disqualifier
        assert not result.disqualified


def test_breakdown_keys_match_v2_weights() -> None:
    """Sanity check: the breakdown dict must contain exactly the 7 dimensions."""
    case = GOLDEN_CASES[0]
    r = rubric.score(case.lead, case.enriched)
    assert set(r.breakdown.keys()) == {
        "company_scale",
        "buy_intent",
        "vertical_fit",
        "market_fit",
        "property_fit",
        "market_dynamics",
        "contact_fit",
    }


def test_total_within_0_100() -> None:
    """Total must always be 0–100 for any case."""
    for case in GOLDEN_CASES:
        r = rubric.score(case.lead, case.enriched)
        assert 0 <= r.total <= 100, f"[{case.name}] total={r.total}"


def test_tier_thresholds_boundary() -> None:
    """75 = Hot, 74 = Warm, 55 = Warm, 54 = Cold."""
    assert rubric.compute_tier(75) == "Hot"
    assert rubric.compute_tier(74) == "Warm"
    assert rubric.compute_tier(55) == "Warm"
    assert rubric.compute_tier(54) == "Cold"
    assert rubric.compute_tier(0) == "Cold"
    assert rubric.compute_tier(100) == "Hot"


def test_reasons_include_dimension_label() -> None:
    """Reasons should be tagged with their dimension for SDR readability."""
    case = GOLDEN_CASES[0]  # Greystar Austin
    r = rubric.score(case.lead, case.enriched)
    # At least one reason from each dimension that contributed
    reason_text = " ".join(r.reasons)
    assert "[Company Scale]" in reason_text
    assert "[Buy Intent]" in reason_text
    assert "[Contact Fit]" in reason_text
