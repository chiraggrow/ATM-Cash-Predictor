"""Persist forecastable observation features and explicit data provenance."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_database_forecasting_source"
down_revision: Union[str, None] = "0003_atm_observations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "atm_observations",
        sa.Column("nearby_competitor_atms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "atm_observations",
        sa.Column("time_of_day", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "atm_observations",
        sa.Column(
            "data_source",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_unknown",
        ),
    )
    op.create_check_constraint(
        "ck_atm_observations_competitors_nonnegative",
        "atm_observations",
        "nearby_competitor_atms IS NULL OR nearby_competitor_atms >= 0",
    )
    op.execute(
        sa.text(
            """
            UPDATE atm_observations
            SET data_source = atms.data_source
            FROM atms
            WHERE atm_observations.atm_id = atms.atm_id
            """
        )
    )
    op.add_column(
        "forecast_records",
        sa.Column(
            "data_source",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_unknown",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE forecast_records
            SET data_source = atms.data_source
            FROM atms
            WHERE forecast_records.atm_id = atms.atm_id
            """
        )
    )


def downgrade() -> None:
    op.drop_column("forecast_records", "data_source")
    op.drop_constraint(
        "ck_atm_observations_competitors_nonnegative",
        "atm_observations",
        type_="check",
    )
    op.drop_column("atm_observations", "data_source")
    op.drop_column("atm_observations", "time_of_day")
    op.drop_column("atm_observations", "nearby_competitor_atms")
