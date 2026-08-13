"""Phase 8 deterministic timelines.

Revision ID: 0008_timelines
Revises: 0007_voice_tracks
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_timelines"
down_revision = "0007_voice_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timelines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("voice_track_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("output_resolution", sa.String(20), nullable=False),
        sa.Column("fps", sa.Integer(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("render_plan_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_track_id"], ["voice_tracks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_timeline_version"),
    )
    op.create_index("ix_timelines_project_id", "timelines", ["project_id"])
    op.create_table(
        "timeline_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timeline_id", sa.Integer(), nullable=False),
        sa.Column(
            "track",
            sa.Enum("VISUAL", "VOICE", "MUSIC", "AMBIENT", "SUBTITLE", name="timelinetrack"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("voice_track_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("source_in", sa.Float(), nullable=False),
        sa.Column("source_out", sa.Float(), nullable=True),
        sa.Column("transition", sa.String(50), nullable=False),
        sa.Column("effect", sa.String(100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_track_id"], ["voice_tracks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_timeline_items_timeline_id", "timeline_items", ["timeline_id"])
    op.create_index("ix_timeline_items_track", "timeline_items", ["track"])


def downgrade() -> None:
    op.drop_index("ix_timeline_items_track", table_name="timeline_items")
    op.drop_index("ix_timeline_items_timeline_id", table_name="timeline_items")
    op.drop_table("timeline_items")
    op.drop_index("ix_timelines_project_id", table_name="timelines")
    op.drop_table("timelines")
