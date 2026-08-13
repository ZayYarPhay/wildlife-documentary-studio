"""Phase 3 scene planner.

Revision ID: 0004_scenes
Revises: 0003_scripts
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_scenes"
down_revision = "0003_scripts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("narration_text", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("target_duration", sa.Float(), nullable=False),
        sa.Column("species", sa.String(200), nullable=False),
        sa.Column("environment", sa.String(500), nullable=False),
        sa.Column("animal_behavior", sa.String(300), nullable=False),
        sa.Column("visual_description", sa.Text(), nullable=False),
        sa.Column("shot_type", sa.String(100), nullable=False),
        sa.Column("camera_motion", sa.String(100), nullable=False),
        sa.Column(
            "visual_strategy",
            sa.Enum("STOCK_VIDEO", "AI_IMAGE_MOTION", "AI_VIDEO", name="visualstrategy"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "READY", "APPROVED", "FAILED", "SKIPPED", name="scenestatus"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scenes_project_id", "scenes", ["project_id"])
    op.create_table(
        "scene_prompts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("image_prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("video_prompt", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scene_prompts_scene_id", "scene_prompts", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_scene_prompts_scene_id", table_name="scene_prompts")
    op.drop_table("scene_prompts")
    op.drop_index("ix_scenes_project_id", table_name="scenes")
    op.drop_table("scenes")
