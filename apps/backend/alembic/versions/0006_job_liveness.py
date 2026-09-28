"""job freshness/liveness: listing_status + last_checked_at on jobs

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("listing_status", sa.String(16), nullable=False, server_default="unknown"))
    op.add_column("jobs", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "last_checked_at")
    op.drop_column("jobs", "listing_status")
