"""semantic role-family matching: a title-only embedding per job

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

EMBED_DIMS = 1024


def upgrade() -> None:
    op.add_column("jobs", sa.Column("title_embedding", Vector(EMBED_DIMS), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "title_embedding")
