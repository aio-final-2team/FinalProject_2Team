"""원장 보고와 화면이 같은 반·최근 30일·같은 주제 민원 수를 함께 써요."""

from sqlalchemy import text


def repeat_count(connection, req):
    if req["type"] != "complaint" or req["topic_key"] in (None, "other"):
        return None
    return connection.scalar(
        text("""SELECT count(*) FROM requests WHERE org_id=:org AND classroom_id=:class
        AND type='complaint' AND topic_key=:topic AND created_at>=now()-interval '30 days' """),
        {"org": req["org_id"], "class": req["classroom_id"], "topic": req["topic_key"]},
    )
