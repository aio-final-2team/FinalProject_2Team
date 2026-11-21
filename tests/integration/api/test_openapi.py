"""계약 생성물과 명세 v0.4의 30개 경로를 대조한다."""

import json
from pathlib import Path
import re

import yaml

from app.main import app

ROOT = Path(__file__).resolve().parents[3]


def test_contract_matches_application():
    assert yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text()) == app.openapi()
    assert set(app.openapi()["components"]["schemas"]["NoteLine"]["properties"]["key"]["enum"]) == {
        "day", "meal", "medication", "pickup", "supplies", "child", "inquiry"}


def test_all_30_documented_endpoints_exist(client):
    doc = (ROOT / "Docs/Step2/API_설계_문서.md").read_text().split("## 2. API 목록")[1].split("## 3.")[0]
    endpoints = re.findall(r"\|\s*\d+\s*\|\s*(GET|POST|PATCH)\s*\|\s*`([^`]+)`", doc)
    assert len(endpoints) == 30
    contract = client.get("/openapi.json").json()
    assert contract == json.loads(json.dumps(app.openapi()))
    for method, path in endpoints:
        assert method.lower() in contract["paths"][path]
    for path in contract["paths"]:
        if path.endswith("/stream"):
            assert "text/event-stream" in contract["paths"][path]["get"]["responses"]["200"]["content"]
