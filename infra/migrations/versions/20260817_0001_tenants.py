"""Initial migration: extensions and tenants.

Deliberately small. The full 15-table schema is the Week 2 deliverable and gets
written as revision 0002 in one hand-authored migration — including the tables
that stay empty until month four.

This revision exists so that `make migrate` has something to do on a clean clone,
which means a teammate finds out their database wiring is broken in Week 1 rather
than in Week 2 when it blocks everyone.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: the Docker image also runs these in its init script, but a
    # migration must not assume it is running against that image.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "tenants",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        # The budget gate (Week 5) refuses actions above this. Per tenant, per month.
        sa.Column(
            "monthly_budget_usd",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="25.00",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("monthly_budget_usd >= 0", name="ck_tenants_budget_non_negative"),
    )

    # Every multi-tenant query in this system filters on tenant_id. Week 29 tests
    # that isolation; the index is here from the start so nobody "optimises" it in
    # later and changes the plan under the isolation suite.
    op.execute(
        """
        INSERT INTO tenants (id, name, monthly_budget_usd) VALUES
            ('tenant-a', 'Demo Tenant A', 25.00),
            ('tenant-b', 'Demo Tenant B', 10.00)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("tenants")
    # Extensions are left in place on purpose: dropping them would break any other
    # database object that happens to use them.
