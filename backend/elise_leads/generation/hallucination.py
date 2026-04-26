"""Layer 3: Post-gen hallucination detection.

After Claude returns a draft, we verify every number and named entity
appears either in the verified facts we passed in or in the EliseAI
proof-point allowlist. Any unverified claim is a potential hallucination.

Severity classification (drives the regenerate vs warn decision):
- 'severe' — invented number or unverified third-party org name. The
  email is rejected and the LLM is asked to regenerate (max 2 retries).
- 'warning' — softer issue (e.g., generic time phrase like "last week"
  with no recent fact to back it). Recorded on the email but does not
  block.

Detection is intentionally conservative — we'd rather flag a few false
positives than ship a fabricated stat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from elise_leads.generation.prompts import PRODUCT_PROOF_POINTS

# Words/phrases that are always OK to mention (EliseAI's own canonical
# customer references and the product name itself). These never trigger
# unverified-org flags.
KNOWN_OK_TERMS: set[str] = set()
for _pp in PRODUCT_PROOF_POINTS.values():
    # Allow the customer name in each proof point quote
    _quote = _pp["quote"]
    # Pull the lead noun (e.g., "Equity Residential", "Asset Living", "Landmark")
    # by extracting all Capitalized Phrases from the quote.
    for _m in re.finditer(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", _quote):
        KNOWN_OK_TERMS.add(_m.group(0))
KNOWN_OK_TERMS.update(
    {
        # Product / company self-references
        "EliseAI", "Elise", "AI",
        # Industry org names that recur in EliseAI's positioning
        "NMHC", "Greystar", "AvalonBay", "Bozzuto",
        # B2B sales / role acronyms commonly appearing in outreach signatures
        "SDR", "AE", "VP", "CEO", "CMO", "COO", "CFO", "CTO",
        "BD", "BDR", "GTM", "RevOps", "CRM", "REIT", "REITs",
    }
)

# Numbers/figures that are always OK (canonical product proof points)
KNOWN_OK_NUMBERS: set[str] = set()
for _pp in PRODUCT_PROOF_POINTS.values():
    KNOWN_OK_NUMBERS.update(_pp.get("numeric_facts", []))
KNOWN_OK_NUMBERS.update({"600", "38", "50", "24", "3", "4"})  # generic small ints

# Common harmless time phrases. These trigger ONLY a warning, not a regen.
SOFT_TIME_PHRASES = (
    "last week",
    "yesterday",
    "this month",
    "recently",
    "just announced",
)


@dataclass
class HallucinationIssue:
    severity: str  # 'severe' | 'warning'
    category: str  # 'unverified_number' | 'unverified_org' | 'time_phrase' | ...
    detail: str


@dataclass
class HallucinationCheck:
    passed: bool          # True if NO severe issues
    issues: list[HallucinationIssue]
    severe_count: int
    warning_count: int

    @property
    def has_severe(self) -> bool:
        return self.severe_count > 0


# ----------------------------------------------------------------------------
# Number extraction & verification
# ----------------------------------------------------------------------------
# Match: digits with optional commas/decimals/percent/currency/units
_NUMBER_RE = re.compile(
    r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?[%KMB]?"  # 1,000 / 1,234.5 / $14M / 47.5%
    r"|\$?\d+\.\d+%?"                            # 47.5% / 14.5
    r"|\$?\d+[%KMB]"                             # $14M / 47%
    r"|\b\d{4,}\b",                              # standalone 4+ digit numbers
)


def _normalize_number(token: str) -> str:
    """Canonicalize a numeric token for comparison."""
    return token.replace("$", "").replace(",", "").replace(" ", "").lower()


def _facts_text_blob(verified_facts: list) -> str:
    """Flatten the verified facts list into one searchable text blob."""
    parts: list[str] = []
    for f in verified_facts:
        if isinstance(f, tuple):
            # (key, value, source, confidence)
            parts.append(str(f[1]))
        elif isinstance(f, dict):
            parts.extend(str(v) for v in f.values())
        else:
            parts.append(str(f))
    return " ".join(parts).lower()


def _check_numbers(
    body: str, fact_blob: str
) -> list[HallucinationIssue]:
    issues: list[HallucinationIssue] = []
    for m in _NUMBER_RE.finditer(body):
        token = m.group(0)
        norm = _normalize_number(token)
        # Allow if it appears in any verified fact text
        if norm in fact_blob.replace(",", "").replace("$", "").lower():
            continue
        # Allow if it's a canonical product number
        if any(_normalize_number(ok) == norm for ok in KNOWN_OK_NUMBERS):
            continue
        # Allow tiny standalone 1–3 digit ints (years, room counts) —
        # too noisy to flag and rarely fabricated stats
        digits = re.sub(r"[^\d]", "", token)
        if digits and len(digits) <= 3 and "%" not in token and "$" not in token:
            continue
        issues.append(
            HallucinationIssue(
                severity="severe",
                category="unverified_number",
                detail=f"Number '{token}' not present in verified_facts or proof points",
            )
        )
    return issues


# ----------------------------------------------------------------------------
# Entity extraction & verification
# ----------------------------------------------------------------------------
# Capitalized phrase: 2+ word proper-noun runs, OR all-caps acronyms.
# Kept simple to avoid spaCy / extra deps for MVP.
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}"   # Two-to-four word title-case
    r"|[A-Z]{2,5})\b"                               # Acronyms 2-5 chars
)

# Stopword phrases that look like entities but aren't (greetings, openers, signature)
_ENTITY_STOPWORDS = {
    "Hi", "Hello", "Hey", "Best", "Best Regards", "Thanks", "Thank You",
    "First Name", "SDR Name",
    "Subject", "Body",
    "Tuesday", "Monday", "Wednesday", "Thursday", "Friday",
    "Walk Score", "Walker", "Property Tract",  # leaked from facts
}


# When the FIRST word of a 2+ word capitalized match is one of these, it's
# almost always a sentence opener / greeting / sign-off / pronoun-led phrase
# rather than an actual organization name. Skipping these dramatically cuts
# false positives without weakening detection of fabricated customer names.
_SENTENCE_STARTERS = {
    # Greetings & sign-offs
    "hi", "hello", "hey", "dear", "best", "thanks", "thank", "regards",
    "sincerely", "cheers", "kind",
    # Pronouns
    "i", "we", "they", "you", "our", "your", "us", "their",
    # Common sentence-leading verbs
    "saw", "noticed", "looking", "looked", "found", "want", "wanted",
    "happy", "excited", "thought", "hoping", "would", "could", "might",
    "can", "may", "do", "does", "did", "should", "let", "seems",
    # Adjectives/quantifiers commonly leading sentences
    "the", "a", "an", "this", "these", "those", "that",
    "quick", "short", "brief", "great", "good", "new",
    "worth", "open", "given", "based",
}


def _check_entities(
    body: str,
    lead_company: str,
    fact_blob: str,
    proof_point_id: str,
) -> list[HallucinationIssue]:
    issues: list[HallucinationIssue] = []

    # Allowed: lead's own company + anything from facts + KNOWN_OK_TERMS +
    # the customer name from the recommended proof point
    pp_text = PRODUCT_PROOF_POINTS.get(proof_point_id, {}).get("quote", "")
    allowed_text = (
        fact_blob.lower()
        + " "
        + lead_company.lower()
        + " "
        + pp_text.lower()
    )

    seen: set[str] = set()
    for m in _ENTITY_RE.finditer(body):
        token = m.group(0)
        if token in _ENTITY_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        if token in KNOWN_OK_TERMS:
            continue
        if token.lower() in allowed_text:
            continue
        # Skip greetings / sentence-starters — first word is a common opener
        words = token.split()
        if words and words[0].lower() in _SENTENCE_STARTERS:
            continue
        # Allow individual capitalized words appearing in proof point quote
        any_word_in_pp = any(w.lower() in pp_text.lower() for w in words)
        if any_word_in_pp and len(words) == 1:
            continue
        issues.append(
            HallucinationIssue(
                severity="severe",
                category="unverified_org",
                detail=f"Entity '{token}' not in verified_facts or proof points",
            )
        )
    return issues


# ----------------------------------------------------------------------------
# Time-phrase check (soft warning only)
# ----------------------------------------------------------------------------
def _check_time_phrases(
    body: str, has_recent_news: bool
) -> list[HallucinationIssue]:
    if has_recent_news:
        return []
    body_lc = body.lower()
    issues: list[HallucinationIssue] = []
    for phrase in SOFT_TIME_PHRASES:
        if phrase in body_lc:
            issues.append(
                HallucinationIssue(
                    severity="warning",
                    category="time_phrase",
                    detail=(
                        f"Time reference '{phrase}' but no supporting recent "
                        "news fact"
                    ),
                )
            )
            break  # one is enough
    return issues


# ----------------------------------------------------------------------------
# Top-level entry
# ----------------------------------------------------------------------------
def detect(
    *,
    body: str,
    verified_facts: list,
    lead_company: str,
    proof_point_id: str,
    has_recent_news: bool,
) -> HallucinationCheck:
    """Run all three sub-checks and return the aggregated result."""
    fact_blob = _facts_text_blob(verified_facts)

    issues: list[HallucinationIssue] = []
    issues.extend(_check_numbers(body, fact_blob))
    issues.extend(_check_entities(body, lead_company, fact_blob, proof_point_id))
    issues.extend(_check_time_phrases(body, has_recent_news))

    severe = sum(1 for i in issues if i.severity == "severe")
    warnings = sum(1 for i in issues if i.severity == "warning")

    return HallucinationCheck(
        passed=severe == 0,
        issues=issues,
        severe_count=severe,
        warning_count=warnings,
    )


def to_db_payload(check: HallucinationCheck) -> dict[str, Any]:
    """Serialize a HallucinationCheck for the emails.hallucination_check JSON column."""
    return {
        "passed": check.passed,
        "severe_count": check.severe_count,
        "warning_count": check.warning_count,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "detail": i.detail,
            }
            for i in check.issues
        ],
    }
