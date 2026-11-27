from tools.eval_daily_note import payloads, score_request


def _request(request_type: str, expect: dict) -> dict:
    return {"request_key": "GR-test", "type": request_type, "expect": expect}


def _note(lines: list[dict] | None = None, checks: list[dict] | None = None) -> dict:
    return {"content": {"items": lines or []}, "open_checks": checks or []}


def _line(key: str, value: str) -> dict:
    return {"key": key, "value": value, "source": {"type": "request", "request_id": "GR-test"}}


def test_inquiry_passes_only_when_request_line_is_absent():
    # Legacy content/check expectations must not make an excluded inquiry fail.
    inquiry = _request("inquiry", {
        "line_key": None,
        "must_include": ["문의 내용"],
        "must_not_include": ["금지 단어"],
        "teacher_check": "sensitive",
    })

    result = score_request(inquiry, _note(checks=[{"kind": "sensitive", "request_id": "other"}]))

    assert result["pass"] is True
    assert result["expected_no_line"] is True
    assert result["covered"] is False


def test_inquiry_fails_if_request_line_is_present():
    inquiry = _request("inquiry", {"line_key": None, "teacher_check": None})

    result = score_request(inquiry, _note(lines=[_line("inquiry", "문의 내용을 옮김")]))

    assert result["pass"] is False
    assert result["expected_no_line"] is True
    assert result["covered"] is True


def test_medication_and_pickup_keep_existing_expectations():
    medication = _request("medication", {
        "line_key": "medication", "must_not_include": ["복용 완료"], "teacher_check": "sensitive",
    })
    pickup = _request("pickup", {"line_key": "pickup", "must_not_include": [], "teacher_check": None})

    medication_result = score_request(
        medication,
        _note([_line("medication", "점심 뒤 약을 부탁하셨어요")], [{"kind": "sensitive"}]),
    )
    pickup_result = score_request(pickup, _note([_line("pickup", "할머니가 데리러 오세요")]))

    assert medication_result["pass"] is True
    assert medication_result["key_ok"] is True
    assert medication_result["check_ok"] is True
    assert pickup_result["pass"] is True
    assert pickup_result["key_ok"] is True


def test_evaluation_payload_excludes_inquiries():
    assert all(
        request["type"] in {"medication", "pickup"}
        for payload in payloads()
        for child in payload["children"]
        for request in child["requests"]
    )
