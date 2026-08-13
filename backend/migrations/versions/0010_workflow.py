"""Phase 10 one-click workflow orchestration.

Revision ID: 0010_workflow
Revises: 0009_subtitle_audio
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_workflow"
down_revision = "0009_subtitle_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.Enum("MANUAL", "AUTO", name="workflowmode"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "RUNNING", "PAUSED", "VOICE_WAITING", "FAILED",
                "RENDER_READY", "CANCELED", name="workflowrunstatus",
            ),
            nullable=False,
        ),
        sa.Column("active_key", sa.String(20), nullable=True),
        sa.Column("current_step", sa.String(50), nullable=True),
        sa.Column("current_operation", sa.String(300), nullable=True),
        sa.Column("current_job_id", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("pause_requested", sa.Boolean(), nullable=False),
        sa.Column("policy_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "active_key", name="uq_project_active_workflow"),
    )
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_run_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "RUNNING", "WAITING", "COMPLETED", "SKIPPED", "FAILED",
                name="workflowstepstatus",
            ),
            nullable=False,
        ),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(300), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workflow_run_id", "name", name="uq_workflow_step_name"),
    )
    op.create_index("ix_workflow_steps_workflow_run_id", "workflow_steps", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_steps_workflow_run_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_project_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
