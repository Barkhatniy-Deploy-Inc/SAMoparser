"""Добавить индекс для связи установок с каталогом ПО."""

from alembic import op

revision = "0004_index_installation_software"
down_revision = "0003_add_import_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_installations_software_id", "installations", ["software_id"])


def downgrade() -> None:
    op.drop_index("ix_installations_software_id", table_name="installations")
