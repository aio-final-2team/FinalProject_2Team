"""지연 신호·자원·기관·시각 경계의 판정을 확인해요."""

from datetime import timedelta

import pytest

from app.core.consultation_alerts import DELAYED, alerts
from tests.integration.api.test_consultation_reminders import NOW


@pytest.mark.parametrize("change,expected", [({}, True), ({"teacher_id": "other"}, True),
                                            ({"room_id": "other"}, True),
                                            ({"room_id": "other", "teacher_id": "other"}, False),
                                            ({"org_id": "other"}, False),
                                            ({"status": "done"}, False), ({"status": "cancelled"}, False),
                                            ({"expected_end_at": None}, False),
                                            ({"expected_end_at": NOW+timedelta(minutes=10)}, False)])
def test_delay_requires_explicit_signal_and_shared_resource_in_same_org(change, expected):
    prior = {"id": "prior", "org_id": "org", "teacher_id": "teacher", "room_id": "room",
             "start": NOW-timedelta(minutes=20), "scheduled_end": NOW+timedelta(minutes=10),
             "end": NOW+timedelta(minutes=35), "expected_end_at": NOW+timedelta(minutes=35), "status": "confirmed"}
    target = {**prior, "id": "target", "start": NOW+timedelta(minutes=10), "end": NOW+timedelta(minutes=40),
              "scheduled_end": NOW+timedelta(minutes=40), "expected_end_at": None}
    result = list(alerts([{**prior, **change}, target], NOW))
    assert any(b["id"] == "target" and kind == DELAYED for b, kind, until in result) == expected
