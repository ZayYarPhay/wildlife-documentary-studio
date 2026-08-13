"""Phase 12 production export jobs.

Revision ID: 0012_production_export
Revises: 0011_worker_jobs
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_production_export"
down_revision = "0011_worker_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch:
        batch.add_column(sa.Column("timeline_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("settings_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(
            sa.Column("validation_json", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("logs", sa.Text(), nullable=True))
        batch.add_column(sa.Column("duration", sa.Float(), nullable=True))
        batch.add_column(sa.Column("width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("fps", sa.Float(), nullable=True))
        batch.add_column(sa.Column("file_size_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_render_jobs_timeline_id", "timelines", ["timeline_id"], ["id"], ondelete="SET NULL"
        )
    op.execute(
        "UPDATE render_jobs SET created_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP"
    )
    with op.batch_alter_table("render_jobs") as batch:
        batch.alter_column("created_at", nullable=False)
        batch.alter_column("updated_at", nullable=False)
        batch.create_index("ix_render_jobs_timeline_id", ["timeline_id"])
        batch.create_index("ix_render_jobs_status", ["status"])


def downgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch:
        batch.drop_index("ix_render_jobs_status")
        batch.drop_index("ix_render_jobs_timeline_id")
        batch.drop_constraint("fk_render_jobs_timeline_id", type_="foreignkey")
        for column in (
            "updated_at",
            "created_at",
            "file_size_bytes",
            "fps",
            "height",
            "width",
            "duration",
            "logs",
            "validation_json",
            "settings_json",
            "cancel_requested",
            "retry_count",
            "timeline_id",
        ):
            batch.drop_column(column)
