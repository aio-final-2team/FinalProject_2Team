"""최초 적재일의 오늘·어제, 별빛반 아이마다 가상 관찰 두 줄을 넣어요."""

from datetime import datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from app.core.schedule import KST
from app.mock import seed


def seed_daily_records(connection):
    today = datetime.now(KST).date()
    children = connection.scalars(text("SELECT id FROM children WHERE org_id=:org AND classroom_id=:class"),
                                 {"org": seed.ORG, "class": seed.CLASS_STAR}).all()
    for child_id in children:
        for offset in (0, 1):
            for index, body in enumerate(("블록을 친구와 나누어 쌓았어요.", "산책길에서 나뭇잎 모양을 살펴봤어요.")):
                at = datetime.combine(today-timedelta(days=offset), time(10+index, 30), KST)
                connection.execute(text("""
                    INSERT INTO daily_records(id,org_id,classroom_id,child_id,note_date,body,author_id,created_at)
                    VALUES (:id,:org,:class,:child,:date,:body,:author,:at) ON CONFLICT DO NOTHING
                """), {"id": uuid5(NAMESPACE_URL, f"daily-record:{child_id}:{offset}:{index}"),
                       "org": seed.ORG, "class": seed.CLASS_STAR, "child": child_id, "date": at.date(),
                       "body": body, "author": seed.TEACHER, "at": at})
