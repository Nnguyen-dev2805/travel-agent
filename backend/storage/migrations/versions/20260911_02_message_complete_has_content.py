"""A complete message must carry content.

Revision ID: 20260911_02
Revises: 20260911_01
Create: 2026-09-11

ADR 0025: the invariant "a `complete` row carries content" is a schema
obligation, not only a model rule. Until this revision `messages` accepted
`status = 'complete'` with `content = ''`, and the repository's reader rejects
that combination, so a single such row made its whole conversation fail to load
with `ConversationStorageError` — not one bad message, but a lost transcript.

The state was reachable through this chain's own rollback path. Revision
`20260911_01` adds the column with `DEFAULT 'complete'`, which is correct when
adding a column to a table of pre-existing messages and wrong when re-adding it:
`downgrade -1` followed by `upgrade head` relabels every `pending` row as
`complete`. Any turn in flight when a process died became a complete row with no
content, and its conversation stopped loading.

`upgrade` therefore repairs first and constrains second, in one transaction:

1. ``UPDATE messages SET status = 'failed' WHERE status = 'complete' AND content = ''``
   `failed` is the truthful status for a row that produced no reply, and the row
   keeps its sequence, so the transcript stays contiguous. Deleting the row would
   break turn adjacency; inventing content for it would fabricate a reply.
2. ``ADD CONSTRAINT ck_messages_complete_has_content``
   ``CHECK (status <> 'complete' OR length(content) > 0)``

The predicate forbids exactly one combination. `pending` and `failed` rows with
empty content stay valid, and any non-`complete` row may carry content.

**The repair is one-way.** `downgrade` drops the constraint and does not restore
the previous status values, because which rows were originally `failed` is not
recoverable once they have been relabelled. A rollback must report how many rows
the repair moved.

`messages` is `FORCE`d for row-level security (revision `20260910_02`). A check
constraint applies to every role, including the bootstrap superuser, so no writer
can bypass it.
"""

import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260911_02"
down_revision = "20260911_01"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_messages_complete_has_content"
PREDICATE = "status <> 'complete' OR length(content) > 0"


def upgrade() -> None:
    # Repair before constraining, in the same transaction, so a failure at either
    # step leaves neither effect applied.
    result = op.execute(
        sa.text(
            "UPDATE messages SET status = 'failed' "
            "WHERE status = 'complete' AND content = ''"
        )
    )
    repaired = getattr(result, "rowcount", None)
    if repaired:
        # A count, never content. A non-zero value means a rollback previously
        # ran over a `pending` row, which is the operator's signal that the
        # repair was needed.
        logger.info("messages.complete_without_content repaired=%s", repaired)

    op.create_check_constraint(CONSTRAINT_NAME, "messages", PREDICATE)


def downgrade() -> None:
    # Drops the constraint only. The repair is deliberately not reversed: which
    # rows were originally `failed` is not recoverable, so a downgrade must
    # report the repair rather than pretend to undo it.
    op.drop_constraint(CONSTRAINT_NAME, "messages", type_="check")
