"""Add ATM metadata and uniquely dated operational observations."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_atm_observations"
down_revision: Union[str, None] = "0002_forecast_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atms",
        sa.Column("atm_id", sa.String(length=32), nullable=False),
        sa.Column("location_name", sa.String(length=120), nullable=False),
        sa.Column("location_type", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Numeric(12, 2), nullable=False),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_atms_capacity_positive"),
        sa.PrimaryKeyConstraint("atm_id"),
    )
    op.create_index("ix_atms_location_type", "atms", ["location_type"])
    op.create_table(
        "atm_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("atm_id", sa.String(length=32), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("total_withdrawals", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_deposits", sa.Numeric(12, 2), nullable=False),
        sa.Column("withdrawal_transactions", sa.Integer(), nullable=False),
        sa.Column("deposit_transactions", sa.Integer(), nullable=False),
        sa.Column("opening_cash_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("closing_cash_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("replenishment_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("next_day_demand", sa.Numeric(12, 2), nullable=False),
        sa.Column("holiday_flag", sa.Boolean(), nullable=False),
        sa.Column("special_event_flag", sa.Boolean(), nullable=False),
        sa.Column("weather_condition", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "total_withdrawals >= 0",
            name="ck_atm_observations_withdrawals_nonnegative",
        ),
        sa.CheckConstraint(
            "total_deposits >= 0",
            name="ck_atm_observations_deposits_nonnegative",
        ),
        sa.CheckConstraint(
            "opening_cash_balance >= 0",
            name="ck_atm_observations_opening_nonnegative",
        ),
        sa.CheckConstraint(
            "closing_cash_balance >= 0",
            name="ck_atm_observations_closing_nonnegative",
        ),
        sa.CheckConstraint(
            "replenishment_amount >= 0",
            name="ck_atm_observations_replenishment_nonnegative",
        ),
        sa.CheckConstraint(
            "next_day_demand >= 0",
            name="ck_atm_observations_demand_nonnegative",
        ),
        sa.CheckConstraint(
            "withdrawal_transactions >= 0",
            name="ck_atm_observations_withdrawals_count_nonnegative",
        ),
        sa.CheckConstraint(
            "deposit_transactions >= 0",
            name="ck_atm_observations_deposits_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["atm_id"],
            ["atms.atm_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("atm_id", "observed_on", name="uq_atm_observations_atm_date"),
    )
    op.create_index(
        "ix_atm_observations_observed_on",
        "atm_observations",
        ["observed_on"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO atms (atm_id, location_name, location_type, capacity, data_source)
            SELECT atm_id,
                   'Unknown (legacy forecast)',
                   'Unknown',
                   CASE WHEN MAX(capacity) > 0 THEN MAX(capacity) ELSE 1 END,
                   'legacy_unknown'
            FROM forecast_records
            GROUP BY atm_id
            """
        )
    )
    with op.batch_alter_table("forecast_records") as batch:
        batch.create_foreign_key(
            "fk_forecast_records_atm_id_atms",
            "atms",
            ["atm_id"],
            ["atm_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    raise RuntimeError(
        "This migration contains operational ATM/observation data. "
        "Do not downgrade it automatically; migrate or back up that data explicitly."
    )
