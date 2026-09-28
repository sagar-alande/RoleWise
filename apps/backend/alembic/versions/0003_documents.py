"""tailored resume and cover letter generation: contact details and claim notes

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("contact", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("claims", sa.Column("validator_note", sa.Text(), nullable=True))
    op.create_index("ix_documents_match_kind", "documents", ["match_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_documents_match_kind", table_name="documents")
    op.drop_column("claims", "validator_note")
    op.drop_column("users", "contact")
