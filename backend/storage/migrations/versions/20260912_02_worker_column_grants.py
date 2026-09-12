"""Narrow the worker's UPDATE grant to the columns the claim path writes.

Revision ID: 20260912_02
Revises: 20260912_01
Create: 2026-09-12

Revision ``20260911_04`` granted the worker role ``SELECT, UPDATE`` on
``conversation_outbox`` as a whole, at a time when the claim path's column
footprint had not yet been enumerated. The worker's ``UPDATE`` statements touch
exactly eight columns:

* ``status``, ``lease_owner``, ``lease_until`` — the lease lifecycle
* ``attempt_count``, ``next_attempt_after``, ``last_error`` — the retry lifecycle
* ``updated_at`` — the mutation timestamp
* ``released_at`` — written by the runtime role inside the turn transaction, and
  never by the worker

The row-level ``worker_outbox_lease`` policy remains ``USING (true) WITH CHECK
(true)``: the cross-owner claim is the point of the role (ADR 0028), and the
policy is what admits it. What this revision narrows is the **column** surface of
the privilege, not the row surface. PostgreSQL applies row-level-security
policies only to columns the role may touch at all, so a row-permissive policy
over a column-narrow grant yields: every row, eight columns. An ``UPDATE``
naming any other column now fails with a privilege error rather than succeeding
— a future claim path that grows the footprint must grow the grant explicitly,
in a reviewed migration, rather than silently inheriting breadth it does not
document.

``downgrade`` restores the table-wide ``UPDATE`` and re-grants the whole-table
privilege. No data is touched, so neither direction requires repair.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260912_02"
down_revision = "20260912_01"
branch_labels = None
depends_on = None

WORKER_ROLE = "travel_worker"
OUTBOX_TABLE = "conversation_outbox"

#: The complete set of columns the worker's claim path writes, across
#: ``claim_event``, ``claim_batch``, ``renew_lease``, ``mark_succeeded``,
#: ``mark_failed`` and ``cancel_events``. Kept as SQL fragments in a tuple so the
#: grant is rendered column-by-column and a reader can see the enumeration.
WORKER_UPDATE_COLUMNS = (
    "status",
    "lease_owner",
    "lease_until",
    "attempt_count",
    "next_attempt_after",
    "last_error",
    "updated_at",
    "released_at",
)


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def upgrade() -> None:
    if _is_offline_mode():
        op.execute(
            sa.text(
                f"REVOKE UPDATE ON {OUTBOX_TABLE} FROM {WORKER_ROLE}"
            )
        )
        op.execute(
            sa.text(
                f"GRANT UPDATE ({', '.join(WORKER_UPDATE_COLUMNS)}) "
                f"ON {OUTBOX_TABLE} TO {WORKER_ROLE}"
            )
        )
        return

    # Idempotent under re-run: revoke before grant, in both directions.
    op.execute(
        sa.text(f"REVOKE UPDATE ON {OUTBOX_TABLE} FROM {WORKER_ROLE}")
    )
    op.execute(
        sa.text(
            f"GRANT UPDATE ({', '.join(WORKER_UPDATE_COLUMNS)}) "
            f"ON {OUTBOX_TABLE} TO {WORKER_ROLE}"
        )
    )
    # ``SELECT`` stays table-wide deliberately: the claim predicate, the batch
    # candidate scan and ``get_event`` read every column, and a read surface
    # narrower than the write surface would break the next caller who adds a
    # read-only column without remembering this grant.


def downgrade() -> None:
    op.execute(
        sa.text(f"REVOKE UPDATE ON {OUTBOX_TABLE} FROM {WORKER_ROLE}")
    )
    op.execute(
        sa.text(f"GRANT UPDATE ON {OUTBOX_TABLE} TO {WORKER_ROLE}")
    )
