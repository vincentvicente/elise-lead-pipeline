"""Resend alerting client with Postgres-backed dedup.

The send_alert() function:
1. Looks up the alert_key in `alert_history` to check cooldown
2. If outside cooldown, sends the email via Resend
3. Records the send in `alert_history` (insert or update last_sent + count)

Critical reliability decisions:
- Failures inside Resend NEVER bubble out — they're logged but the
  pipeline continues (alert system is not on the critical path)
- If Resend or alert_email is unconfigured, send_alert() returns silently
  and only logs (so dev / test environments don't crash)
- The dedup write happens AFTER successful send, so a failed send won't
  set the cooldown clock (you'll get a retry on the next event)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.alerting.rules import ALERT_RULES, get_rule
from elise_leads.enrichers._http import log
from elise_leads.models import AlertHistory
from elise_leads.settings import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------
# Lightweight Markdown → HTML converter
# ----------------------------------------------------------------------------
# Resend can send raw HTML. We avoid pulling in `markdown` lib for this MVP
# and just do the most-common transforms our alert templates need.
def md_to_html(md: str) -> str:
    """Tiny markdown→HTML for alert emails. Supports headings, lists, bold,
    inline code, and links. Anything else falls through as <p> blocks.
    """
    html_lines: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue
        # Headings
        if line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{line[4:]}</h3>")
            continue
        if line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
            continue
        if line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{line[2:]}</h1>")
            continue
        # Lists
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        # Plain paragraph
        html_lines.append(f"<p>{_inline(line)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
async def send_alert(
    session: AsyncSession,
    alert_key: str,
    subject: str,
    body_md: str,
    *,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Try to send an alert. Returns True if delivered, False if suppressed/skipped.

    `alert_key` must be defined in ALERT_RULES (rules.py). Cooldowns are
    enforced via the alert_history table.

    `body_md` is plain markdown — converted to HTML for delivery.
    """
    rule = get_rule(alert_key)
    settings = get_settings()

    # Dedup check
    history = (
        await session.execute(
            select(AlertHistory).where(AlertHistory.alert_key == alert_key)
        )
    ).scalar_one_or_none()

    if history is not None and rule.cooldown_seconds > 0:
        # SQLite strips tzinfo on round-trip; normalize to UTC if naive
        last_sent = history.last_sent
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = _utcnow() - last_sent
        if elapsed < timedelta(seconds=rule.cooldown_seconds):
            log.info(
                "alert.suppressed_cooldown",
                alert_key=alert_key,
                elapsed_s=int(elapsed.total_seconds()),
                cooldown_s=rule.cooldown_seconds,
            )
            return False

    # Configuration guard — skip silently if alerting isn't configured
    if not settings.resend_api_key or not settings.alert_email:
        log.warning(
            "alert.no_config",
            alert_key=alert_key,
            reason="RESEND_API_KEY or ALERT_EMAIL missing",
        )
        return False

    # Send
    try:
        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.alert_from_address,
                "to": settings.alert_email,
                "subject": f"[{rule.severity.upper()}] {subject}",
                "html": md_to_html(body_md),
            }
        )
        log.info("alert.sent", alert_key=alert_key, severity=rule.severity)
    except Exception as exc:
        # Alerting must NEVER crash the pipeline. Log and return.
        log.error(
            "alert.send_failed",
            alert_key=alert_key,
            error=type(exc).__name__,
            detail=str(exc)[:300],
        )
        return False

    # Record dedup state
    if history is None:
        session.add(
            AlertHistory(
                alert_key=alert_key,
                severity=rule.severity,
                last_sent=_utcnow(),
                count=1,
            )
        )
    else:
        history.last_sent = _utcnow()
        history.count = (history.count or 0) + 1
    await session.commit()

    return True


# ----------------------------------------------------------------------------
# Helper — quick access from pipeline / cron without full module imports
# ----------------------------------------------------------------------------
def list_known_alert_keys() -> list[str]:
    return sorted(ALERT_RULES.keys())
