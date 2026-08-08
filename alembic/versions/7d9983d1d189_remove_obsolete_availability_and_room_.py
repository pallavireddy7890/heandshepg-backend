"""remove obsolete availability and room caption columns

Revision ID: 7d9983d1d189
Revises: e1d77a3a3ae4
Create Date: 2026-08-08 13:52:52.814125

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d9983d1d189'
down_revision: Union[str, None] = 'e1d77a3a3ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("profiles", "owner_available")
    op.drop_column("profiles", "available_from")
    op.drop_column("profiles", "available_to")
    op.drop_column("profiles", "available_days")
    op.drop_column("rooms", "caption")



def downgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "owner_available",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=True,
        ),
    )
    op.add_column(
        "profiles",
        sa.Column("available_from", sa.String(10), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column("available_to", sa.String(10), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column("available_days", sa.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "rooms",
        sa.Column("caption", sa.Text(), nullable=True),
    )