"""Prompt templates — Layer 2 of the hallucination defense.

The system prompt is static (cached at import time). It establishes:
- The SDR persona at EliseAI
- Hard-coded product proof points the model is allowed to cite
- Email writing rules (length, tone, banned jargon, no fake stats)
- XML output format the parser expects

The user prompt is rendered per-lead. It carries:
- <verified_facts> — every fact tagged with source + confidence
- <lead_score> — score breakdown + top reasons
- <recommended_proof_point> — pre-selected by rule (proof_points.py)
- <instructions> — explicit "use ONLY verified_facts" directive

The grounding rules tell the model:
- Cite specific numbers ONLY for confidence ≥ 0.85 facts
- For lower confidence, mention the topic but never the figure
- Never invent customers / events / partnerships

Confidence ranges (per provenance.confidence column):
- 0.95+ — government data (Census, FRED, NMHC list)
- 0.85+ — premium news sources (WSJ, Bloomberg)
- 0.70  — Wikipedia (crowd-sourced, may be stale)
- 0.65  — text-extracted scale numbers (regex-derived)
"""

from __future__ import annotations

from typing import Any

# Pre-defined customer-success references the model may cite.
# IMPORTANT: each `id` matches the keys returned by proof_points.select(),
# and the `quote` text is the only customer-citation form the model is
# permitted to use. The post-gen check verifies every number/name in the
# generated email appears either in <verified_facts> or in this set.
PRODUCT_PROOF_POINTS: dict[str, dict[str, Any]] = {
    "equity_residential": {
        "best_for": "large enterprise REITs and national portfolios",
        "quote": (
            "Equity Residential — one of the largest publicly-traded multifamily "
            "REITs — saved $14M in payroll by automating leasing conversations "
            "with EliseAI."
        ),
        "numeric_facts": ["$14M"],
    },
    "asset_living": {
        "best_for": "mid-to-large operators scaling operations",
        "quote": (
            "Asset Living, managing 450,000+ units, saw +300 bps occupancy and "
            "+600 bps on-time rent in Q2 2025 after deploying EliseAI."
        ),
        "numeric_facts": ["450,000", "300 bps", "600 bps"],
    },
    "after_hours": {
        "best_for": "urban high-velocity leasing markets",
        "quote": (
            "47.5% of leasing inquiries arrive outside business hours — EliseAI "
            "answers all of them via voice, SMS, email, and chat."
        ),
        "numeric_facts": ["47.5%"],
    },
    "landmark_student": {
        "best_for": "student housing operators",
        "quote": (
            "Landmark Properties runs EliseAI across 100+ student housing "
            "communities, lifting occupancy while cutting leasing-team load."
        ),
        "numeric_facts": ["100"],
    },
    "nmhc_top_50": {
        "best_for": "generic social proof when no specific fit",
        "quote": "Trusted by 38 of the NMHC Top 50 multifamily operators.",
        "numeric_facts": ["38", "50"],
    },
}


# ----------------------------------------------------------------------------
# System prompt — ~500 tokens (per PART_A v2 §11.2)
# ----------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an SDR at EliseAI, an AI leasing assistant used by 600+ multifamily \
operators including Greystar, AvalonBay, and Bozzuto. Your job: write a personalized \
cold outreach email for a new inbound lead.

<product>
EliseAI automates inbound leasing across voice, SMS, email, and chat — answering \
prospects, scheduling tours, handling maintenance 24/7.

You may reference ONLY the proof point passed in <recommended_proof_point> in the \
user message. Do not mix multiple proof points or invent additional customer names \
or numbers.
</product>

<email_rules>
- Length: 80–120 words. 3 short paragraphs.
- Opening (1 sentence): reference ONE specific detail from <verified_facts>. Prove \
you researched.
- Middle (2–3 sentences): use the <recommended_proof_point> to tie value to their \
situation. Tie it to a real customer outcome from <product>.
- Closing (1 sentence): low-friction CTA — "Would 15 min next Tuesday work?" or \
"Worth a quick reply?"
- Tone: professional, warm, confident.
- Cite specific numbers ONLY when the fact has confidence ≥ 0.85 in \
<verified_facts>. For lower confidence, you may mention the topic but never the \
figure.
- NEVER invent stats, customer names, partnerships, or features.
- If a fact is marked "do not cite specific numbers", obey.
- If <verified_facts> is sparse, use industry/market angle without inventing.
- No emojis. No jargon (leverage / synergy / unlock / game-changer). No fake urgency.
- Sign off as "[SDR Name]" (literal placeholder; do not invent a name).
</email_rules>

<output_format>
Return EXACTLY this XML structure, nothing else:
<subject>One specific line, under 45 characters</subject>
<body>
Hi [First Name],

[paragraph 1 — specific hook from verified_facts]

[paragraph 2 — recommended proof point, tied to their situation]

Best,
[SDR Name]
</body>
</output_format>"""


# ----------------------------------------------------------------------------
# User prompt template
# ----------------------------------------------------------------------------
def render_fact(fact_key: str, fact_value: Any, source: str, confidence: float) -> str:
    """Render one provenance fact as an XML <fact> element."""
    note = ""
    if confidence < 0.85:
        note = " <note>Confidence < 0.85 — do NOT cite specific numbers from this fact.</note>"
    return (
        f'  <fact source="{source}" confidence="{confidence:.2f}">\n'
        f"    {fact_key}: {fact_value}{note}\n"
        f"  </fact>"
    )


def render_user_prompt(
    *,
    lead_name: str,
    lead_company: str,
    lead_property: str,
    facts: list[tuple[str, Any, str, float]],  # (key, value, source, confidence)
    score_total: int,
    score_tier: str,
    top_reasons: list[str],
    recommended_proof_point_id: str,
    recommended_proof_point_quote: str,
) -> str:
    """Render a per-lead user prompt for Claude.

    Facts are filtered/sorted by confidence (highest first) before being
    passed in. The model treats <verified_facts> as the only allowed source
    of citable information.
    """
    if facts:
        facts_xml = "\n".join(render_fact(*f) for f in facts)
    else:
        facts_xml = "  <!-- no high-confidence facts available; use product/proof_point only -->"

    reasons_block = "\n".join(f"  - {r}" for r in top_reasons[:5])

    return f"""<lead>
  Name: {lead_name}
  Company: {lead_company}
  Property: {lead_property}
</lead>

<verified_facts>
{facts_xml}
</verified_facts>

<lead_score>
  Score: {score_total}/100 (tier: {score_tier})
  Top signals (most relevant first):
{reasons_block}
</lead_score>

<recommended_proof_point id="{recommended_proof_point_id}">
{recommended_proof_point_quote}
</recommended_proof_point>

<instructions>
Use ONLY the <recommended_proof_point> above. Do NOT mix in other proof points
from your training. Do NOT cite numbers absent from <verified_facts> or
<recommended_proof_point>. If verified_facts is sparse, write a generic but
honest email referencing only what's stated.
</instructions>"""
