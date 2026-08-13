"""Phase 11 separate GPU worker queue.

Revision ID: 0011_worker_jobs
Revises: 0010_workflow
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_worker_jobs"
down_revision = "0010_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("generation_job_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED", "CLAIMED", "RUNNING", "COMPLETED", "FAILED", "CANCELED",
                name="workerjobstatus",
            ),
            nullable=False,
        ),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["generation_job_id"], ["generation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("generation_job_id"),
    )
    op.create_index("ix_worker_jobs_generation_job_id", "worker_jobs", ["generation_job_id"], unique=True)
    op.create_index("ix_worker_jobs_project_id", "worker_jobs", ["project_id"])
    op.create_index("ix_worker_jobs_scene_id", "worker_jobs", ["scene_id"])
    op.create_index("ix_worker_jobs_job_type", "worker_jobs", ["job_type"])
    op.create_index("ix_worker_jobs_status", "worker_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_worker_jobs_status", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_job_type", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_scene_id", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_project_id", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_generation_job_id", table_name="worker_jobs")
    op.drop_table("worker_jobs")
