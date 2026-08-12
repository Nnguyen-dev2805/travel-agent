"""Add title column to chat_sessions table.

Revision ID: 002_add_session_title
Revises: 001_initial_auth_and_memory
Create Date: 2026-08-11 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
# pyrefly: ignore [missing-import]
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_add_session_title'
down_revision: Union[str, None] = '001_initial_auth_and_memory'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_sessions', sa.Column('title', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('chat_sessions', 'title')
