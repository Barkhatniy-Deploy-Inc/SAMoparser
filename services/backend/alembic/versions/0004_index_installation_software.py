"""Добавить индекс для связи установок с каталогом ПО."""

from alembic import op

revision = "0004_index_installation_software"
down_revision = "0003_add_import_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The index was created with the initial installations table in 0001.
    pass


def downgrade() -> None:
    pass
