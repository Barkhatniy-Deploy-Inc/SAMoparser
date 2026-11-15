"""Добавить реестр компьютеров и связь с установками."""

import sqlalchemy as sa
from alembic import op

revision = "0002_add_devices"
down_revision = "0001_mvp_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("computer_id", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("department", sa.String(200), nullable=False, server_default=""),
        sa.Column("user_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("operating_system", sa.String(100), nullable=False, server_default=""),
    )
    op.create_index("ix_devices_computer_id", "devices", ["computer_id"], unique=True)
    op.add_column("installations", sa.Column("device_id", sa.Integer(), nullable=True))
    op.create_index("ix_installations_device_id", "installations", ["device_id"])
    op.create_foreign_key("fk_installations_device_id_devices", "installations", "devices", ["device_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_installations_device_id_devices", "installations", type_="foreignkey")
    op.drop_index("ix_installations_device_id", table_name="installations")
    op.drop_column("installations", "device_id")
    op.drop_index("ix_devices_computer_id", table_name="devices")
    op.drop_table("devices")
