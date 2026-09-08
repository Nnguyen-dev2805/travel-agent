"""Versioned semantic-memory write pipeline tables.

Revision ID: 20260907_02
Revises: 20260907_01
Create: 2026-09-07

Normalized tables per ADR 0012: assertions own the stable identity with
a uniqueness constraint, versions carry the lifecycle with a partial
unique index enforcing one current version per assertion, and
registry-validated JSONB owns variable value payloads behind a
required-keys check. Every owner-scoped row carries `owner_user_id`
and is guarded by a tenant RLS policy on top of application
authorization.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260907_02"
down_revision = "20260907_01"
branch_labels = None
depends_on = None

OWNER_TABLES = (
    "memory_assertions",
    "memory_versions",
    "memory_evidence",
    "memory_candidates",
    "memory_decisions",
    "memory_events",
    "memory_outbox",
    "memory_write_idempotency",
    "memory_summaries",
    "memory_episodes",
    "memory_deletion_ledger",
)


def _enable_tenant_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL TO PUBLIC "
            f"USING (owner_user_id = current_setting('app.tenant', true)) "
            f"WITH CHECK (owner_user_id = current_setting('app.tenant', true))"
        )
    )


def upgrade() -> None:
    op.create_table(
        "memory_assertions",
        sa.Column("assertion_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("subject_key", sa.Text(), nullable=False),
        sa.Column("condition_fingerprint", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_user_id",
            "scope",
            "scope_id",
            "canonical_key",
            "subject_key",
            "condition_fingerprint",
            name="uq_memory_assertions_identity",
        ),
    )
    op.create_table(
        "memory_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column(
            "assertion_id",
            sa.Text(),
            sa.ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("value_payload", JSONB(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("sensitivity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value_payload ?& array['normalized_value', 'display_text']",
            name="ck_memory_versions_value_payload",
        ),
    )
    op.create_index(
        "uq_memory_versions_current",
        "memory_versions",
        ["assertion_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_memory_versions_assertion", "memory_versions", ["assertion_id"]
    )
    op.create_table(
        "memory_evidence",
        sa.Column("evidence_id", sa.Text(), primary_key=True),
        sa.Column(
            "assertion_id",
            sa.Text(),
            sa.ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Text(), nullable=False),
        sa.Column("display_text", sa.Text(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_memory_evidence_assertion", "memory_evidence", ["assertion_id"]
    )
    op.create_table(
        "memory_candidates",
        sa.Column("candidate_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "assertion_id",
            sa.Text(),
            sa.ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_memory_candidates_owner", "memory_candidates", ["owner_user_id"]
    )
    op.create_table(
        "memory_decisions",
        sa.Column("decision_id", sa.Text(), primary_key=True),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column(
            "assertion_id",
            sa.Text(),
            sa.ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_memory_decisions_assertion", "memory_decisions", ["assertion_id"]
    )
    op.create_index(
        "idx_memory_decisions_candidate", "memory_decisions", ["candidate_id"]
    )
    op.create_table(
        "memory_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "assertion_id",
            sa.Text(),
            sa.ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("version_id", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_memory_events_assertion", "memory_events", ["assertion_id"])
    op.create_table(
        "memory_outbox",
        sa.Column("outbox_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_memory_outbox_status", "memory_outbox", ["status", "created_at"]
    )
    op.create_table(
        "memory_write_idempotency",
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Text(), nullable=True),
        sa.Column("decision_id", sa.Text(), nullable=True),
        sa.Column("superseded_version_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("reference_version_id", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memory_summaries",
        sa.Column("summary_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memory_episodes",
        sa.Column("episode_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memory_deletion_ledger",
        sa.Column("ledger_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "target_type", "target_id", name="uq_memory_deletion_target"
        ),
    )
    for table in OWNER_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in reversed(OWNER_TABLES):
        op.drop_table(table)
