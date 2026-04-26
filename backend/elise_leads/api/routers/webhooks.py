"""Inbound-lead webhook — production entry point for CRM integrations.

Accepts payloads from any system that can fire a webhook:
- Salesforce flows / Process Builder / Apex outbound message
- HubSpot Workflows
- Pipedrive automations
- Zapier / n8n / Make scenarios
- Raw form submissions on the EliseAI marketing site

Same outcome as the CSV upload route: writes a `Lead` row with
`status='pending'`. The next cron run (or a manual trigger from the
dashboard) processes it through the standard pipeline.

The schema is CRM-agnostic — we only require the 7 lead fields. Optional
`source` and `external_id` fields preserve traceability to the upstream
system without coupling the schema to any vendor.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.api.deps import get_session
from elise_leads.enrichers._http import log
from elise_leads.models import Lead

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class InboundWebhookPayload(BaseModel):
    """Generic inbound-lead webhook body.

    Field naming uses CRM-conventional prefixes (`contact_*`, `company`,
    `property_*`) so a Salesforce/HubSpot workflow can map directly without
    extra glue code.
    """

    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr
    company: str = Field(min_length=1, max_length=200)
    property_address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(default="US", max_length=50)

    # Optional traceability — logged but not (yet) persisted.
    source: str | None = Field(
        default=None,
        max_length=100,
        description="Upstream system identifier (e.g. 'salesforce_flow_inbound_form')",
    )
    external_id: str | None = Field(
        default=None,
        max_length=100,
        description="CRM record id for cross-system join (e.g. SFDC Lead Id)",
    )


class WebhookAck(BaseModel):
    status: str
    lead_id: str
    will_process: str


@router.post(
    "/inbound",
    response_model=WebhookAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generic inbound-lead webhook (Salesforce / HubSpot / Zapier)",
)
async def inbound_webhook(
    payload: InboundWebhookPayload,
    session: AsyncSession = Depends(get_session),
) -> WebhookAck:
    """Persist a pending lead from a CRM webhook payload.

    Returns 202 Accepted with the new `lead_id`. The lead is processed by
    the next scheduled or manually-triggered pipeline run.
    """
    lead = Lead(
        name=payload.contact_name,
        email=str(payload.contact_email),
        company=payload.company,
        property_address=payload.property_address,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        status="pending",
    )
    session.add(lead)
    await session.flush()

    log.info(
        "webhook.inbound.received",
        lead_id=str(lead.id),
        source=payload.source,
        external_id=payload.external_id,
        company=payload.company,
    )

    return WebhookAck(
        status="received",
        lead_id=str(lead.id),
        will_process="next cron run or manual trigger",
    )
