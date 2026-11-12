"""Remove display_name from user accounts."""
import sqlalchemy as sa
from alembic import op

revision = "0002_remove_user_display_name"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "display_name")


def downgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""))
    op.alter_column("users", "display_name", server_default=None)
