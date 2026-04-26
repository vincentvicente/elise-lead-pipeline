"""Simulate a CRM (Salesforce/HubSpot/Zapier) firing inbound-lead webhooks.

Run via:
    uv run python -m scripts.simulate_crm_webhook
    uv run python -m scripts.simulate_crm_webhook --base http://localhost:8000

What it does:
- POSTs three realistic payloads to /api/v1/webhooks/inbound
- Each payload mimics a different upstream CRM's field shape (after the
  Salesforce/HubSpot Workflow has mapped them to our generic schema)
- Prints the resulting lead_ids so you can see them appear in the
  dashboard's pending list

This is the "production entry point" for inbound leads. The CSV upload
in the dashboard is the same shape under a different transport.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

# Three realistic payloads — same target schema, each tagged with its
# pretend upstream so the demo can show traceability.
PAYLOADS: list[dict] = [
    {
        "contact_name": "Marcus Tate",
        "contact_email": "marcus.tate@rpmliving.com",
        "company": "RPM Living",
        "property_address": "555 Market Plaza",
        "city": "Austin",
        "state": "TX",
        "country": "US",
        "source": "salesforce_flow:inbound_demo_request",
        "external_id": "0034x000003BCDEFG",
    },
    {
        "contact_name": "Priya Desai",
        "contact_email": "priya@bhmanagement.com",
        "company": "BH Management Services",
        "property_address": "910 Lincoln Way",
        "city": "Des Moines",
        "state": "IA",
        "country": "US",
        "source": "hubspot_workflow:contact_form_submission",
        "external_id": "hs_98341",
    },
    {
        "contact_name": "Devin Park",
        "contact_email": "devin.park@willowbridge.com",
        "company": "Willow Bridge Property Company",
        "property_address": "212 Oak Lawn",
        "city": "Dallas",
        "state": "TX",
        "country": "US",
        "source": "zapier:typeform_inbound",
        "external_id": "tf_abc123",
    },
]


def fire(base: str) -> int:
    url = f"{base.rstrip('/')}/api/v1/webhooks/inbound"
    print(f"\n→ POSTing {len(PAYLOADS)} webhooks to {url}\n")

    failures = 0
    for i, payload in enumerate(PAYLOADS, start=1):
        try:
            r = httpx.post(url, json=payload, timeout=10.0)
        except httpx.HTTPError as e:
            print(f"  [{i}] ✗ network error: {e}")
            failures += 1
            continue

        line_prefix = f"  [{i}] {payload['source']:<48}"
        if r.status_code == 202:
            body = r.json()
            print(f"{line_prefix} → 202 lead_id={body['lead_id'][:8]}…")
        else:
            failures += 1
            print(f"{line_prefix} → {r.status_code} {r.text[:120]}")

    print(
        f"\n{len(PAYLOADS) - failures}/{len(PAYLOADS)} webhooks accepted. "
        "Open http://localhost:5173/leads?status=pending to see them."
    )
    return 0 if failures == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base",
        default="http://localhost:8000",
        help="Backend base URL (default: %(default)s)",
    )
    p.add_argument(
        "--print-payloads",
        action="store_true",
        help="Print the JSON payloads without sending",
    )
    args = p.parse_args()

    if args.print_payloads:
        print(json.dumps(PAYLOADS, indent=2))
        return 0

    return fire(args.base)


if __name__ == "__main__":
    sys.exit(main())
