"""[제안] 기존 문의 답변의 인용 검증·가리기를 교직원 질문에도 적용해요."""

from agents.graphs import answer as graph
from agents.guardrails.sensitive import mask_sensitive


class MaskedModel:
    def __init__(self, model):
        self.model = model

    def json(self, system, user):
        return self.model.json(system, mask_sensitive(user))


def respond(question, search, sources, writer=None, checker=None):
    def safe_search(kind, query):
        return [{k: mask_sensitive(v) if isinstance(v, str) else v for k, v in chunk.items()}
                for chunk in search(kind, query)]

    try:
        draft = graph.draft_answer(mask_sensitive(question), safe_search,
                                  writer=MaskedModel(writer if writer is not None else graph.OpenAIModel("DOCUMENT")),
                                  checker=MaskedModel(checker if checker is not None else graph.OpenAIModel("CHECKER")))
    except Exception:
        draft = graph.fallback(["search", "write"])
    if draft["no_evidence"] or draft["conflict"] or not draft["check_result"]["passed"]:
        return {"answer": "자료에서 못 찾았어요", "evidence": []}
    evidence = [sources[e["chunk_id"]] for e in draft["evidence"] if e["chunk_id"] in sources]
    return {"answer": draft["text"] if evidence else "자료에서 못 찾았어요", "evidence": evidence}
