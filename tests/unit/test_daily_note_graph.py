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
            raise ModelError("가짜 실패")
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


def test_other_child_name_is_caught_by_code_even_if_checker_passes():
    writer = Script({"child": "지아와 블록으로 다퉜다가 화해했어요.", "requests": []})
    children = [kid("a", "지안", "지아랑 블록 다툼, 화해함"), kid("b", "지아")]
    note = draft_daily_notes(payload(children), writer, Script(OK))[0]
    assert [c["kind"] for c in note["open_checks"]] == ["other_child"]
    assert note["open_checks"][0]["id"] == "c1" and "지아" in note["open_checks"][0]["sentence"]


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
    [check] = note["open_checks"]
    assert check["kind"] == "request_missed" and check["request_id"] == "r1" and check["item_key"] == "medication"
    assert check["sentence"] is None


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
        {"key": "day", "value": "블록으로 동네를 만들었어요."},
        {"key": "child", "value": "오늘은 결석했어요."}]},
        "open_checks": [{"kind": "absent"}]}
    assert score(case, note)["pass"] is True
    note["open_checks"] = []
    assert score(case, note)["pass"] is False
