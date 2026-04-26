"""Rule-based proof-point selector (per PART_A v2 §11.1).

Maps a lead's enrichment profile to the single most relevant proof point
to cite in their email. Returning ONE proof point (not many) is critical:
- It forces the email to stay focused
- It prevents the LLM from synthesizing across multiple points and
  inventing new claims (Layer 2 hallucination defense)

Selection priority order (first match wins):
1. NMHC Top 10 OR M&A news    → equity_residential ($14M payroll)
2. Expansion/launch news       → asset_living (+300 bps occupancy)
3. Student housing keywords    → landmark_student
4. High renter density (>0.6)  → after_hours (47.5% messages)
5. Default / no signal         → nmhc_top_50 (38/50 social proof)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elise_leads.generation.prompts import PRODUCT_PROOF_POINTS


@dataclass
class ProofPointSelection:
    id: str
    quote: str
    rationale: str  # logged in DB for traceability


_STUDENT_KEYWORDS = ("student", "campus", "university", "college")


def select(
    *,
    lead_company: str,
    nmhc: dict[str, Any] | None,
    news: dict[str, Any] | None,
    census: dict[str, Any] | None,
) -> ProofPointSelection:
    """Choose the single best proof point for this lead."""
    company_lower = lead_company.lower()
    signals = (news or {}).get("signal_keywords", {}) or {}

    # Rule 1 — Tier-1 enterprise: NMHC Top 10 OR M&A news
    if nmhc and nmhc.get("matched") and nmhc.get("rank", 999) <= 10:
        return _make("equity_residential", "NMHC Top 10 operator → enterprise reference fits")
    if "high" in signals:
        return _make("equity_residential", "M&A news in last 30 days → enterprise reference")

    # Rule 2 — Expansion / new property
    if "medium_high" in signals:
        return _make("asset_living", "Expansion signal in news → operations-scaling reference")

    # Rule 3 — Student housing
    if any(kw in company_lower for kw in _STUDENT_KEYWORDS):
        return _make("landmark_student", "Student-housing keyword in company name")

    # Rule 4 — High renter density market → after-hours response pitch
    if census:
        acs = census.get("acs", {})
        renter = acs.get("renter_pct") if acs else None
        if renter and renter > 0.6:
            return _make(
                "after_hours",
                f"High renter density ({renter * 100:.0f}%) → urban after-hours pitch",
            )

    # Rule 5 — Default social proof
    return _make("nmhc_top_50", "No specific match → generic NMHC social proof")


def _make(proof_id: str, rationale: str) -> ProofPointSelection:
    if proof_id not in PRODUCT_PROOF_POINTS:
        raise ValueError(f"Unknown proof point id: {proof_id}")
    return ProofPointSelection(
        id=proof_id,
        quote=PRODUCT_PROOF_POINTS[proof_id]["quote"],
        rationale=rationale,
    )
