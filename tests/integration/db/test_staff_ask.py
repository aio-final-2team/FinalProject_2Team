"""[제안] 담당 반이 없어도 원 공통 자료는 검색 상한 전에 남겨요."""

from sqlalchemy import text

from app.core import users
from app.mock import seed
from app.modules.documents.staff_ask import ask
from tests.integration.api.test_staff_ask import Model, add_doc


def test_staff_ask_scope_before_top_k(seeded_db, monkeypatch):
    monkeypatch.setattr("app.modules.documents.embedding.enabled", lambda: False)
    with seeded_db.begin() as c:
        c.execute(text("DELETE FROM classroom_staff WHERE user_id=:id"), {"id": seed.TEACHER})
    doc = add_doc("db", "준비물은 개인 용품")
    for _ in range(25):
        add_doc("db", "준비물은 수건", target=seed.CLASS_SUN)
    Model.calls, Model.bad = [], False
    result = ask(users.get_user(seed.TEACHER), "준비물 수건", Model("DOCUMENT"), Model("CHECKER"))
    assert str(result["evidence"][0]["document_id"]) == doc and len(Model.calls) == 2
