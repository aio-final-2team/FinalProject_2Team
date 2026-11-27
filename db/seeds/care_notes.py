"""가상 돌봄 메모만 채워요. 기본 시드 실행에는 아직 연결하지 않아요."""
import json
from pathlib import Path
from sqlalchemy import text
from app.core.db import transaction
from app.mock import seed


def seed_care_notes(connection):
    rows = json.loads((Path(__file__).resolve().parents[2] / "data/fixtures/kg-demo-01/memories/care_notes.json").read_text())
    for row in rows:
        connection.execute(text("""
            INSERT INTO memories(org_id,owner_id,child_id,kind,content,structured,confirm_status,confirmed_at)
            SELECT :org,:owner_id,:child_id,'care_note',:content,CAST(:data AS jsonb),:confirm_status,
                   CASE WHEN :confirm_status='confirmed' THEN now() END
            WHERE EXISTS (SELECT 1 FROM child_guardians WHERE (org_id,user_id,child_id)=(:org,:owner_id,:child_id))
              AND NOT EXISTS (SELECT 1 FROM memories WHERE org_id=:org AND owner_id=:owner_id
                AND child_id=:child_id AND kind='care_note' AND content=:content)
        """), {"org": seed.ORG, "data": json.dumps({"is_virtual": True}), **row})


if __name__ == "__main__":
    with transaction() as connection:
        seed_care_notes(connection)
