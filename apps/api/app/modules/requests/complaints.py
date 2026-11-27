"""반복 민원 원장 보고의 기준이에요. 원장 보고와 화면이 같은 반·최근 30일·같은 주제 민원 수를 함께 써요.

이 셈이 정책 선이라 감독 AI는 '세 번째'라는 말로 등급을 올리지 않고 주제만 고른다(supervisor.md).
"""

from sqlalchemy import text

REPEAT_REPORT_AT = 3  # 같은 반·30일·같은 주제 민원이 이 건수가 되면 원장에게 보고해요


def repeat_count(connection, req):
    if req["type"] != "complaint" or req["topic_key"] in (None, "other"):
        return None
    return connection.scalar(
        text("""SELECT count(*) FROM requests WHERE org_id=:org AND classroom_id=:class
        AND type='complaint' AND topic_key=:topic AND created_at>=now()-interval '30 days' """),
        {"org": req["org_id"], "class": req["classroom_id"], "topic": req["topic_key"]},
    )
