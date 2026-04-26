"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24 12:00:00.000000

Creates the full M1 schema: runs, leads, enriched_data, provenance,
scores, emails, feedback, api_logs, alert_history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from elise_leads.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lead_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("report_md", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )

    # ------------------------------------------------------------------
    # leads
    # ------------------------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("property_address", sa.String(length=500), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_leads_run_id_runs", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
    )
    op.create_index("ix_leads_run_id", "leads", ["run_id"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_company", "leads", ["company"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_status_uploaded", "leads", ["status", "uploaded_at"])

    # ------------------------------------------------------------------
    # enriched_data
    # ------------------------------------------------------------------
    op.create_table(
        "enriched_data",
        sa.Column("lead_id", GUID(), nullable=False),
        sa.Column("census_json", sa.JSON(), nullable=True),
        sa.Column("news_json", sa.JSON(), nullable=True),
        sa.Column("wiki_json", sa.JSON(), nullable=True),
        sa.Column("walkscore_json", sa.JSON(), nullable=True),
        sa.Column("fred_json", sa.JSON(), nullable=True),
        sa.Column("nmhc_json", sa.JSON(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name="fk_enriched_data_lead_id_leads",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lead_id", name="pk_enriched_data"),
    )

    # ------------------------------------------------------------------
    # provenance
    # ------------------------------------------------------------------
    op.create_table(
        "provenance",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("lead_id", GUID(), nullable=False),
        sa.Column("fact_key", sa.String(length=100), nullable=False),
        sa.Column("fact_value", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_ref", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name="fk_provenance_lead_id_leads", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provenance"),
    )
    op.create_index("ix_provenance_lead_key", "provenance", ["lead_id", "fact_key"])

    # ------------------------------------------------------------------
    # scores
    # ------------------------------------------------------------------
    op.create_table(
        "scores",
        sa.Column("lead_id", GUID(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=10), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total >= 0 AND total <= 100", name="ck_scores_total_in_range"),
        sa.CheckConstraint("tier IN ('Hot', 'Warm', 'Cold')", name="ck_scores_tier_enum"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name="fk_scores_lead_id_leads", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("lead_id", name="pk_scores"),
    )
    op.create_index("ix_scores_tier", "scores", ["tier"])

    # ------------------------------------------------------------------
    # emails
    # ------------------------------------------------------------------
    op.create_table(
        "emails",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("lead_id", GUID(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("hallucination_check", sa.JSON(), nullable=False),
        sa.Column("proof_point_used", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name="fk_emails_lead_id_leads", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_emails"),
        sa.UniqueConstraint("lead_id", name="uq_emails_lead_id"),
    )

    # ------------------------------------------------------------------
    # feedback
    # ------------------------------------------------------------------
    op.create_table(
        "feedback",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("email_id", GUID(), nullable=False),
        sa.Column("sdr_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("final_subject", sa.String(length=500), nullable=True),
        sa.Column("final_body", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("review_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('approved', 'edited', 'rejected')",
            name="ck_feedback_action_enum",
        ),
        sa.CheckConstraint(
            "review_seconds >= 0", name="ck_feedback_review_seconds_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["emails.id"], name="fk_feedback_email_id_emails", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
    )
    op.create_index("ix_feedback_email_id", "feedback", ["email_id"])
    op.create_index("ix_feedback_sdr_email", "feedback", ["sdr_email"])
    op.create_index("ix_feedback_action", "feedback", ["action"])

    # ------------------------------------------------------------------
    # api_logs
    # ------------------------------------------------------------------
    op.create_table(
        "api_logs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("lead_id", GUID(), nullable=True),
        sa.Column("api_name", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=50), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name="fk_api_logs_lead_id_leads", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_api_logs_run_id_runs", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_logs"),
    )
    op.create_index("ix_api_logs_run_id", "api_logs", ["run_id"])
    op.create_index("ix_api_logs_lead_id", "api_logs", ["lead_id"])
    op.create_index("ix_api_logs_api_name", "api_logs", ["api_name"])
    op.create_index("ix_api_logs_success", "api_logs", ["success"])
    op.create_index("ix_api_logs_api_started", "api_logs", ["api_name", "started_at"])

    # ------------------------------------------------------------------
    # alert_history
    # ------------------------------------------------------------------
    op.create_table(
        "alert_history",
        sa.Column("alert_key", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("last_sent", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("alert_key", name="pk_alert_history"),
    )


def downgrade() -> None:
    op.drop_table("alert_history")
    op.drop_index("ix_api_logs_api_started", table_name="api_logs")
    op.drop_index("ix_api_logs_success", table_name="api_logs")
    op.drop_index("ix_api_logs_api_name", table_name="api_logs")
    op.drop_index("ix_api_logs_lead_id", table_name="api_logs")
    op.drop_index("ix_api_logs_run_id", table_name="api_logs")
    op.drop_table("api_logs")
    op.drop_index("ix_feedback_action", table_name="feedback")
    op.drop_index("ix_feedback_sdr_email", table_name="feedback")
    op.drop_index("ix_feedback_email_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_table("emails")
    op.drop_index("ix_scores_tier", table_name="scores")
    op.drop_table("scores")
    op.drop_index("ix_provenance_lead_key", table_name="provenance")
    op.drop_table("provenance")
    op.drop_table("enriched_data")
    op.drop_index("ix_leads_status_uploaded", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_company", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_run_id", table_name="leads")
    op.drop_table("leads")
    op.drop_table("runs")
