"""데모 사용자별 알림 설정 대역이에요."""

def get(user_id, *, connection=None):
    from app.mock import store
    with store._lock:
        return store.state().user_settings.get(user_id, {"quiet_start": None, "quiet_end": None}).copy()


def save(user, body):
    from app.mock import store
    with store._lock:
        if body.quiet_start is None:
            store.state().user_settings.pop(user.id, None)
        else:
            store.state().user_settings[user.id] = body.model_dump()
        return get(user.id)
