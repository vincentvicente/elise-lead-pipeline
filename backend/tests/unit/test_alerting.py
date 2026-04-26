"""Tests for the alerting layer.

Covers:
- Resend client invocation (mocked)
- Cooldown enforcement via alert_history table
- Failure tolerance (Resend errors should NOT raise)
- Markdown → HTML conversion
- Missing-config silent skip
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Set env BEFORE importing settings-using modules
os.environ.setdefault("RESEND_API_KEY", "test-resend-key")
os.environ.setdefault("ALERT_EMAIL", "alerts@example.com")

from elise_leads.alerting.client import md_to_html, send_alert
from elise_leads.alerting.rules import ALERT_RULES, get_rule
from elise_leads.models import AlertHistory
from elise_leads.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield


# ============================================================================
# Markdown → HTML
# ============================================================================
class TestMarkdownToHtml:
    def test_headings_convert(self) -> None:
        html = md_to_html("# H1\n## H2\n### H3")
        assert "<h1>H1</h1>" in html
        assert "<h2>H2</h2>" in html
        assert "<h3>H3</h3>" in html

    def test_bullet_list_wrapped_in_ul(self) -> None:
        html = md_to_html("- one\n- two\n- three")
        assert html.count("<ul>") == 1
        assert html.count("</ul>") == 1
        assert html.count("<li>") == 3

    def test_bold_inline(self) -> None:
        html = md_to_html("**critical** alert")
        assert "<strong>critical</strong>" in html

    def test_link_inline(self) -> None:
        html = md_to_html("[dashboard](https://x.com)")
        assert '<a href="https://x.com">dashboard</a>' in html

    def test_paragraph_default(self) -> None:
        html = md_to_html("just some text")
        assert "<p>just some text</p>" in html


# ============================================================================
# Rule lookup
# ============================================================================
class TestAlertRules:
    def test_known_keys_have_rules(self) -> None:
        assert "pipeline_crash" in ALERT_RULES
        assert "high_failure_rate" in ALERT_RULES

    def test_immediate_severity_has_zero_cooldown(self) -> None:
        r = get_rule("pipeline_crash")
        assert r.severity == "immediate"
        assert r.cooldown_seconds == 0

    def test_throttled_severity_has_positive_cooldown(self) -> None:
        r = get_rule("high_failure_rate")
        assert r.severity == "throttled"
        assert r.cooldown_seconds > 0

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError):
            get_rule("nonexistent_alert_key")


# ============================================================================
# send_alert behavior
# ============================================================================
class TestSendAlert:
    @pytest.mark.asyncio
    async def test_first_send_calls_resend_and_records_history(
        self, session: AsyncSession
    ) -> None:
        with patch("elise_leads.alerting.client.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock(return_value={"id": "re_xxx"})

            sent = await send_alert(
                session,
                alert_key="pipeline_crash",
                subject="Test crash",
                body_md="# crashed",
            )

            assert sent is True
            mock_resend.Emails.send.assert_called_once()
            call = mock_resend.Emails.send.call_args[0][0]
            assert call["to"] == "alerts@example.com"
            assert "[IMMEDIATE]" in call["subject"]
            assert "<h1>crashed</h1>" in call["html"]

        # alert_history row exists
        rows = (
            await session.execute(
                select(AlertHistory).where(AlertHistory.alert_key == "pipeline_crash")
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].count == 1

    @pytest.mark.asyncio
    async def test_second_send_within_cooldown_suppressed(
        self, session: AsyncSession
    ) -> None:
        # Pre-populate history with recent send
        session.add(
            AlertHistory(
                alert_key="high_failure_rate",
                severity="throttled",
                last_sent=datetime.now(timezone.utc) - timedelta(minutes=10),
                count=1,
            )
        )
        await session.commit()

        with patch("elise_leads.alerting.client.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock()

            sent = await send_alert(
                session,
                alert_key="high_failure_rate",
                subject="Failure rate high",
                body_md="# x",
            )

            assert sent is False
            mock_resend.Emails.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_immediate_severity_ignores_cooldown(
        self, session: AsyncSession
    ) -> None:
        """Pipeline crash always sends — never suppressed."""
        session.add(
            AlertHistory(
                alert_key="pipeline_crash",
                severity="immediate",
                last_sent=datetime.now(timezone.utc),  # just sent
                count=1,
            )
        )
        await session.commit()

        with patch("elise_leads.alerting.client.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock(return_value={"id": "re"})
            sent = await send_alert(
                session,
                alert_key="pipeline_crash",
                subject="x",
                body_md="x",
            )
            assert sent is True
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_resend_failure_does_not_raise(
        self, session: AsyncSession
    ) -> None:
        """Alerting bugs must never crash the pipeline."""
        with patch("elise_leads.alerting.client.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock(
                side_effect=RuntimeError("Resend down")
            )
            sent = await send_alert(
                session,
                alert_key="pipeline_crash",
                subject="x",
                body_md="x",
            )
            assert sent is False  # but no exception escaped

    @pytest.mark.asyncio
    async def test_missing_resend_key_skips_silently(
        self, session: AsyncSession
    ) -> None:
        # Override settings cache with empty key
        os.environ["RESEND_API_KEY"] = ""
        get_settings.cache_clear()
        try:
            sent = await send_alert(
                session,
                alert_key="pipeline_crash",
                subject="x",
                body_md="x",
            )
            assert sent is False
        finally:
            os.environ["RESEND_API_KEY"] = "test-resend-key"
            get_settings.cache_clear()
