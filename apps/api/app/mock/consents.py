"""[제안] 동의 기록은 최초 시각을 유지하고 약관 판별로 보관해요."""

from app.core import consents as rules
from app.core.constants import CONSENT_VERSION
from app.mock import store
from app.mock.feed import record


def get(user):
    with store._lock:
        agreed = {item: at for (org, uid, item, version), at in store.state().consents.items()
                  if (org, uid, version) == (user.org_id, user.id, CONSENT_VERSION)}
        return rules.view(user.role, agreed)


def agree(user, items, terms_version):
    required = rules.validate(user, items, terms_version)
    with store._lock:
        changed = False
        agreed_at = store.now()
        for item in required:
            key = (user.org_id, user.id, item, terms_version)
            if key not in store.state().consents:
                store.state().consents[key] = agreed_at
                changed = True
        if changed:
            record(user, "consent_agreed", items=required, terms_version=terms_version)
        return get(user)


def classroom(user, classroom_id):
    with store._lock:
        state = store.state()
        row = state.classrooms.get(classroom_id)
        rules.check_classroom(user, classroom_id, row.org_id if row else None)
        completed = {u.id for u in state.users.values() if u.org_id == user.org_id and u.role == "parent"
                     and get(u)["complete"]}
        return {"items": [rules.child_view(c.id, c.display_name, c.guardian_ids, completed)
                          for c in sorted(state.children.values(), key=lambda c: (c.display_name, c.id))
                          if c.org_id == user.org_id and c.classroom_id == classroom_id]}
