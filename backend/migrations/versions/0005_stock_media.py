"""Phase 4 stock media candidates.

Revision ID: 0005_stock_media
Revises: 0004_scenes
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_stock_media"
down_revision = "0004_scenes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_asset_id", sa.String(300), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "STOCK_VIDEO",
                "STOCK_IMAGE",
                "AI_IMAGE",
                "AI_VIDEO",
                "AUDIO",
                "MUSIC",
                "SFX",
                name="mediaassettype",
            ),
            nullable=False,
        ),
        sa.Column("preview_url", sa.String(2000), nullable=False),
        sa.Column("download_url", sa.String(2000), nullable=True),
        sa.Column("source_page_url", sa.String(2000), nullable=False),
        sa.Column("creator", sa.String(300), nullable=True),
        sa.Column("license", sa.String(500), nullable=True),
        sa.Column("attribution_requirements", sa.String(1000), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("local_path", sa.String(1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("CANDIDATE", "SELECTED", "REJECTED", "FAILED", name="mediaassetstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "scene_id", "provider", "provider_asset_id", name="uq_scene_provider_asset"
        ),
    )
    op.create_index("ix_media_assets_project_id", "media_assets", ["project_id"])
    op.create_index("ix_media_assets_scene_id", "media_assets", ["scene_id"])
    with op.batch_alter_table("scenes") as batch:
        batch.add_column(sa.Column("preferred_media_asset_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("scene_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_generation_jobs_scene", "scenes", ["scene_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_constraint("fk_generation_jobs_scene", type_="foreignkey")
        batch.drop_column("scene_id")
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("preferred_media_asset_id")
    op.drop_index("ix_media_assets_scene_id", table_name="media_assets")
    op.drop_index("ix_media_assets_project_id", table_name="media_assets")
    op.drop_table("media_assets")
