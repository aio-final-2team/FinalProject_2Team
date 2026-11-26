"""T11 가상 원 자료(`data/fixtures/kg-demo-01`)를 DB `documents`·`document_chunks`·`document_classrooms`에 넣는다(T20).

저장소 루트에서 `PYTHONPATH=apps/api python -m db.seeds.documents`로 실행해요. 데모 시드(`db.seeds.demo`) 뒤에 써요.
- 적재 대상은 README 'T20 적재 규칙'의 다섯 폴더 Markdown 30개뿐이에요(README·알림장 데이터는 넣지 않음).
- 반 키는 시드 반으로 이어요: C4 → 만 4세 별빛반(`…0101`), C5 → 만 5세 햇님반(`…0102`). 시드에 없는 반(C3)만
  대상인 문서는 원 전체로 잘못 보이지 않게 넣지 않아요.
- 같은 내용(`content_sha256`)이 이미 있으면 건너뛰고, 현재 원 자료에 없는 옛 가상 문서는 superseded로 내려요.
  원 자료끼리 일부러 넣은 충돌(겨울방학 12/24 vs 12/26)은
  평가용이라 충돌 검사를 하지 않고 둘 다 사용 중(active)으로 넣어요.
"""

from pathlib import Path

from sqlalchemy import text

from app.mock import seed
from app.modules.documents.parsing import parse_document

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures" / "kg-demo-01"
FOLDERS = ("notice", "schedule", "menu", "policy", "consult_timetable")
CLASSROOMS = {"C4": seed.CLASS_STAR, "C5": seed.CLASS_SUN}


def fixture_files() -> list[Path]:
    return [path for folder in FOLDERS for path in sorted((FIXTURES / folder).glob("*.md"))]


def seed_documents(connection) -> dict[str, list[str]]:
    """넣은 문서 id·건너뛴 문서 id를 돌려줘요."""
    added, skipped = [], []
    current_shas = []
    for path in fixture_files():
        parsed = parse_document(path.read_text(encoding="utf-8"))
        current_shas.append(parsed.content_sha256)
        meta = parsed.meta
        classrooms = [CLASSROOMS[key] for key in meta.classroom_keys if key in CLASSROOMS]
        if meta.classroom_keys and not classrooms:
            skipped.append(meta.id)
            continue
        document_id = connection.scalar(text("""
            INSERT INTO documents (org_id, title, doc_type, visibility, source, effective_from, status,
                                   ingest_status, content_sha256, is_virtual)
            VALUES (:org, :title, :doc_type, :visibility, 'virtual', :effective_from, 'active',
                    'succeeded', :sha, true)
            ON CONFLICT (org_id, content_sha256) DO NOTHING
            RETURNING id
        """), {"org": seed.ORG, "title": meta.title, "doc_type": meta.doc_type, "visibility": meta.visibility,
               "effective_from": meta.effective_from, "sha": parsed.content_sha256})
        if document_id is None:
            skipped.append(meta.id)
            continue
        for classroom_id in classrooms:
            connection.execute(text("""
                INSERT INTO document_classrooms (document_id, classroom_id, org_id) VALUES (:d, :c, :org)
            """), {"d": document_id, "c": classroom_id, "org": seed.ORG})
        for chunk in parsed.chunks:
            connection.execute(text("""
                INSERT INTO document_chunks (document_id, org_id, chunk_index, location, content)
                VALUES (:d, :org, :i, :loc, :content)
            """), {"d": document_id, "org": seed.ORG, "i": chunk.index, "loc": chunk.location,
                   "content": chunk.content})
        added.append(meta.id)
    connection.execute(text("""
        UPDATE documents SET status='superseded'
        WHERE org_id=:org AND is_virtual=true AND status='active'
          AND id <> ALL(CAST(:demo_ids AS uuid[]))
          AND content_sha256 <> ALL(CAST(:shas AS text[]))
    """), {"org": seed.ORG, "demo_ids": [seed.MENU, seed.NOTICE, seed.OLD_NOTICE], "shas": current_shas})
    connection.execute(text("""
        UPDATE documents SET status='active'
        WHERE org_id=:org AND is_virtual=true AND status='superseded'
          AND id <> ALL(CAST(:demo_ids AS uuid[]))
          AND content_sha256 = ANY(CAST(:shas AS text[]))
    """), {"org": seed.ORG, "demo_ids": [seed.MENU, seed.NOTICE, seed.OLD_NOTICE], "shas": current_shas})
    return {"added": added, "skipped": skipped}


if __name__ == "__main__":
    from app.core.db import transaction

    with transaction() as connection:
        result = seed_documents(connection)
    print(f"원 자료 적재: {len(result['added'])}개 넣음, 건너뜀 {result['skipped']}")
