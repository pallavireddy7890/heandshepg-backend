"""merge migration heads

Revision ID: e1d77a3a3ae4
Revises: 76ee11dca739, e72bb3a8f4c2
Create Date: 2026-08-08 13:46:06.279812

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1d77a3a3ae4'
down_revision: Union[str, None] = ('76ee11dca739', 'e72bb3a8f4c2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
