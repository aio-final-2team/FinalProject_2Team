"""시연용 가상 사진을 원에 넣어요: 아이 프로필 사진과 식단표 점심의 급식 참고 사진.

데모 원과 사람별 QA 원이 같은 함수를 써요. 다시 실행해도 이미 있는 행·파일은 건드리지 않아요.
사진은 모두 AI로 만든 가상 사진이에요(실제 원아·실제 급식 아님).
"""

from sqlalchemy import text

from app.core import media
from app.mock import seed


def _write(name, data):
    target = media.path(name)
    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def seed_photos(connection, org_id=seed.ORG, child_id_of=lambda child_id: child_id, *, write_media=True):
    """0021 전 revision(왕복 시험)에서는 열·표가 없어 건너뛰어요."""
    if not connection.scalar(text("SELECT to_regclass('meal_photos') IS NOT NULL")):
        return
    # 퇴소 작업(withdraw_child)을 거친 아이의 프로필 사진은 다시 넣지 않아요.
    withdrawn = set(connection.scalars(text("""
        SELECT (detail->>'child_id')::uuid FROM events
        WHERE org_id=:org AND action='photo_scope_changed' AND detail->>'withdrawn'='true'
    """), {"org": org_id}))
    for child in seed.CHILDREN:
        source, child_id = seed.profile_photo(child["id"]), child_id_of(child["id"])
        if source is None or child_id in withdrawn:
            continue
        name = f"profiles/{child_id}.jpg"
        current = connection.scalar(text("""
            UPDATE children SET profile_photo_path=coalesce(profile_photo_path, :path)
            WHERE id=:id AND org_id=:org RETURNING profile_photo_path
        """), {"path": name, "id": child_id, "org": org_id})
        if write_media and current == name:
            _write(name, source.read_bytes())
    for meal in seed.meal_photos():
        data = meal["path"].read_bytes()
        metadata = media.inspect(data)
        name = f"meals/{org_id}/{meal['date']}.{metadata['extension']}"
        connection.execute(text("""
            INSERT INTO meal_photos(org_id, meal_date, main_dish, storage_path, media_type, size_bytes)
            SELECT :org, CAST(:date AS date), :dish, :path, :media_type, :size
            WHERE EXISTS (SELECT 1 FROM organizations WHERE id=:org)
            ON CONFLICT (org_id, meal_date) DO NOTHING
        """), {"org": org_id, "date": meal["date"], "dish": meal["main_dish"], "path": name,
               "media_type": metadata["media_type"], "size": metadata["size_bytes"]})
        if write_media:
            _write(name, data)
