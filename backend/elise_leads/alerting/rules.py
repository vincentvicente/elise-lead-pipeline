"""Alert rule configuration.

Two severity tiers per PART_A v2 §13.2:
- 'immediate' — pipeline crash / all leads failed (no cooldown)
- 'throttled' — high failure rate / quota exhausted (1h cooldown)

Cooldowns prevent spamming the inbox during retry storms or recurring
intermittent issues. The dedup state is stored in the Postgres
`alert_history` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["immediate", "throttled"]


@dataclass(frozen=True)
class AlertRule:
    severity: Severity
    cooldown_seconds: int


# Cooldown windows
_NO_COOLDOWN = 0
_HOUR = 3600
_DAY = 86400


ALERT_RULES: dict[str, AlertRule] = {
    # Pipeline-level critical failures
    "pipeline_crash": AlertRule("immediate", _NO_COOLDOWN),
    "all_leads_failed": AlertRule("immediate", _NO_COOLDOWN),
    # Throttled operational alerts
    "high_failure_rate": AlertRule("throttled", _HOUR),
    "newsapi_quota_exhausted": AlertRule("throttled", _DAY),
    "claude_rate_limit_burst": AlertRule("throttled", _HOUR),
    "no_pending_leads": AlertRule("throttled", _DAY),
}


def get_rule(alert_key: str) -> AlertRule:
    """Return the rule for an alert key. Raises KeyError if unknown."""
    if alert_key not in ALERT_RULES:
        raise KeyError(
            f"Unknown alert_key '{alert_key}' — add to ALERT_RULES in rules.py"
        )
    return ALERT_RULES[alert_key]
