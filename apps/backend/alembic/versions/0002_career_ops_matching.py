"""career-ops style matching: importance bands, evidence tiers, work auth, archetypes, verdicts

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("preferences", sa.Column("excluded_title_keywords", sa.ARRAY(sa.String()),
                                           nullable=False, server_default=sa.text("'{}'")))
    op.add_column("preferences", sa.Column("skip_tiers", sa.ARRAY(sa.String()),
                                           nullable=False, server_default=sa.text("'{}'")))
    op.add_column("preferences", sa.Column("authorized_in", sa.ARRAY(sa.String()),
                                           nullable=False, server_default=sa.text("'{}'")))
    op.add_column("preferences", sa.Column("needs_sponsorship", sa.Boolean(), nullable=True))
    op.add_column("preferences", sa.Column("archetypes", JSONB(), nullable=False,
                                           server_default=sa.text("'[]'::jsonb")))

    op.add_column("job_requirements", sa.Column("importance", sa.String(16), nullable=True))
    op.add_column("job_requirements", sa.Column("evidence_tier", sa.String(16), nullable=True))
    op.add_column("job_requirements", sa.Column("jd_signal", sa.Text(), nullable=True))

    op.add_column("matches", sa.Column("global_score", sa.Float(), nullable=True))
    op.add_column("matches", sa.Column("verdict", sa.String(32), nullable=True))


def downgrade() -> None:
    for table, col in [
        ("matches", "verdict"), ("matches", "global_score"),
        ("job_requirements", "jd_signal"), ("job_requirements", "evidence_tier"),
        ("job_requirements", "importance"),
        ("preferences", "archetypes"), ("preferences", "needs_sponsorship"), ("preferences", "authorized_in"),
        ("preferences", "skip_tiers"), ("preferences", "excluded_title_keywords"),
    ]:
        op.drop_column(table, col)
