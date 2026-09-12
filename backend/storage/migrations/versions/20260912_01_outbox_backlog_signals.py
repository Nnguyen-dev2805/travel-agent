"""The runtime role can observe backlog *age* and dead letters, not just depth.

Revision ID: 20260912_01
Revises: 20260911_06
Create: 2026-09-12

`ready_outbox_event_count()` (migration ``20260911_04``) let the runtime role see
queue depth without row access. Readiness then used that depth as the memory
pipeline's health, which answers the wrong question in both directions:

    worker healthy, one job queued   -> DEGRADED -> HTTP 503
    worker dead,    queue empty      -> READY

Five events being drained steadily is a healthy pipeline. One event nobody has
claimed for twenty minutes is not. Depth cannot tell those apart, and neither can
any other signal the runtime role can currently read — `conversation_outbox` is
protected by a tenant policy that `travel_app` cannot satisfy, which is exactly why
the count exists as a `SECURITY DEFINER` function.

**``oldest_ready_outbox_event_age_seconds()``** returns the age, in whole seconds,
of the oldest event a worker could claim right now. Zero when the queue is empty or
everything is fresh. It is the smallest interface that distinguishes "busy" from
"stalled": it cannot return a row, a payload, an owner, or a count.

**``dead_letter_outbox_event_count()``** returns how many events exhausted their
attempts. It is reported, not alerted on: a dead letter is a data condition an
operator inspects, and it does not by itself mean the service cannot serve.

Both are parameterless, scalar, read-only, ``SECURITY DEFINER``, with
``search_path`` pinned and the table fully qualified so the definer's privileges
cannot be redirected through a caller-controlled path. ``EXECUTE`` is granted to
``travel_app`` and revoked from ``PUBLIC``. No table is altered and no row is
written, so neither direction requires data repair.
"""

import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260912_01"
down_revision = "20260911_06"
branch_labels = None
depends_on = None

APP_ROLE = "travel_app"
OUTBOX_TABLE = "conversation_outbox"
AGE_FUNCTION = "oldest_ready_outbox_event_age_seconds"
DEAD_LETTER_FUNCTION = "dead_letter_outbox_event_count"

#: The events a worker could claim right now: pending and released (ADR 0027).
#: Kept identical to `ready_outbox_event_count()`'s predicate on purpose — two
#: functions that disagree about what "ready" means would be worse than one.
READY_PREDICATE = "status = 'pending' AND released_at IS NOT NULL"


def upgrade() -> None:
    # `min(created_at)` is NULL on an empty queue, so the whole expression is
    # wrapped: a quiet queue reports an age of 0, never NULL and never an error.
    # `GREATEST(..., 0)` guards a clock that moved backwards between the row's
    # creation and this read.
    op.execute(
        sa.text(
            f"CREATE OR REPLACE FUNCTION public.{AGE_FUNCTION}() "
            f"RETURNS bigint "
            f"LANGUAGE sql "
            f"SECURITY DEFINER "
            f"SET search_path = pg_catalog, public "
            f"AS $fn$ "
            f"SELECT COALESCE( "
            f"  GREATEST( "
            f"    EXTRACT(EPOCH FROM (now() - min(created_at)))::bigint, 0 "
            f"  ), 0 "
            f") "
            f"FROM public.{OUTBOX_TABLE} "
            f"WHERE {READY_PREDICATE} "
            f"$fn$"
        )
    )
    op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{AGE_FUNCTION}() FROM PUBLIC"))
    op.execute(
        sa.text(f"GRANT EXECUTE ON FUNCTION public.{AGE_FUNCTION}() TO {APP_ROLE}")
    )

    op.execute(
        sa.text(
            f"CREATE OR REPLACE FUNCTION public.{DEAD_LETTER_FUNCTION}() "
            f"RETURNS bigint "
            f"LANGUAGE sql "
            f"SECURITY DEFINER "
            f"SET search_path = pg_catalog, public "
            f"AS $fn$ "
            f"SELECT count(*) FROM public.{OUTBOX_TABLE} "
            f"WHERE status = 'dead_letter' "
            f"$fn$"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION public.{DEAD_LETTER_FUNCTION}() FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"GRANT EXECUTE ON FUNCTION public.{DEAD_LETTER_FUNCTION}() TO {APP_ROLE}"
        )
    )

    logger.info(
        "outbox backlog signals added: %s(), %s() granted to %s",
        AGE_FUNCTION,
        DEAD_LETTER_FUNCTION,
        APP_ROLE,
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{AGE_FUNCTION}()"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{DEAD_LETTER_FUNCTION}()"))
