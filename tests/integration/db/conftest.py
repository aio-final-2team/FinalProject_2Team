"""DB API 시험에서도 같은 계정·시드를 쓴다."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_client(seeded_db, monkeypatch):
    from app import backend
    from app.core import users, workflows
    from app.main import app

    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(workflows, "settings", replace(workflows.settings, data_backend="db"))
    with TestClient(app) as client:
        yield client
