import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mock import seed, store


@pytest.fixture(autouse=True)
def _reset_store():
    store.reset()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, login_id: str) -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"login_id": login_id, "password": seed.DEMO_PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def parent(client):
    return _login(client, "parent01")


@pytest.fixture
def parent_other(client):
    return _login(client, "parent02")


@pytest.fixture
def teacher(client):
    return _login(client, "teacher01")


@pytest.fixture
def teacher_other(client):
    return _login(client, "teacher02")


@pytest.fixture
def director(client):
    return _login(client, "director01")
