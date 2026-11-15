"""Добавить реестр импортов для идемпотентной загрузки."""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_import_batches"
down_revision = "0002_add_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_import_batches_idempotency_key", "import_batches", ["idempotency_key"], unique=True)
    op.add_column("installations", sa.Column("import_batch_id", sa.Integer(), nullable=True))
    op.create_index("ix_installations_import_batch_id", "installations", ["import_batch_id"])
    op.create_foreign_key("fk_installations_import_batch_id_import_batches", "installations", "import_batches", ["import_batch_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_installations_import_batch_id_import_batches", "installations", type_="foreignkey")
    op.drop_index("ix_installations_import_batch_id", table_name="installations")
    op.drop_column("installations", "import_batch_id")
    op.drop_index("ix_import_batches_idempotency_key", table_name="import_batches")
    op.drop_table("import_batches")
