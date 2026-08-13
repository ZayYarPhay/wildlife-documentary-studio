"""Phase 9 subtitle and audio mix.

Revision ID: 0009_subtitle_audio
Revises: 0008_timelines
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_subtitle_audio"
down_revision = "0008_timelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Enum("MUSIC", "AMBIENT", name="audioassetkind"), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("public_url", sa.String(2000), nullable=False),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("license", sa.String(500), nullable=False),
        sa.Column("attribution", sa.String(1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_audio_assets_project_id", "audio_assets", ["project_id"])
    op.create_index("ix_audio_assets_scene_id", "audio_assets", ["scene_id"])
    op.create_index("ix_audio_assets_kind", "audio_assets", ["kind"])
    op.create_table(
        "audio_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("subtitles_enabled", sa.Boolean(), nullable=False),
        sa.Column("subtitle_font_size", sa.Integer(), nullable=False),
        sa.Column("subtitle_position", sa.String(20), nullable=False),
        sa.Column("subtitle_outline", sa.Boolean(), nullable=False),
        sa.Column("subtitle_background", sa.Boolean(), nullable=False),
        sa.Column("subtitle_safe_margin", sa.Integer(), nullable=False),
        sa.Column("music_enabled", sa.Boolean(), nullable=False),
        sa.Column("music_asset_id", sa.Integer(), nullable=True),
        sa.Column("music_volume", sa.Float(), nullable=False),
        sa.Column("music_fade_in", sa.Float(), nullable=False),
        sa.Column("music_fade_out", sa.Float(), nullable=False),
        sa.Column("ducking_ratio", sa.Float(), nullable=False),
        sa.Column("ambient_enabled", sa.Boolean(), nullable=False),
        sa.Column("ambient_volume", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["music_asset_id"], ["audio_assets.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_audio_settings_project_id", "audio_settings", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_audio_settings_project_id", table_name="audio_settings")
    op.drop_table("audio_settings")
    op.drop_index("ix_audio_assets_kind", table_name="audio_assets")
    op.drop_index("ix_audio_assets_scene_id", table_name="audio_assets")
    op.drop_index("ix_audio_assets_project_id", table_name="audio_assets")
    op.drop_table("audio_assets")
