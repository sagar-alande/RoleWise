"""widen jobs.location - some employers list many regions in one string, past 255 chars

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "location", type_=sa.String(1000))


def downgrade() -> None:
    op.alter_column("jobs", "location", type_=sa.String(255))
