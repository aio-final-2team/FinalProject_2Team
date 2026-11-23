"""자료 조각의 빈 임베딩을 채운다: PYTHONPATH=apps/api python -m db.seeds.embed"""

from app.core.db import transaction
from app.modules.documents.embedding import fill_missing

if __name__ == "__main__":
    with transaction() as connection:
        count = fill_missing(connection)
    print(f"벡터를 채운 조각: {count}개")
