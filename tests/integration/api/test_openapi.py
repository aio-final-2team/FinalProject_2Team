"""계약 생성물과 명세 v0.8의 HTTP 50개 경로를 대조한다."""

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
    # 투약·귀가는 별도 교직원 목록이에요. 기존 받은함 응답의 유형 계약은 그대로예요.
    assert app.openapi()["components"]["schemas"]["CardItem"]["properties"]["request_type"]["anyOf"][0]["enum"] == [
        "inquiry", "consultation", "complaint"]
    for target in ("classrooms/{classroom_id}", "organizations/{org_id}"):
        schema = app.openapi()["paths"][f"/api/v1/{target}/posts"]["post"]["requestBody"]["content"][
            "multipart/form-data"]["schema"]
        assert schema["properties"]["files"]["maxItems"] == 10


def test_all_50_documented_endpoints_exist(client):
    doc = (ROOT / "Docs/Step2/API_설계_문서.md").read_text().split("## 2. API 목록")[1].split("## 3.")[0]
    endpoints = re.findall(r"\|\s*\d+\s*\|\s*(GET|POST|PATCH|DELETE)\s*\|\s*`([^`]+)`", doc)
    assert len(endpoints) == 50
    contract = client.get("/openapi.json").json()
    assert contract == json.loads(json.dumps(app.openapi()))
    for method, path in endpoints:
        assert method.lower() in contract["paths"][path]
    for path in contract["paths"]:
        if path.endswith("/stream"):
            assert "text/event-stream" in contract["paths"][path]["get"]["responses"]["200"]["content"]
