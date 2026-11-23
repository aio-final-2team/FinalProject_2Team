"""원 자료 읽기·조각 나누기·충돌 찾기 (T20).

DB 저장·임베딩·검색은 T19 마이그레이션이 나온 뒤 이 모듈 위에 붙인다.
"""

from .conflicts import Conflict, Fact, extract_facts, find_conflicts
from .parsing import Chunk, DocumentFormatError, DocumentMeta, ParsedDocument, parse_document

__all__ = [
    "Chunk",
    "Conflict",
    "DocumentFormatError",
    "DocumentMeta",
    "Fact",
    "ParsedDocument",
    "extract_facts",
    "find_conflicts",
    "parse_document",
]
