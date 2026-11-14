"""Создать таблицы минимального прототипа SAM."""

from alembic import op
import sqlalchemy as sa

revision = "0001_mvp_assets"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "software_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("license_type", sa.String(50), nullable=False),
        sa.Column("policy_status", sa.String(50), nullable=False),
        sa.Column("license_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_software_products_name", "software_products", ["name"])
    op.create_index("ix_software_products_normalized_name", "software_products", ["normalized_name"], unique=True)
    op.create_table(
        "installations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("computer_id", sa.String(200), nullable=False),
        sa.Column("raw_name", sa.String(300), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=True),
        sa.Column("match_status", sa.String(30), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("software_id", sa.Integer(), sa.ForeignKey("software_products.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_installations_computer_id", "installations", ["computer_id"])
    op.create_index("ix_installations_canonical_name", "installations", ["canonical_name"])
    op.create_index("ix_installations_match_status", "installations", ["match_status"])
    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("installation_id", sa.Integer(), sa.ForeignKey("installations.id"), nullable=False),
        sa.Column("risk", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_risk_events_installation_id", "risk_events", ["installation_id"])
    op.create_index("ix_risk_events_risk", "risk_events", ["risk"])
    op.create_index("ix_risk_events_severity", "risk_events", ["severity"])


def downgrade() -> None:
    op.drop_table("risk_events")
    op.drop_table("installations")
    op.drop_index("ix_software_products_name", table_name="software_products")
    op.drop_index("ix_software_products_normalized_name", table_name="software_products")
    op.drop_table("software_products")
