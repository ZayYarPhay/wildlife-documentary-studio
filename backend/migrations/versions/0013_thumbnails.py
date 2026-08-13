"""Optional Phase 14 documentary thumbnails.

Revision ID: 0013_thumbnails
Revises: 0012_production_export
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_thumbnails"
down_revision = "0012_production_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thumbnail_concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("concept_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_thumbnail_concepts_project_id", "thumbnail_concepts", ["project_id"])
    op.create_table(
        "thumbnail_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "COMPLETED", "APPROVED", "REJECTED", "FAILED", name="thumbnailstatus"
            ),
            nullable=False,
        ),
        sa.Column("local_path", sa.String(1000), nullable=True),
        sa.Column("public_url", sa.String(2000), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("title_overlay", sa.Boolean(), nullable=False),
        sa.Column("overlay_text", sa.String(200), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["thumbnail_concepts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_thumbnail_assets_project_id", "thumbnail_assets", ["project_id"])
    op.create_index("ix_thumbnail_assets_concept_id", "thumbnail_assets", ["concept_id"])
    op.create_index("ix_thumbnail_assets_status", "thumbnail_assets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_thumbnail_assets_status", table_name="thumbnail_assets")
    op.drop_index("ix_thumbnail_assets_concept_id", table_name="thumbnail_assets")
    op.drop_index("ix_thumbnail_assets_project_id", table_name="thumbnail_assets")
    op.drop_table("thumbnail_assets")
    op.drop_index("ix_thumbnail_concepts_project_id", table_name="thumbnail_concepts")
    op.drop_table("thumbnail_concepts")
