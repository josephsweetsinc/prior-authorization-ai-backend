"""add_insurance_and_npi_fields.

Revision ID: 4039f522c20f
Revises: 5c0c548ee4f2, f4537fc1e764, 38693011c912
Create Date: 2026-09-08 00:00:00.000000

Merges the three previously-diverged migration heads and adds the
insurance/payer and physician NPI fields needed for CMS-1500 and
Novitas prior-authorization package generation:
- patient_sex
- ordering_physician_npi
- insurance_type
- insurance_payer_name
- insured_id_number
- insured_name
- patient_relationship_to_insured
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4039f522c20f'
down_revision: str | Sequence[str] | None = (
    '5c0c548ee4f2',
    'f4537fc1e764',
    '38693011c912',
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE patientsex AS ENUM ('MALE', 'FEMALE'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE insurancetype AS ENUM ("
        "'MEDICARE', 'MEDICAID', 'TRICARE', 'CHAMPVA', "
        "'GROUP_HEALTH_PLAN', 'FECA_BLACK_LUNG', 'OTHER'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE patientrelationshiptoinsured AS ENUM ("
        "'SELF', 'SPOUSE', 'CHILD', 'OTHER'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )

    op.add_column(
        'ambulance_requests',
        sa.Column(
            'patient_sex',
            sa.Enum('MALE', 'FEMALE', name='patientsex', create_type=False),
            nullable=True,
            comment='Patient sex (CMS-1500 Box 3)',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'ordering_physician_npi',
            sa.String(length=10),
            nullable=True,
            comment='NPI of the ordering physician (CMS-1500 Box 17b)',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'insurance_type',
            sa.Enum(
                'MEDICARE',
                'MEDICAID',
                'TRICARE',
                'CHAMPVA',
                'GROUP_HEALTH_PLAN',
                'FECA_BLACK_LUNG',
                'OTHER',
                name='insurancetype',
                create_type=False,
            ),
            nullable=True,
            comment='Type of insurance/payer (CMS-1500 Box 1)',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'insurance_payer_name',
            sa.String(length=200),
            nullable=True,
            comment='Name of the insurance carrier/payer',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'insured_id_number',
            sa.String(length=50),
            nullable=True,
            comment=(
                "Insured's ID number (CMS-1500 Box 1a); same as "
                'patient_id when the patient is the insured'
            ),
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'insured_name',
            sa.String(length=200),
            nullable=True,
            comment=(
                "Insured's name (CMS-1500 Box 4) if different from "
                'the patient'
            ),
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'patient_relationship_to_insured',
            sa.Enum(
                'SELF',
                'SPOUSE',
                'CHILD',
                'OTHER',
                name='patientrelationshiptoinsured',
                create_type=False,
            ),
            nullable=True,
            comment="Patient's relationship to insured (CMS-1500 Box 6)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ambulance_requests', 'patient_relationship_to_insured')
    op.drop_column('ambulance_requests', 'insured_name')
    op.drop_column('ambulance_requests', 'insured_id_number')
    op.drop_column('ambulance_requests', 'insurance_payer_name')
    op.drop_column('ambulance_requests', 'insurance_type')
    op.drop_column('ambulance_requests', 'ordering_physician_npi')
    op.drop_column('ambulance_requests', 'patient_sex')

    op.execute('DROP TYPE IF EXISTS patientrelationshiptoinsured')
    op.execute('DROP TYPE IF EXISTS insurancetype')
    op.execute('DROP TYPE IF EXISTS patientsex')
