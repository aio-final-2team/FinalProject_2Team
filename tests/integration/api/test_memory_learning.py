"""[TEST] 모의·DB가 같은 말투 저장 계약을 지켜요."""

from uuid import UUID

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE
from tests.integration.api.test_cards import create
from tests.integration.api import test_memories

memory_backend = test_memories.memory_backend


def test_tone_storage_contract(client, parent, teacher, memory_backend):
    _, cid = create(client, parent, teacher, type="inquiry")
    user = backend.users.get_user(seed.TEACHER)
    card = {"id": UUID(cid), "version": 1}
    def save(candidates):
        if memory_backend == "db":
            with transaction() as connection:
                backend.memories.save_tones(connection, user, card, candidates, ["하늘"])
        else:
            backend.memories.save_tones(user, card, candidates, ["하늘"])
    candidates = [{"kind": "tone", "content": value} for value in (
        "하늘에게 해요체로 안내해요.", "해요체로 안내해요.", "해요체로 안내해요.",
        "010-1234-5678로 끝내요.", "test@example.com을 붙여요.", "내일 3시에 안내해요.",
        "첫 문장. 둘째 문장.", "줄을\n나눠요", "가" * 81)]
    save(candidates + [{"kind": "preference", "content": "짧게 써요."}])
    items = client.get(BASE + "/memories?kind=tone&size=100", headers=teacher).json()["items"]
    assert {m["content"] for m in items} == {"○○에게 해요체로 안내해요.", "해요체로 안내해요."}
    assert all(m["structured"] == {"source": "edit_approve", "card_version": 1} for m in items)
    for suffix in "가나다라마바사아자차카타파하":
        save([{"kind": "tone", "content": f"마무리에는 {suffix} 표현을 써요."}])
    items = client.get(BASE + "/memories?kind=tone&size=100", headers=teacher).json()["items"]
    assert len(items) == 12
    assert not any(m["content"] == "해요체로 안내해요." for m in items)
    if memory_backend == "mock":
        assert len([m for m in store.state().memories.values() if m.deleted_at is not None]) == 4
