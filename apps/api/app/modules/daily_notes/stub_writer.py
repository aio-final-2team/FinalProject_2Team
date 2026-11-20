"""T32 영민 그래프로 교체, T29에 Celery 워커로 이동.

입구는 write(payload) -> 아이별 {child_id, content, open_checks} 목록이다.
대역은 입력 원문만 옮긴다. 저장·상태·이벤트 처리는 runner가 맡는다.
"""

from app.mock.seed import REQUEST_PICKUP


def common_content(payload):
    items = [
        {"key": "day", "label": "오늘 하루", "value": payload["activities"],
         "source": {"type": "teacher_input"}},
        {"key": "supplies", "label": "준비물", "value": payload["supplies"],
         "source": {"type": "teacher_input"}},
    ]
    if payload["menu"] is not None:
        menu = payload["menu"]
        items.append({"key": "meal", "label": "식사", "value": menu["text"],
                      "source": {"type": "document", "document_id": menu["document_id"],
                                 "document_title": menu["title"]}})
    return {"items": items}


def failed_child(payload, child):
    return {"child_id": child["child_id"], "content": common_content(payload), "open_checks": [
        {"id": "draft-failed", "item_key": "child", "kind": "draft_failed",
         "problem": "아이 메모 초안을 만들지 못했어요. 직접 확인해 주세요", "sentence": None}]}


def write_child(payload, child, index):
    content = common_content(payload)
    checks = [{"id": "c1", "item_key": "supplies", "kind": "date_check",
               "problem": "준비물 날짜를 확인해 주세요", "sentence": payload["supplies"]}] if index == 0 else []
    if child["memo"].strip():
        content["items"].append({"key": "child", "label": "아이 메모", "value": child["memo"],
                                 "source": {"type": "teacher_input"}})
        if any(word in child["memo"] for word in ("열", "다침", "약")):
            checks.append({"id": "sensitive", "item_key": "child", "kind": "sensitive",
                           "problem": "건강 관련 메모를 확인해 주세요", "sentence": child["memo"]})
    for request in child["requests"]:
        key = "day" if request["type"] == "inquiry" else request["type"]
        # 모의 API의 고정 귀가 요청 하나만 누락 확인 시연에 쓴다.
        if str(request["request_id"]) == str(REQUEST_PICKUP):
            checks.append({"id": f"request-{request['request_id']}", "item_key": key,
                           "kind": "request_missed", "problem": "보호자 요청을 초안에 반영해 주세요",
                           "sentence": None, "request_id": request["request_id"]})
        else:
            content["items"].append({"key": key, "label": "보호자 요청", "value": request["text"],
                                     "source": {"type": "request", "request_id": request["request_id"]}})
    return {"child_id": child["child_id"], "content": content, "open_checks": checks}


def write(payload):
    if "[실패]" in payload["activities"]:
        raise RuntimeError("대역 writer 전체 실패")
    result = []
    for index, child in enumerate(payload["children"]):
        try:
            result.append(write_child(payload, child, index))
        except Exception:
            result.append(failed_child(payload, child))
    return result
