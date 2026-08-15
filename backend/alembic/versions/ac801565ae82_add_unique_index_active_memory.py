"""add_unique_index_active_memory

Revision ID: ac801565ae82
Revises: '663badefb304'
Create Date: 2026-08-15 01:11:43.954152+00:00

"""
from typing import Sequence, Union

from alembic import op
# pyrefly: ignore [missing-import]
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac801565ae82'
down_revision: Union[str, None] = '663badefb304'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX uq_user_memory_active_fact 
        ON user_memories (user_id, fact_key) 
        WHERE status = 'active';
    """)
    pass


def downgrade() -> None:
    op.execute("DROP INDEX uq_user_memory_active_fact;")
    pass
