"""Alerting via Resend — populated in M5.

Two severity tiers:
- 'immediate' — pipeline crash, all-leads-failed (no cooldown)
- 'throttled' — high failure rate, quota exhausted (1h cooldown)

Dedup state lives in `alert_history` table.
"""
