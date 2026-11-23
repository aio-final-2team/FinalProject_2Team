"""선택한 bge-m3 모델로 비어 있는 자료 조각의 벡터를 채운다."""

import os
from functools import lru_cache

from sqlalchemy import text

VERSION = "bge-m3@1"
MODEL = "BAAI/bge-m3"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL)


def enabled() -> bool:
    if os.getenv("EMBEDDING_MODEL", "") != MODEL:
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def embed(texts: list[str]) -> list[list[float]]:
    if not enabled():
        return []
    try:
        vectors = _model().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]
    except Exception:  # noqa: BLE001 - 모델 내려받기·읽기 실패는 선택 기능만 끈다
        return []


def fill_missing(connection, limit=None) -> int:
    """빈 조각만 채운다. 모델을 못 읽으면 자료는 그대로 둔다."""
    if not enabled():
        return 0
    rows = connection.execute(text("""
        SELECT id, content FROM document_chunks WHERE embedding IS NULL ORDER BY id LIMIT :limit
    """), {"limit": limit if limit is not None else 2147483647}).mappings().all()
    if not rows:
        return 0
    vectors = embed([row["content"] for row in rows])
    if len(vectors) != len(rows) or any(len(vector) != 1024 for vector in vectors):
        return 0
    for row, vector in zip(rows, vectors):
        connection.execute(text("""
            UPDATE document_chunks SET embedding=CAST(:vector AS vector), embedding_model=:model,
                embedding_version=:version WHERE id=:id AND embedding IS NULL
        """), {"id": row["id"], "vector": "[" + ",".join(map(str, vector)) + "]",
               "model": MODEL, "version": VERSION})
    return len(rows)
