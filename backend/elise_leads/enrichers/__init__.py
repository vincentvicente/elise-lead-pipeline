"""Enrichment modules — populated in M2.

Each enricher takes a Lead and returns:
- raw API payload (stored in EnrichedData.<source>_json)
- list of Provenance records (one per fact extracted)
- ApiLog row(s) for audit
"""
