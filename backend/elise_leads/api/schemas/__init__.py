"""Pydantic schemas for HTTP request/response.

Kept separate from SQLAlchemy ORM models so we can:
- Hide internal fields from the API surface
- Add UI-specific computed fields (e.g. days_since_published)
- Auto-generate stable OpenAPI types for the React frontend
"""

from elise_leads.api.schemas.feedback import FeedbackCreate, FeedbackOut
from elise_leads.api.schemas.lead import (
    LeadDetail,
    LeadListItem,
    LeadListResponse,
)
from elise_leads.api.schemas.metrics import (
    ApiPerformancePoint,
    KpiCard,
    OverviewResponse,
    TrendPoint,
)
from elise_leads.api.schemas.run import RunDetail, RunListItem, RunListResponse
from elise_leads.api.schemas.upload import UploadResponse

__all__ = [
    "ApiPerformancePoint",
    "FeedbackCreate",
    "FeedbackOut",
    "KpiCard",
    "LeadDetail",
    "LeadListItem",
    "LeadListResponse",
    "OverviewResponse",
    "RunDetail",
    "RunListItem",
    "RunListResponse",
    "TrendPoint",
    "UploadResponse",
]
