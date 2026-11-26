"""DB API 시험에서도 같은 계정·시드를 쓴다."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_client(seeded_db, monkeypatch):
    from app import backend
    from app.core import users, workflows
    from app.modules.daily_notes import notes
    from app.modules.documents import documents
    from app.modules.cards import cards, card_views
    from app.modules.notifications import notifications
    from app.modules.requests import requests
    from app.modules.consents import consents
    from app.main import app

    monkeypatch.setattr(backend, "cards", cards)
    monkeypatch.setattr(backend, "card_views", card_views)
    monkeypatch.setattr(backend, "notifications", notifications)
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "notes", notes)
    monkeypatch.setattr(backend, "documents", documents)
    monkeypatch.setattr(backend, "request_actions", requests)
    monkeypatch.setattr(backend, "consents", consents)
    monkeypatch.setattr(workflows, "settings", replace(workflows.settings, data_backend="db"))
    with TestClient(app) as client:
        yield client
