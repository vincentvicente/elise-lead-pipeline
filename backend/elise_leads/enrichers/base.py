"""Base types and protocol for all enrichers.

Each enricher takes a Lead (and optionally upstream data like geocoder
output) and returns an `EnrichmentResult` with:
- `data`        — the structured payload for EnrichedData.<source>_json
- `provenance`  — list of facts to persist (Layer 1 hallucination defense)
- `api_log`     — single per-call audit row for api_logs table
- `error`       — error_type string if the call failed (None on success)

Failures DO NOT raise; enrichers return `EnrichmentResult(data=None,
error="...")`. The orchestrator decides what to do with the failure
(score uses median fallback).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProvenanceFact:
    """One fact extracted from an API response.

    Mirrors the columns of the `provenance` table.
    """

    fact_key: str
    fact_value: Any
    source: str
    confidence: float
    raw_ref: str | None = None  # set by orchestrator if available


@dataclass
class ApiLogEntry:
    """One row destined for the `api_logs` table."""

    api_name: str
    started_at: datetime
    duration_ms: int
    http_status: int | None
    success: bool
    error_type: str | None = None
    error_detail: str | None = None


@dataclass
class EnrichmentResult:
    """Output from one enricher for one lead.

    `data` is the JSON payload stored in EnrichedData.<source>_json.
    `provenance` is the list of facts to write to the `provenance` table.
    `api_log` is the single audit row for this call.
    `error` is set to a short error_type string when the call failed
    (e.g., "rate_limit", "timeout"). When set, `data` is None.
    """

    data: dict[str, Any] | None
    provenance: list[ProvenanceFact] = field(default_factory=list)
    api_log: ApiLogEntry | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.data is not None


@runtime_checkable
class Enricher(Protocol):
    """Protocol every enricher must implement.

    `name` identifies the source for logging and provenance.
    `enrich(lead, ...)` returns an EnrichmentResult.

    Some enrichers depend on upstream data (Census ACS needs geocoder
    output, WalkScore needs lat/lon). Those enrichers accept extra kwargs
    documented in their concrete classes.
    """

    name: str

    async def enrich(self, lead: "LeadInput", **kwargs: Any) -> EnrichmentResult: ...


@dataclass
class LeadInput:
    """Lightweight read-only view of a Lead for enrichers.

    Decouples enrichers from SQLAlchemy ORM so they can be tested without
    a session. Built from a `Lead` row by the orchestrator.
    """

    name: str
    email: str
    company: str
    property_address: str
    city: str
    state: str
    country: str

    @property
    def full_address(self) -> str:
        return f"{self.property_address}, {self.city}, {self.state}"
