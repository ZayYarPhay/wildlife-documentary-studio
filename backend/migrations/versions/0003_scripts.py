"""Phase 2 documentary scripts.

Revision ID: 0003_scripts
Revises: 0002_research
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_scripts"
down_revision = "0002_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column(
                "documentary_tone",
                sa.String(100),
                nullable=False,
                server_default="cinematic wildlife documentary",
            )
        )
    op.create_table(
        "scripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tone", sa.String(100), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("estimated_words", sa.Integer(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Float(), nullable=False),
        sa.Column("length_status", sa.String(30), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "version", name="uq_script_version"),
    )
    op.create_index("ix_scripts_project_id", "scripts", ["project_id"])
    op.create_table(
        "script_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Float(), nullable=False),
        sa.Column("source_fact_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("script_id", "order", name="uq_script_section_order"),
    )
    op.create_index("ix_script_sections_script_id", "script_sections", ["script_id"])


def downgrade() -> None:
    op.drop_index("ix_script_sections_script_id", table_name="script_sections")
    op.drop_table("script_sections")
    op.drop_index("ix_scripts_project_id", table_name="scripts")
    op.drop_table("scripts")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("documentary_tone")
