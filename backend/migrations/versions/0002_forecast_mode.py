"""Record whether forecasts are historical demos or production forecasts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_forecast_mode"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "forecast_records",
        sa.Column(
            "forecast_mode",
            sa.String(length=32),
            server_default="legacy_unknown",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("forecast_records", "forecast_mode")
