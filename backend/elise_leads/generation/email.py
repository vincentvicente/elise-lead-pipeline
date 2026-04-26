"""Top-level email generation — orchestrates the L1 → L2 → L4 fallback chain.

Per PART_A v2 §11.5:

    L1: tenacity retry inside Claude client (3x, automatic for transient)
       ↓ fails
    L2: switch to Haiku (same SDK, same prompt)
       ↓ fails / hallucination check fails after 2 regenerations
    L4: deterministic template (never silently fails)

L3 (post-gen hallucination check) lives between each LLM attempt: if the
draft fails the check with severe issues, we ask the same model to
regenerate (max 2 retries) before falling through to the next layer.

Returns an EmailDraft + list[ApiLogEntry] for DB persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elise_leads.enrichers.base import ApiLogEntry
from elise_leads.enrichers._http import log
from elise_leads.generation import hallucination, llm_client, prompts
from elise_leads.generation.proof_points import ProofPointSelection
from elise_leads.scoring.rubric import LeadScore
from elise_leads.settings import get_settings


@dataclass
class EmailDraft:
    """Final email + traceability metadata for the emails table."""

    subject: str
    body: str
    source: str  # 'llm:claude-sonnet-4-6' / 'llm:claude-haiku-4-5' / 'template_fallback'
    proof_point_used: str
    warnings: list[str] = field(default_factory=list)
    hallucination_check: dict[str, Any] = field(default_factory=dict)
    api_logs: list[ApiLogEntry] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Email validation (light checks, never blocks)
# ----------------------------------------------------------------------------
_BANNED_JARGON = (
    "synergy",
    "synergies",
    "leverage",
    "unlock",
    "game-changer",
    "game changer",
    "circle back",
    "low-hanging fruit",
    "move the needle",
)


def _validate_email(subject: str, body: str) -> list[str]:
    warnings: list[str] = []
    word_count = len(body.split())
    if word_count > 200:
        warnings.append(f"Body length {word_count} words (target 80–120)")
    if word_count < 50:
        warnings.append(f"Body too short ({word_count} words)")
    if "[SDR Name]" not in body:
        warnings.append("Missing [SDR Name] placeholder")
    body_lower = body.lower()
    for j in _BANNED_JARGON:
        if j in body_lower:
            warnings.append(f"Contains jargon: '{j}'")
    if len(subject) > 60:
        warnings.append(f"Subject too long ({len(subject)} chars)")
    return warnings


# ----------------------------------------------------------------------------
# Template fallback (L4) — used when all LLM attempts fail
# ----------------------------------------------------------------------------
_TEMPLATE_BODY = """Hi [First Name],

I noticed {company} manages properties in {city}. EliseAI helps multifamily
operators automate inbound leasing — answering prospects, scheduling tours,
and handling maintenance 24/7.

{proof_quote}

Would 15 min next week make sense to compare notes?

Best,
[SDR Name]"""


def _template_fallback(
    *, lead_first_name: str, lead_company: str, lead_city: str, proof_quote: str
) -> tuple[str, str]:
    subject = f"Quick question about {lead_company}"
    body = _TEMPLATE_BODY.format(
        company=lead_company,
        city=lead_city,
        proof_quote=proof_quote,
    )
    return subject, body


# ----------------------------------------------------------------------------
# Main generator
# ----------------------------------------------------------------------------
async def generate_email(
    *,
    lead_name: str,
    lead_email: str,
    lead_company: str,
    lead_property: str,
    lead_city: str,
    score: LeadScore,
    facts: list[tuple[str, Any, str, float]],
    proof: ProofPointSelection,
    has_recent_news: bool,
) -> EmailDraft:
    """Run the LLM cascade and return the final EmailDraft.

    The cascade:
      Sonnet (with up to 2 regenerations on hallucination)
      → Haiku (with up to 2 regenerations on hallucination)
      → Deterministic template
    """
    settings = get_settings()
    api_logs: list[ApiLogEntry] = []
    last_check: hallucination.HallucinationCheck | None = None

    user_prompt = prompts.render_user_prompt(
        lead_name=lead_name,
        lead_company=lead_company,
        lead_property=lead_property,
        facts=facts,
        score_total=score.total,
        score_tier=score.tier,
        top_reasons=score.reasons,
        recommended_proof_point_id=proof.id,
        recommended_proof_point_quote=proof.quote,
    )

    # Try primary then fallback model
    for model in (settings.llm_primary_model, settings.llm_fallback_model):
        for attempt in range(2):  # up to 2 regenerations per model
            attempt_user_prompt = user_prompt
            if attempt > 0:
                # Append regeneration directive — push the model away from
                # the prior hallucination
                attempt_user_prompt = (
                    user_prompt
                    + "\n\n<regeneration_note>The previous draft cited "
                    "facts not present in <verified_facts>. Please write "
                    "a fresh email using ONLY information explicitly stated "
                    "above. Do not invent customer names, statistics, or "
                    "events.</regeneration_note>"
                )
            try:
                resp = await llm_client.call_claude(
                    model=model,
                    system=prompts.SYSTEM_PROMPT,
                    user=attempt_user_prompt,
                )
                api_logs.append(resp.api_log)
            except Exception as exc:
                log.warning(
                    "email.llm_attempt_failed",
                    model=model,
                    attempt=attempt + 1,
                    error=type(exc).__name__,
                )
                continue  # next attempt or next model

            check = hallucination.detect(
                body=resp.body,
                verified_facts=facts,
                lead_company=lead_company,
                proof_point_id=proof.id,
                has_recent_news=has_recent_news,
            )
            last_check = check

            if check.passed:
                # Accept this draft
                warnings = _validate_email(resp.subject, resp.body)
                if check.warning_count > 0:
                    warnings.extend(
                        f"hallucination warning: {i.detail}"
                        for i in check.issues
                        if i.severity == "warning"
                    )
                return EmailDraft(
                    subject=resp.subject,
                    body=resp.body,
                    source=f"llm:{model}",
                    proof_point_used=proof.id,
                    warnings=warnings,
                    hallucination_check=hallucination.to_db_payload(check),
                    api_logs=api_logs,
                )
            # Severe issues — log and continue (next attempt or next model)
            log.warning(
                "email.hallucination_severe",
                model=model,
                attempt=attempt + 1,
                severe=check.severe_count,
            )

    # ----- L4: Template fallback -----
    log.warning(
        "email.fallback_to_template",
        last_check_severe=(last_check.severe_count if last_check else "n/a"),
    )
    first_name = lead_name.split()[0] if lead_name else "there"
    subject, body = _template_fallback(
        lead_first_name=first_name,
        lead_company=lead_company,
        lead_city=lead_city,
        proof_quote=proof.quote,
    )
    warnings = _validate_email(subject, body)
    warnings.insert(0, "LLM unavailable — used deterministic template")
    return EmailDraft(
        subject=subject,
        body=body,
        source="template_fallback",
        proof_point_used=proof.id,
        warnings=warnings,
        hallucination_check=(
            hallucination.to_db_payload(last_check) if last_check else {}
        ),
        api_logs=api_logs,
    )
