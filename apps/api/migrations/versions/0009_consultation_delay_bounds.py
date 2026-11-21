"""예상 종료를 예약 당일·원래 종료 뒤 세 시간 안으로 제한해요."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE consultation_bookings ADD CONSTRAINT consultation_bookings_delay_bounds_check
        CHECK (expected_end_at <= upper(period) + interval '3 hours'
          AND (expected_end_at AT TIME ZONE 'Asia/Seoul')::date
              = (lower(period) AT TIME ZONE 'Asia/Seoul')::date)
    """)


def downgrade():
    op.drop_constraint("consultation_bookings_delay_bounds_check", "consultation_bookings")
