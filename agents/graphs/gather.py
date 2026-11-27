"""자료 찾는 AI. 범위가 정해진 도구를 골라 불러서 답변 근거 후보를 모은다. 답은 쓰지 않는다.

toolbox는 specs()(도구 이름·설명·인자)와 call(name, args)(근거 조각 목록)를 가진다. 기관·아이·보호자 범위와
인자 검사는 toolbox가 맡고, 잘못된 인자면 ValueError를 올린다. 여기서는 부르는 횟수 상한과 중복·주입 거르기만 한다.
found 요약에는 조각마다 제목과 앞부분(head)을 줘서, 모은 자료로 답할 수 있는지 AI가 스스로 보고 끝내게 한다.
같은 (도구, 인자) 호출은 다시 실행하지 않고 이미 불렀다고만 알린다(판단이 아니라 중복 제거).
모델이나 도구가 실패하면 None을 돌려주고, 부른 쪽은 지금의 고정 검색으로 돌아간다.
"""

import json
import logging

from agents.graphs.answer import PERSONAL, _common, _evidence_key, _prompt, day_label
from agents.guardrails.injection import suspicious_chunk
from agents.guardrails.sensitive import mask_sensitive
from agents.llm import ModelError, OpenAIModel

MAX_ROUNDS = 3
MAX_CALLS = 4
MAX_CANDIDATES = 12
HEAD = 80  # found 요약에 보여 줄 조각 앞부분 글자 수
log = logging.getLogger(__name__)


def _title(chunk):
    return chunk.get("title") or chunk.get("document_title") or ""


def _items(chunks):
    """요약에 실을 조각: 제목과 앞부분. 주입 의심 조각은 결과에서도 빠지니 요약에도 싣지 않는다."""
    return [{"title": _title(chunk), "head": mask_sensitive(" ".join(chunk["content"].split()))[:HEAD]}
            for chunk in chunks if not suspicious_chunk(chunk["content"])]


def gather(question, toolbox, model=None, *, today=None, trace=None, who=None) -> list[dict] | None:
    trace = trace if trace is not None else []
    model = model if model is not None else OpenAIModel("GATHER")
    prompt = _common(today, who) + "\n" + _prompt("gather.md", "# 자료 찾기")
    specs = toolbox.specs()
    names = {spec["name"] for spec in specs}
    found, summary, seen, called = [], [], set(), set()
    for round_no in range(1, MAX_ROUNDS + 1):
        payload = {"question": mask_sensitive(question), "today": day_label(today), "tools": specs, "found": summary,
                   "round": round_no, "untrusted_data_fields": ["question", "found"]}
        try:
            answer = model.json(prompt, json.dumps(payload, ensure_ascii=False, default=str))
        except ModelError:
            trace.append("gather:failed")
            return None
        calls = answer.get("calls", []) if isinstance(answer, dict) else None
        if not isinstance(calls, list):
            trace.append("gather:failed")
            return None
        for call in calls[:MAX_CALLS]:
            name = call.get("tool") if isinstance(call, dict) else None
            args = call.get("args", {}) if isinstance(call, dict) else None
            if name not in names:
                trace.append(f"gather:bad:{str(name)[:40]}")
                summary.append({"tool": str(name)[:40], "count": 0, "items": [], "error": "없는 도구예요"})
                continue
            signature = (name, json.dumps(args, ensure_ascii=False, sort_keys=True, default=str))
            if signature in called:
                trace.append(f"gather:repeat:{name}")
                summary.append({"tool": name, "args": args, "repeat": "이미 부른 호출이에요. 결과는 앞의 found에 있어요"})
                continue
            called.add(signature)
            try:
                chunks = toolbox.call(name, args)
            except ValueError as error:  # 인자가 틀린 호출만 건너뛰고, 고칠 수 있게 이유를 다음 차례에 알려 줘요
                trace.append(f"gather:bad:{name}")
                summary.append({"tool": name, "args": args, "count": 0, "items": [], "error": str(error)})
                continue
            except Exception as error:  # noqa: BLE001 - 자료 조회가 깨지면 고정 검색이 다시 시도해요
                log.warning("자료 찾기 도구 실패 tool=%s error_type=%s", name, type(error).__name__)
                trace.append("gather:failed")
                return None
            trace.append(f"gather:{name}")
            for chunk in chunks:
                key = _evidence_key(chunk)
                if key not in seen:
                    seen.add(key)
                    found.append(chunk)
            summary.append({"tool": name, "args": args, "count": len(chunks), "items": _items(chunks)})
        if not calls or (isinstance(answer, dict) and answer.get("done") is True):
            break
    return sorted((item for item in found if not suspicious_chunk(item["content"])),
                  key=lambda item: (item.get("source") in PERSONAL, item["score"]), reverse=True)[:MAX_CANDIDATES]
