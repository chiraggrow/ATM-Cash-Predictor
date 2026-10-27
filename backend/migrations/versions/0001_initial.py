"""Create user and forecast audit tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "forecast_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.String(length=32), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("source_data_as_of", sa.Date(), nullable=False),
        sa.Column("predicted_demand", sa.Integer(), nullable=False),
        sa.Column("lower_bound", sa.Integer(), nullable=False),
        sa.Column("upper_bound", sa.Integer(), nullable=False),
        sa.Column("current_balance", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("recommended_replenishment", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("capacity_constrained", sa.Boolean(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_records_atm_id", "forecast_records", ["atm_id"])
    op.create_index("ix_forecast_records_forecast_date", "forecast_records", ["forecast_date"])


def downgrade() -> None:
    op.drop_index("ix_forecast_records_forecast_date", table_name="forecast_records")
    op.drop_index("ix_forecast_records_atm_id", table_name="forecast_records")
    op.drop_table("forecast_records")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
