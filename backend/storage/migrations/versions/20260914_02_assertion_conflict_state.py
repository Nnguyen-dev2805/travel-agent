"""Persist authoritative current unresolved-conflict state."""
from alembic import op
import sqlalchemy as sa

revision = "20260914_02"
down_revision = "20260914_01"
branch_labels = depends_on = None

def upgrade():
    op.add_column("memory_assertions", sa.Column("has_unresolved_conflict", sa.Boolean(), nullable=False, server_default=sa.text("false")))

def downgrade():
    op.drop_column("memory_assertions", "has_unresolved_conflict")
