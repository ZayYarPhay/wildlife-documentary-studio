"""Phase 1 research tables.

Revision ID: 0002_research
Revises: 0001_phase_0
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_research"
down_revision = "0001_phase_0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "url", name="uq_research_source_project_url"),
    )
    op.create_index("ix_research_sources_project_id", "research_sources", ["project_id"])
    op.create_table(
        "research_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("normalized_claim", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["research_sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "normalized_claim", name="uq_fact_claim"),
    )
    op.create_index("ix_research_facts_project_id", "research_facts", ["project_id"])
    op.create_index("ix_research_facts_source_id", "research_facts", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_research_facts_source_id", table_name="research_facts")
    op.drop_index("ix_research_facts_project_id", table_name="research_facts")
    op.drop_table("research_facts")
    op.drop_index("ix_research_sources_project_id", table_name="research_sources")
    op.drop_table("research_sources")
