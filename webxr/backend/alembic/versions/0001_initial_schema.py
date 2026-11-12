"""Create backend auth, scan, job, and artifact tables."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    uid = sa.Uuid(as_uuid=True)
    timestamptz = sa.DateTime(timezone=True)
    op.create_table(
        "users",
        sa.Column("id", uid, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("email_verified_at", timestamptz),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", timestamptz, nullable=False),
        sa.Column("updated_at", timestamptz, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "auth_tokens",
        sa.Column("id", uid, primary_key=True),
        sa.Column("user_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", timestamptz, nullable=False),
        sa.Column("consumed_at", timestamptz),
        sa.Column("created_at", timestamptz, nullable=False),
    )
    op.create_index("ix_auth_tokens_token_hash", "auth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
    op.create_index("ix_auth_tokens_user_kind", "auth_tokens", ["user_id", "kind"])
    op.create_index("ix_auth_tokens_expires_at", "auth_tokens", ["expires_at"])

    op.create_table(
        "scans",
        sa.Column("id", uid, primary_key=True),
        sa.Column("owner_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("subject_type", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(240)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", timestamptz, nullable=False),
        sa.Column("updated_at", timestamptz, nullable=False),
    )
    op.create_index("ix_scans_owner_id", "scans", ["owner_id"])
    op.create_index("ix_scans_status", "scans", ["status"])
    op.create_index("ix_scans_owner_updated", "scans", ["owner_id", "updated_at"])

    op.create_table(
        "scan_assets",
        sa.Column("id", uid, primary_key=True),
        sa.Column("scan_id", uid, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(700), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("expires_at", timestamptz),
        sa.Column("created_at", timestamptz, nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_scan_assets_storage_key"),
    )
    op.create_index("ix_scan_assets_scan_id", "scan_assets", ["scan_id"])
    op.create_index("ix_scan_assets_owner_id", "scan_assets", ["owner_id"])
    op.create_index("ix_scan_assets_status", "scan_assets", ["status"])
    op.create_index("ix_scan_assets_expires_at", "scan_assets", ["expires_at"])

    op.create_table(
        "scan_jobs",
        sa.Column("id", uid, primary_key=True),
        sa.Column("scan_id", uid, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metrics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", timestamptz, nullable=False),
        sa.Column("started_at", timestamptz),
        sa.Column("finished_at", timestamptz),
    )
    op.create_index("ix_scan_jobs_scan_id", "scan_jobs", ["scan_id"])
    op.create_index("ix_scan_jobs_owner_id", "scan_jobs", ["owner_id"])
    op.create_index("ix_scan_jobs_celery_task_id", "scan_jobs", ["celery_task_id"])
    op.create_index("ix_scan_jobs_status", "scan_jobs", ["status"])
    op.create_index("ix_scan_jobs_owner_created", "scan_jobs", ["owner_id", "created_at"])

    op.create_table(
        "scan_artifacts",
        sa.Column("id", uid, primary_key=True),
        sa.Column("scan_id", uid, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", uid, sa.ForeignKey("scan_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", uid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(700), nullable=False),
        sa.Column("created_at", timestamptz, nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_scan_artifacts_storage_key"),
    )
    op.create_index("ix_scan_artifacts_scan_id", "scan_artifacts", ["scan_id"])
    op.create_index("ix_scan_artifacts_job_id", "scan_artifacts", ["job_id"])
    op.create_index("ix_scan_artifacts_owner_id", "scan_artifacts", ["owner_id"])


def downgrade():
    op.drop_table("scan_artifacts")
    op.drop_table("scan_jobs")
    op.drop_table("scan_assets")
    op.drop_table("scans")
    op.drop_table("auth_tokens")
    op.drop_table("users")
