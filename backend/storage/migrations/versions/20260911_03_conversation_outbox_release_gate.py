"""An outbox event is claimable only once its turn is terminal.

Revision ID: 20260911_03
Revises: 20260911_02
Create: 2026-09-11

ADR 0027: a transactional outbox must write its event in the same transaction as
the message, but "written atomically" and "ready to be consumed" are different
facts. Until this revision the schema recorded only the first, so a worker could
claim an extraction event while the assistant row for that same turn was still
`pending`, and the failure-path cancellation could not undo a claim that had
already happened.

This revision adds the missing fact as an explicit, nullable release gate.

``ADD COLUMN released_at timestamptz NULL``
    `NULL` means blocked: the event exists and is owed, but its turn is not
    finished. A non-NULL value means released. The column is nullable with no
    default on purpose — a default would silently release every future row and
    reintroduce the defect.

``UPDATE conversation_outbox SET released_at = created_at WHERE released_at IS NULL``
    Every pre-existing row was written under a contract in which readiness was
    implied by the status alone, so every one of them is released.

    The backfill deliberately has **no status predicate**. Covering `leased` rows
    matters: the claim query's lease-expiry branch also requires the gate, so a
    `leased` row left with `released_at IS NULL` could never be reclaimed after
    its lease expired. It would be permanently stuck rather than merely delayed.

``CREATE INDEX idx_conversation_outbox_ready``
    On `(status, released_at)`, supporting the claim path's new predicate.

**The release gate is not a status.** `OutboxStatus` keeps its existing
vocabulary, because where an event sits in its retry lifecycle and whether its
turn has finished are independent. Merging them would make every future status
transition carry a hidden second meaning.

`downgrade` drops the index and then the column, which restores the previous
behaviour including the race. Rolling back re-opens the defect rather than
corrupting data, so no repair is required in either direction.
"""

import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260911_03"
down_revision = "20260911_02"
branch_labels = None
depends_on = None

TABLE_NAME = "conversation_outbox"
COLUMN_NAME = "released_at"
INDEX_NAME = "idx_conversation_outbox_ready"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column(COLUMN_NAME, sa.DateTime(timezone=True), nullable=True),
    )

    # Every existing row predates the gate. Released, not blocked: blocking them
    # would strand work that the previous contract had made claimable, and would
    # strand any `leased` row permanently.
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            f"UPDATE {TABLE_NAME} SET {COLUMN_NAME} = created_at "
            f"WHERE {COLUMN_NAME} IS NULL"
        )
    )
    logger.info(
        "outbox release gate: released %s pre-existing event(s)",
        result.rowcount if result.rowcount is not None else "unknown",
    )

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["status", COLUMN_NAME],
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, COLUMN_NAME)
