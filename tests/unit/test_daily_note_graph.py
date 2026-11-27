"""알림장 초안 그래프: 가짜 모델로 흐름(쓰기 → 코드 검사 → 검사 AI → 돌려보내기)을 확인한다."""

from agents.graphs.daily_note import MAX_RETURNS, draft_daily_notes
from agents.llm import ModelError

MENU = {"document_id": "doc-menu", "title": "11월 3주 식단표", "text": "점심: 카레라이스"}


def payload(children, supplies="없음", menu=MENU):
    return {"input_id": "in-1", "note_date": "2026-11-18", "classroom": "만 4세 별빛반",
            "activities": "재롱잔치 노래를 배웠어요.", "supplies": supplies, "children": children, "menu": menu}


def kid(child_id, name, memo="", requests=None):
    return {"child_id": child_id, "display_name": name, "memo": memo, "requests": requests or []}


class Script:
    """정해 둔 답을 차례로 돌려준다. ModelError를 넣으면 그 차례에 실패한다."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def json(self, system, user):
        self.calls += 1
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if answer is ModelError:
            raise ModelError("가짜 실패", format=True)  # 답 모양 실패: 그래프가 1번 더 묻는다
        if answer == "transport":
            raise ModelError("APITimeoutError")  # 전송 실패: llm.py가 이미 다시 했다
        return answer


OK = {"checks": []}


def keys(note):
    return [line["key"] for line in note["content"]["items"]]


def test_common_lines_and_empty_memo_skip_models():
    writer, checker = Script({"child": "x", "requests": []}), Script(OK)
    [note] = draft_daily_notes(payload([kid("a", "가온")], supplies="앞치마"), writer, checker)
    assert keys(note) == ["day", "supplies", "meal"]
    assert note["content"]["items"][2]["source"] == {"type": "document", "document_id": "doc-menu",
                                                      "document_title": "11월 3주 식단표"}
    assert note["open_checks"] == [] and writer.calls == checker.calls == 0


def test_no_supplies_and_no_menu_lines_are_left_out():
    [note] = draft_daily_notes(payload([kid("a", "가온")], supplies="없음", menu=None), Script({}), Script(OK))
    assert keys(note) == ["day"]


def test_child_line_from_memo():
    writer = Script({"child": "점심을 조금 먹었어요.", "requests": []})
    [note] = draft_daily_notes(payload([kid("a", "다온", "점심 조금 먹음")]), writer, Script(OK))
    line = note["content"]["items"][1]
    assert line == {"key": "child", "label": "아이 메모", "value": "점심을 조금 먹었어요.", "source": {"type": "teacher_input"}}
    assert note["open_checks"] == []
    assert "handoff_reason" not in note


def test_other_child_name_is_caught_by_code_even_if_checker_passes():
    writer = Script({"child": "지아와 블록으로 다퉜다가 화해했어요.", "requests": []})
    children = [kid("a", "지안", "지아랑 블록 다툼, 화해함"), kid("b", "지아")]
    note = draft_daily_notes(payload(children), writer, Script(OK))[0]
    assert [c["kind"] for c in note["open_checks"]] == ["other_child"]
    assert note["open_checks"][0]["id"] == "c1" and "지아" in note["open_checks"][0]["sentence"]


def test_roster_names_catches_other_child_outside_draft_batch():
    one_child = payload([kid("a", "지안", "블록 놀이")])
    one_child["roster_names"] = ["지안", "지아"]
    writer = Script({"child": "지아와 블록 놀이를 했어요.", "requests": []})
    [note] = draft_daily_notes(one_child, writer, Script(OK))
    assert [c["kind"] for c in note["open_checks"]] == ["other_child"]
    assert note["end"] == "needs_check"


def test_missing_request_is_returned_then_fixed():
    req = {"request_id": "r1", "type": "pickup", "text": "오늘 할머니가 데리러 가요"}
    writer = Script({"child": "블록 놀이를 했어요.", "requests": []},
                    {"child": "블록 놀이를 했어요.", "requests": [{"request_id": "r1", "value": "오늘은 할머니가 데리러 오세요."}]})
    [note] = draft_daily_notes(payload([kid("a", "노을", "블록놀이", [req])]), writer, Script(OK))
    assert writer.calls == 2
    pickup = next(line for line in note["content"]["items"] if line["key"] == "pickup")
    assert pickup["source"] == {"type": "request", "request_id": "r1"} and note["open_checks"] == []


def test_returns_stop_after_two_and_leave_check():
    req = {"request_id": "r1", "type": "medication", "text": "점심 후 약 먹여 주세요"}
    writer = Script({"child": "잘 지냈어요.", "requests": [{"request_id": "모르는-id", "value": "x"}]})
    [note] = draft_daily_notes(payload([kid("a", "아라", "블록놀이", [req])]), writer, Script(OK))
    assert writer.calls == MAX_RETURNS + 1
    check = note["open_checks"][0]
    assert check["kind"] == "request_missed" and check["request_id"] == "r1" and check["item_key"] == "medication"
    assert check["sentence"] is None
    assert note["open_checks"][1]["kind"] == "return_limit"


def test_not_in_memo_from_checker_is_returned_but_sensitive_is_not():
    writer = Script({"child": "편식이 심해요.", "requests": []}, {"child": "점심을 조금 먹었어요.", "requests": []})
    checker = Script({"checks": [{"item_key": "child", "kind": "not_in_memo", "problem": "메모에 없는 말", "sentence": "편식이 심해요."}]},
                     OK)
    [note] = draft_daily_notes(payload([kid("a", "다온", "점심 조금 먹음")]), writer, checker)
    assert writer.calls == 2 and note["open_checks"] == []

    writer = Script({"child": "넘어져 무릎이 살짝 긁혀 소독했어요.", "requests": []})
    checker = Script({"checks": [{"item_key": "child", "kind": "sensitive", "problem": "다침", "sentence": None}]})
    [note] = draft_daily_notes(payload([kid("a", "별하", "넘어져 무릎 긁힘, 소독함")]), writer, checker)
    assert writer.calls == 1 and [c["kind"] for c in note["open_checks"]] == ["sensitive"]


def test_unknown_kind_from_checker_is_ignored():
    checker = Script({"checks": [{"item_key": "child", "kind": "made_up"}, {"kind": "request_missed"}]})
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), Script({"child": "블록 놀이를 했어요."}), checker)
    assert note["open_checks"] == []


def test_writer_fails_twice_gives_draft_failed():
    writer = Script(ModelError)
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), writer, Script(OK))
    assert writer.calls == 2 and keys(note) == ["day", "meal"]
    assert [c["kind"] for c in note["open_checks"]] == ["draft_failed"]


def test_writer_retry_once_then_succeeds():
    writer = Script(ModelError, {"child": "블록 놀이를 했어요."})
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), writer, Script(OK))
    assert writer.calls == 2 and "child" in keys(note) and note["open_checks"] == []


def test_checker_fails_twice_gives_check_failed_and_keeps_draft():
    checker = Script(ModelError)
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), Script({"child": "블록 놀이를 했어요."}), checker)
    assert checker.calls == 2 and "child" in keys(note)
    assert [c["kind"] for c in note["open_checks"]] == ["check_failed"]


def test_writer_failure_handoff_reason():
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), Script(ModelError), Script(OK))
    assert note["end"] == "handoff" and note["handoff_reason"] == "draft_failed"


def test_checker_failure_handoff_reason():
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]),
                               Script({"child": "블록 놀이를 했어요."}), Script(ModelError))
    assert note["end"] == "handoff" and note["handoff_reason"] == "check_failed"


def test_medication_code_check_survives_checker_failure():
    req = {"request_id": "r1", "type": "medication", "text": "점심 후 약 먹여 주세요"}
    writer = Script({"child": None, "requests": [{"request_id": "r1", "value": "점심 후 약 요청이 있었어요."}]})
    [note] = draft_daily_notes(payload([kid("a", "가온", "", [req])]), writer, Script(ModelError))
    assert [c["kind"] for c in note["open_checks"]] == ["sensitive", "check_failed"]
    assert note["end"] == "handoff" and note["handoff_reason"] == "check_failed"


def test_return_limit_handoff_reason():
    req = {"request_id": "r1", "type": "pickup", "text": "오늘 할머니가 데리러 가요"}
    writer = Script({"child": "블록 놀이를 했어요.", "requests": []})
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록", [req])]), writer, Script(OK))
    assert writer.calls == MAX_RETURNS + 1
    assert note["end"] == "handoff" and note["handoff_reason"] == "return_limit"


def test_return_limit_adds_explicit_open_check():
    req = {"request_id": "r1", "type": "pickup", "text": "오늘 할머니가 데리러 가요"}
    writer = Script({"child": "블록 놀이를 했어요.", "requests": []})
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록", [req])]), writer, Script(OK))
    assert [c["kind"] for c in note["open_checks"]] == ["request_missed", "return_limit"]
    assert note["open_checks"][-1]["item_key"] == "child"
    assert note["open_checks"][-1]["problem"] == "AI가 두 번 고쳐도 남은 문제가 있어요. 직접 확인해 주세요."
    assert note["end"] == "handoff"


def test_one_note_per_child_in_order():
    children = [kid("a", "가온", "블록"), kid("b", "나래"), kid("c", "다온", "낮잠 잘 잠")]
    notes = draft_daily_notes(payload(children), Script({"child": "문장"}), Script(OK))
    assert [n["child_id"] for n in notes] == ["a", "b", "c"]
    assert ["child" in keys(n) for n in notes] == [True, False, True]


def test_eval_score_uses_only_ai_lines_and_flag_kind():
    from tools.eval_daily_note import score

    case = {"id": "ND-17", "category": "반 공통과 섞임", "must_not_include": ["만들었"], "expect_flag": True,
            "flag_kind": "absent", "must_include": ["결석"]}
    note = {"content": {"items": [
        {"key": "day", "value": "블록으로 동네를 만들었어요.", "source": {"type": "teacher_input"}},
        {"key": "child", "value": "오늘은 결석했어요.", "source": {"type": "teacher_input"}}]},
        "open_checks": [{"kind": "absent"}]}
    assert score(case, note)["pass"] is True
    note["open_checks"] = []
    assert score(case, note)["pass"] is False


def test_eval_request_score_needs_line_key_and_teacher_check():
    from tools.eval_daily_note import score_request

    req = {"request_key": "GR-05", "type": "medication", "trap": {"type": "dose_number"},
           "expect": {"line_key": "medication", "must_include": ["2.5ml"], "must_not_include": ["먹였어요"],
                      "teacher_check": "sensitive"}}
    line = {"key": "medication", "value": "점심 후 시럽 2.5ml 요청이 있었어요.", "source": {"type": "request", "request_id": "GR-05"}}
    note = {"content": {"items": [line]}, "open_checks": [{"kind": "sensitive"}]}
    assert score_request(req, note)["pass"] is True
    assert score_request(req, {**note, "open_checks": []})["pass"] is False
    assert score_request(req, {"content": {"items": []}, "open_checks": [{"kind": "request_missed"}]})["covered"] is False


def test_memo_left_out_without_check_returns_then_hands_off():
    writer = Script({"child": None})
    [note] = draft_daily_notes(payload([kid("a", "다온", "블록을 친구와 나누어 쌓음")]), writer, Script(OK))
    assert writer.calls == MAX_RETURNS + 1
    assert "child" not in keys(note)
    assert [c["kind"] for c in note["open_checks"]] == ["return_limit"]
    assert note["end"] == "handoff" and note["handoff_reason"] == "return_limit"
    assert note["trace"][-2]["memo_left_out"] is True


def test_memo_left_out_is_returned_then_fixed():
    writer = Script({"child": None}, {"child": "친구와 블록을 나누어 쌓았어요."})
    [note] = draft_daily_notes(payload([kid("a", "다온", "블록을 친구와 나누어 쌓음")]), writer, Script(OK))
    assert writer.calls == 2 and "child" in keys(note) and note["open_checks"] == []


def test_memo_left_out_preserves_sensitive_check():
    checker = Script({"checks": [{"item_key": "child", "kind": "sensitive", "problem": "다침", "sentence": None}]})
    [note] = draft_daily_notes(payload([kid("a", "다온", "무릎을 다침")]), Script({"child": None}), checker)
    assert [c["kind"] for c in note["open_checks"]] == ["sensitive"]


def test_not_in_memo_check_does_not_hide_missing_child_line():
    checker = Script({"checks": [{"item_key": "child", "kind": "not_in_memo", "problem": "근거 없음", "sentence": None}]})
    [note] = draft_daily_notes(payload([kid("a", "다온", "블록을 친구와 나누어 쌓음")]),
                               Script({"child": None}), checker)
    assert [c["kind"] for c in note["open_checks"]] == ["not_in_memo", "return_limit"]


def test_memo_rewrite_signal_is_not_exposed_when_checker_fails():
    [note] = draft_daily_notes(payload([kid("a", "다온", "블록 놀이")]),
                               Script({"child": None}), Script(ModelError))
    assert [c["kind"] for c in note["open_checks"]] == ["check_failed"]


def test_memo_left_out_with_checker_kind_adds_nothing_more():
    checker = Script({"checks": [{"item_key": "child", "kind": "date_check", "problem": "날짜", "sentence": None}]})
    [note] = draft_daily_notes(payload([kid("a", "라온", "앞치마 내일")]), Script({"child": None}), checker)
    assert [c["kind"] for c in note["open_checks"]] == ["date_check"]


def test_other_child_name_in_memo_is_caught_even_when_line_left_out():
    children = [kid("a", "지안", "지아 점심 다 먹음"), kid("b", "지아")]
    note = draft_daily_notes(payload(children), Script({"child": None}), Script(OK))[0]
    assert [c["kind"] for c in note["open_checks"]] == ["other_child"]


def test_medication_request_line_always_gets_teacher_check():
    req = {"request_id": "r1", "type": "medication", "text": "점심 먹고 시럽 2.5ml 먹여 주세요"}
    writer = Script({"child": None, "requests": [{"request_id": "r1", "value": "점심 후 시럽 2.5ml를 먹여 달라는 요청이 있었어요."}]})
    [note] = draft_daily_notes(payload([kid("a", "로아", "", [req])]), writer, Script(OK))
    [check] = note["open_checks"]
    assert check["kind"] == "sensitive" and check["item_key"] == "medication" and check["request_id"] == "r1"


def test_concurrent_run_keeps_child_order_and_same_result():
    import threading
    import time

    class Slow:
        def __init__(self):
            self.active = self.peak = 0
            self.lock = threading.Lock()

        def json(self, system, user):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            return {"checks": []} if '"draft"' in user else {"child": "문장", "requests": []}

    children = [kid(str(i), f"아이{i}", "메모") for i in range(8)]
    model = Slow()
    together = draft_daily_notes(payload(children), model, model, workers=4)
    one_by_one = draft_daily_notes(payload(children), Slow(), Slow(), workers=1)
    assert [n["child_id"] for n in together] == [str(i) for i in range(8)]
    assert together == one_by_one
    assert 1 < model.peak <= 4


WEEK = """# 11월 3주 식단표 (11/16~11/20)

| 날짜 | 점심 | 오후 간식 |
| --- | --- | --- |
| 11-17(화) | 차조밥, 콩나물국 | 고구마 |
| 11-18(수) | 카레라이스②⑥, 계란국① | 사과 |
"""


def test_meal_line_uses_only_that_day_row():
    from agents.graphs.daily_note import meal_text

    assert meal_text(WEEK, "2026-11-18") == "점심: 카레라이스②⑥, 계란국① / 오후 간식: 사과"
    assert meal_text(WEEK, "2026-11-20") == WEEK  # 행이 없으면 원문
    assert meal_text("점심: 카레라이스", "2026-11-18") == "점심: 카레라이스"


def test_same_line_same_kind_checks_are_merged():
    req = {"request_id": "r1", "type": "medication", "text": "점심 후 약 먹여 주세요"}
    writer = Script({"child": None, "requests": [{"request_id": "r1", "value": "점심 후 약을 먹여 달라는 요청이 있었어요."}]})
    checker = Script({"checks": [{"item_key": "medication", "kind": "sensitive", "problem": "투약", "sentence": "x"}]})
    [note] = draft_daily_notes(payload([kid("a", "지아", "", [req])]), writer, checker)
    [check] = note["open_checks"]
    assert check["kind"] == "sensitive" and check["request_id"] == "r1"


def test_unanswered_inquiry_keeps_text_without_code_check():
    req = {"request_id": "r1", "type": "inquiry", "text": "기침해요. 낮잠 때 잘 봐 주세요."}
    writer = Script({"child": "블록 놀이를 했어요.",
                     "requests": [{"request_id": "r1", "value": "기침을 한다고 알려 주셨어요.", "answered": False}]})
    [note] = draft_daily_notes(payload([kid("a", "새봄", "블록놀이", [req])]), writer, Script(OK))
    line = next(item for item in note["content"]["items"] if item["source"]["type"] == "request")
    assert line["value"] == "기침을 한다고 알려 주셨어요." and "_unanswered" not in line
    assert note["open_checks"] == []


def test_request_line_repeating_child_line_becomes_request_text():
    req = {"request_id": "r1", "type": "inquiry", "text": "요즘 친구랑 잘 지내나요?"}
    writer = Script({"child": "친구에게 먼저 사과했어요.",
                     "requests": [{"request_id": "r1", "value": "친구에게 먼저 사과했어요."}]})
    [note] = draft_daily_notes(payload([kid("a", "윤슬", "친구에게 먼저 사과함", [req])]), writer, Script(OK))
    line = next(item for item in note["content"]["items"] if item["source"]["type"] == "request")
    assert line["value"] == "보호자 요청: 요즘 친구랑 잘 지내나요?"
    assert note["open_checks"] == []


def test_eval_memo_score_ignores_request_checks():
    from tools.eval_daily_note import score

    case = {"id": "ND-03", "category": "지어내기", "must_not_include": ["협동"], "expect_flag": False,
            "flag_kind": None, "must_include": []}
    note = {"content": {"items": [{"key": "child", "value": "블록놀이를 했어요.", "source": {"type": "teacher_input"}}]},
            "open_checks": [{"kind": "sensitive", "item_key": "day", "request_id": "GR-14"}]}
    assert score(case, note)["pass"] is True


def test_eval_memo_score_rejects_missing_child_line_without_safety_reason():
    from tools.eval_daily_note import score

    case = {"id": "ND-03", "category": "지어내기", "memo": "블록 놀이", "must_not_include": [],
            "expect_flag": False, "flag_kind": None, "must_include": []}
    note = {"content": {"items": []}, "open_checks": [{"kind": "return_limit", "item_key": "child"}]}
    result = score(case, note)
    assert result["pass"] is False and result["banned_hits"] == ["(child 줄 없음)"]


def test_model_retries_only_retryable_errors_with_backoff():
    from agents.llm import ModelError, OpenAIModel

    class Timeout(Exception):
        pass

    Timeout.__name__ = "APITimeoutError"

    class BadRequest(Exception):
        status_code = 400

    waits = []
    model = OpenAIModel("DOCUMENT", sleep=waits.append)
    calls = iter([Timeout(), Timeout(), '{"ok": true}'])

    def fake_call(system, user):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    model._call = fake_call
    assert model.json("s", "u") == {"ok": True} and waits == [1.0, 2.0]

    model = OpenAIModel("DOCUMENT", sleep=waits.append)
    model._call = lambda s, u: (_ for _ in ()).throw(BadRequest())
    waits.clear()
    try:
        model.json("s", "u")
        raise AssertionError("ModelError가 나야 해요")
    except ModelError:
        assert waits == []


def test_transport_failure_is_not_asked_again_in_graph():
    writer = Script("transport")
    [note] = draft_daily_notes(payload([kid("a", "가온", "블록")]), writer, Script(OK))
    assert writer.calls == 1 and [c["kind"] for c in note["open_checks"]] == ["draft_failed"]
    assert note["end"] == "handoff"


def test_trace_keeps_first_and_final_draft_and_end():
    writer = Script({"child": "편식이 심해요.", "requests": []}, {"child": "점심을 조금 먹었어요.", "requests": []})
    checker = Script({"checks": [{"item_key": "child", "kind": "not_in_memo", "problem": "메모에 없는 말", "sentence": "편식이 심해요."}]}, OK)
    [note] = draft_daily_notes(payload([kid("a", "다온", "점심 조금 먹음")]), writer, checker)
    steps = [t["step"] for t in note["trace"]]
    assert steps == ["write", "check", "return", "write", "check", "end"]
    assert note["trace"][0]["lines"][0]["value"] == "편식이 심해요."
    assert note["trace"][3]["lines"][0]["value"] == "점심을 조금 먹었어요."
    assert note["end"] == "done" and "생각" not in str(note["trace"])


def test_stub_and_graph_have_same_common_lines_with_fake_models():
    from app.modules.daily_notes import stub_writer

    for supplies in ("[TEST] 앞치마", "없음", "", "  없음  "):
        for menu in (None, {**MENU, "text": WEEK}):
            data = payload([kid("a", "가온", "[TEST] 블록 놀이")], supplies=supplies, menu=menu)
            graph = draft_daily_notes(data, Script({"child": "[TEST] 블록 놀이", "requests": []}), Script(OK))[0]
            stub = stub_writer.write(data)[0]
            def common(row):
                return [line for line in row["content"]["items"] if line["key"] in ("day", "supplies", "meal")]
            assert common(stub) == common(graph)
            assert stub_writer.failed_child(data, data["children"][0])["content"]["items"] == common(graph)


def test_stub_checks_protected_roster_name_during_partial_regenerate():
    from app.modules.daily_notes import stub_writer

    data = payload([kid("a", "가온", "[TEST] 나래와 블록 놀이")])
    data["roster_names"] = ["가온", "나래"]
    [note] = stub_writer.write(data)
    checks = [c for c in note["open_checks"] if c["kind"] == "other_child"]
    assert len(checks) == 1 and checks[0]["id"] and "나래" in checks[0]["sentence"]
