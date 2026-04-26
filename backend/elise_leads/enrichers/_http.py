"""Shared HTTP utilities for enrichers.

Provides:
- `get_http_client()` — module-level async httpx.AsyncClient with
  reasonable timeouts and a polite User-Agent
- `timed_get()` — wrapper that measures duration and returns an ApiLogEntry
- `RETRY_ON_TRANSIENT` — tenacity decorator for 5xx/timeout retries only
  (NOT 4xx; those mean we sent bad params and retrying won't help)
- A simple structlog logger configured for the project
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from elise_leads.enrichers.base import ApiLogEntry
from elise_leads.settings import get_settings

# ----------------------------------------------------------------------------
# Logging — configure once at import time
# ----------------------------------------------------------------------------
_log_level = getattr(logging, get_settings().log_level)
logging.basicConfig(level=_log_level, format="%(message)s")

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


# ----------------------------------------------------------------------------
# HTTP client
# ----------------------------------------------------------------------------
_HTTP_CLIENT: httpx.AsyncClient | None = None

USER_AGENT = (
    "EliseAI-Lead-Enricher/0.1 "
    "(+https://github.com/eliseai/lead-pipeline; gtm@elise.ai)"
)


def get_http_client() -> httpx.AsyncClient:
    """Lazy-init module-level async client.

    Reused across enrichers to share connection pooling. Closed via
    `close_http_client()` at app shutdown (handled by FastAPI lifespan
    or explicitly in the cron entry point).
    """
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _HTTP_CLIENT


async def close_http_client() -> None:
    """Close the shared async client. Safe to call multiple times."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
        await _HTTP_CLIENT.aclose()
    _HTTP_CLIENT = None


# ----------------------------------------------------------------------------
# Retry decorator — transient failures only (5xx, timeouts, network)
# ----------------------------------------------------------------------------
RETRY_ON_TRANSIENT = retry(
    retry=retry_if_exception_type(
        (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=4.0),
    reraise=True,
)


# ----------------------------------------------------------------------------
# Convenience wrapper that measures duration and emits an ApiLogEntry
# ----------------------------------------------------------------------------
@asynccontextmanager
async def timed_call(api_name: str):
    """Context manager that measures elapsed time and builds an ApiLogEntry.

    The `api_log` is created EAGERLY (at yield time) and mutated in place
    by the finally block. This means callers can `return ctx["api_log"]`
    safely from inside the `async with` block — when control reaches the
    return statement, the finally has already populated `duration_ms`,
    `http_status`, etc. via in-place mutation.

    Usage:
        async with timed_call("census_geocoder") as ctx:
            response = await client.get(...)
            ctx["status"] = response.status_code
            ctx["success"] = True
            return EnrichmentResult(..., api_log=ctx["api_log"])
            # finally fires here and mutates ctx["api_log"] in place
    """
    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    # Pre-build the log object so it's referenceable even before finally
    api_log = ApiLogEntry(
        api_name=api_name,
        started_at=started_at,
        duration_ms=0,
        http_status=None,
        success=False,
    )
    ctx: dict[str, Any] = {
        "status": None,
        "success": False,
        "error_type": None,
        "error_detail": None,
        "api_log": api_log,
    }
    try:
        yield ctx
    finally:
        # Mutate the shared object in place so any caller-held reference
        # sees the final values.
        api_log.duration_ms = int((time.perf_counter() - t0) * 1000)
        api_log.http_status = ctx.get("status")
        api_log.success = bool(ctx.get("success"))
        api_log.error_type = ctx.get("error_type")
        api_log.error_detail = ctx.get("error_detail")


def classify_http_error(exc: Exception, status: int | None = None) -> str:
    """Map an exception/status to a stable error_type string."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return "network"
    if status is not None:
        if status == 429:
            return "rate_limit"
        if 400 <= status < 500:
            return f"http_{status}"
        if 500 <= status < 600:
            return "http_5xx"
    return "unknown"
