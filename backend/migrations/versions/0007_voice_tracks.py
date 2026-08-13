"""Phase 7 voice-over and transcript alignment.

Revision ID: 0007_voice_tracks
Revises: 0006_ai_images
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_voice_tracks"
down_revision = "0006_ai_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("public_url", sa.String(2000), nullable=False),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "UPLOADED", "TRANSCRIBING", "READY", "FAILED", "APPLIED", name="voicetrackstatus"
            ),
            nullable=False,
        ),
        sa.Column("alignment_confidence", sa.Float(), nullable=True),
        sa.Column("mismatch_warning", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_tracks_project_id", "voice_tracks", ["project_id"])
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voice_track_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["voice_track_id"], ["voice_tracks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_transcript_segments_voice_track_id", "transcript_segments", ["voice_track_id"]
    )
    op.create_table(
        "scene_voice_alignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voice_track_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("recommended_start", sa.Float(), nullable=False),
        sa.Column("recommended_end", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mismatch", sa.Boolean(), nullable=False),
        sa.Column("visual_adjustment", sa.String(100), nullable=False),
        sa.Column("manually_edited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["voice_track_id"], ["voice_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("voice_track_id", "scene_id", name="uq_voice_scene_alignment"),
    )
    op.create_index(
        "ix_scene_voice_alignments_voice_track_id", "scene_voice_alignments", ["voice_track_id"]
    )
    op.create_index("ix_scene_voice_alignments_scene_id", "scene_voice_alignments", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_scene_voice_alignments_scene_id", table_name="scene_voice_alignments")
    op.drop_index("ix_scene_voice_alignments_voice_track_id", table_name="scene_voice_alignments")
    op.drop_table("scene_voice_alignments")
    op.drop_index("ix_transcript_segments_voice_track_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("ix_voice_tracks_project_id", table_name="voice_tracks")
    op.drop_table("voice_tracks")
