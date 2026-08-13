"""Phase 5 AI image generation.

Revision ID: 0006_ai_images
Revises: 0005_stock_media
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_ai_images"
down_revision = "0005_stock_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scene_prompts") as batch:
        batch.create_unique_constraint("uq_scene_prompt_version", ["scene_id", "version"])
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("source_page_url", existing_type=sa.String(2000), nullable=True)
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("prompt_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("output_asset_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("seed", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_generation_jobs_prompt", "scene_prompts", ["prompt_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_constraint("fk_generation_jobs_prompt", type_="foreignkey")
        batch.drop_column("completed_at")
        batch.drop_column("updated_at")
        batch.drop_column("request_json")
        batch.drop_column("seed")
        batch.drop_column("output_asset_id")
        batch.drop_column("prompt_id")
    media_assets = sa.table("media_assets", sa.column("source_page_url", sa.String(2000)))
    op.execute(
        media_assets.update()
        .where(media_assets.c.source_page_url.is_(None))
        .values(source_page_url="about:blank")
    )
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("source_page_url", existing_type=sa.String(2000), nullable=False)
    with op.batch_alter_table("scene_prompts") as batch:
        batch.drop_constraint("uq_scene_prompt_version", type_="unique")
