"""Async Claude client wrapper.

Centralizes:
- Throttling (1.3s between calls — keeps us under Tier 1 RPM limit of 50)
- Retry on rate-limit / 5xx (tenacity exponential backoff)
- XML response parsing (subject + body)
- ApiLogEntry construction so the caller can persist audit rows

Caller-facing API:
- async call_claude(model, system, user) -> ClaudeResponse
- Both strings and ApiLogEntry returned for end-to-end traceability
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from elise_leads.enrichers.base import ApiLogEntry
from elise_leads.enrichers._http import log
from elise_leads.settings import get_settings

# ----------------------------------------------------------------------------
# Throttle state — module-level so it works across all callers in one process
# ----------------------------------------------------------------------------
_throttle_lock = asyncio.Lock()
_last_call_at: float = 0.0


# ----------------------------------------------------------------------------
# Module-level shared client
# ----------------------------------------------------------------------------
_CLIENT: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = get_settings().anthropic_api_key
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — cannot call Claude. "
                "Set it in .env or fall back to the deterministic template."
            )
        _CLIENT = AsyncAnthropic(api_key=api_key)
    return _CLIENT


def reset_client() -> None:
    """Test helper — drops the cached client so tests can monkeypatch fresh."""
    global _CLIENT
    _CLIENT = None


# ----------------------------------------------------------------------------
# Response dataclass
# ----------------------------------------------------------------------------
@dataclass
class ClaudeResponse:
    raw_text: str
    subject: str
    body: str
    model: str
    api_log: ApiLogEntry


# ----------------------------------------------------------------------------
# XML parsing
# ----------------------------------------------------------------------------
_SUBJECT_RE = re.compile(r"<subject>(.*?)</subject>", re.DOTALL | re.IGNORECASE)
_BODY_RE = re.compile(r"<body>(.*?)</body>", re.DOTALL | re.IGNORECASE)


def parse_xml_response(text: str) -> tuple[str, str]:
    """Extract <subject> and <body> XML elements from Claude's response.

    Raises ValueError if either tag is missing — that signals the model
    didn't follow the output format and we should treat as a generation
    failure (fallback chain kicks in).
    """
    sub_m = _SUBJECT_RE.search(text)
    body_m = _BODY_RE.search(text)
    if not sub_m or not body_m:
        raise ValueError(
            f"Claude response missing <subject>/<body> XML tags. Got: {text[:200]}"
        )
    return sub_m.group(1).strip(), body_m.group(1).strip()


# ----------------------------------------------------------------------------
# Throttle (max ~46 RPM = 1.3s between calls)
# ----------------------------------------------------------------------------
async def _throttle() -> None:
    global _last_call_at
    settings = get_settings()
    interval = settings.llm_throttle_seconds
    async with _throttle_lock:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        _last_call_at = time.monotonic()


# ----------------------------------------------------------------------------
# Inner retry-wrapped call
# ----------------------------------------------------------------------------
@retry(
    retry=retry_if_exception_type(
        (RateLimitError, APITimeoutError, APIConnectionError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2.0, max=30.0),
    reraise=True,
)
async def _call_inner(model: str, system: str, user: str, max_tokens: int) -> str:
    client = get_client()
    msg = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if not msg.content:
        raise ValueError("Empty response from Claude")
    # Grab the first text block
    for block in msg.content:
        if hasattr(block, "text"):
            return block.text
    raise ValueError("No text block in Claude response")


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
async def call_claude(
    model: str,
    system: str,
    user: str,
    max_tokens: int | None = None,
) -> ClaudeResponse:
    """Throttled + retried call to Claude with structured response parsing.

    Returns a ClaudeResponse with parsed subject + body. Raises if the
    model is unreachable, returns malformed XML, or hits non-retriable
    API errors (e.g., bad request).
    """
    settings = get_settings()
    if max_tokens is None:
        max_tokens = settings.llm_max_tokens

    await _throttle()

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    api_log = ApiLogEntry(
        api_name=f"claude:{model}",
        started_at=started_at,
        duration_ms=0,
        http_status=None,
        success=False,
    )

    try:
        raw = await _call_inner(model, system, user, max_tokens)
        subject, body = parse_xml_response(raw)
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.http_status = 200
        api_log.success = True
        return ClaudeResponse(
            raw_text=raw, subject=subject, body=body, model=model, api_log=api_log
        )
    except RateLimitError as e:
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.error_type = "rate_limit"
        api_log.error_detail = str(e)[:500]
        log.warning("claude.rate_limit", model=model)
        raise
    except (APIConnectionError, APITimeoutError) as e:
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.error_type = "network"
        api_log.error_detail = str(e)[:500]
        log.warning("claude.network", model=model, error=str(e))
        raise
    except APIStatusError as e:
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.http_status = e.status_code
        api_log.error_type = f"http_{e.status_code}"
        api_log.error_detail = str(e)[:500]
        raise
    except ValueError as e:
        # XML parse error or empty content
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.error_type = "parse_error"
        api_log.error_detail = str(e)[:500]
        raise
