"""[TEST] 보호자 기억의 확인 전 차단과 가정·반 경계를 확인해요."""
from uuid import uuid4
import pytest
from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api import test_memories, test_memory_learning
from tests.integration.api.test_memory_learning import find, change

# 다른 시험 파일의 fixture를 이름으로 묶어 둬요(import하면 ruff F811 오탐).
memory_backend = test_memories.memory_backend
saved_case = test_memory_learning.saved_case


def save(mode, candidates, body=None, **changes):
    req = dict(id=uuid4(), org_id=seed.ORG, requester_id=seed.PARENT, child_id=seed.CHILDREN[0]['id'],
               body=body or '견과류 알레르기가 있어요. 평소 상담은 오후 4시 이후를 선호해요.', **changes)
    # 알림의 요청 FK를 위해 실제 접수 대신 기본 시드 요청을 출처로 써요.
    req['id'] = seed.DEMO_NOTE_REQUESTS[0]['id']
    if mode == 'db':
        with transaction() as c:
            backend.memories.save_parent_candidates(c, req, candidates, [x['display_name'] for x in seed.CHILDREN])
    else:
        backend.memories.save_parent_candidates(req, candidates, [x['display_name'] for x in seed.CHILDREN])
    return req


def load(mode, child_id, reader_id):
    if mode == 'db':
        with transaction() as c:
            return backend.memories.load_child_notes(c, seed.ORG, child_id, reader_id)
    return backend.memories.load_child_notes(seed.ORG, child_id, reader_id)


CARE = dict(kind='care_note', content='견과류 알레르기가 있어요.')
PREF = dict(kind='preference', content='평소 상담은 오후 4시 이후를 선호해요.', structured={'after': '16:00'})


def test_memory_parent_pending_dedupe_and_preference(memory_backend):
    req = save(memory_backend, [CARE, PREF])
    save(memory_backend, [CARE, PREF])
    assert load(memory_backend, req['child_id'], seed.PARENT) == []
    if memory_backend == 'db':
        from sqlalchemy import text
        with transaction() as c:
            rows = c.execute(text("SELECT kind,confirm_status FROM memories")).all()
            assert sorted(rows) == [('care_note','pending'), ('preference','confirmed')]
            assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind='memory_candidate'")) == 1
            assert backend.memories.load_preferences(c, seed.ORG, seed.PARENT)[0]['structured']['after'] == '16:00'
    else:
        assert len(store.state().memories) == 2
        assert len([n for n in store.state().notifications.values() if n.kind == 'memory_candidate']) == 1
        assert backend.memories.load_preferences(seed.ORG, seed.PARENT)[0]['structured']['after'] == '16:00'


def test_memory_parent_rejects_temporary_diagnosis_other_child_and_sensitive(memory_backend):
    from sqlalchemy import text
    for body, content in [('오늘만 낮잠 전에 책을 읽어 주세요.','낮잠 전에 책을 읽어 주세요.'),
                          ('ADHD 진단으로 낮잠이 어려워요.','낮잠이 어려워요.'),
                          ('친구는 견과류 알레르기가 있어요.',CARE['content']),
                          ('낮잠 연락은 010-1234-5678로 해요.','낮잠 연락은 010-1234-5678로 해요.'),
                          ('견과류 알레르기는 없어요.',CARE['content'])]:
        save(memory_backend, [dict(kind='care_note',content=content)],body)
    save(memory_backend, [dict(kind='preference',content='평소 견과류 알레르기가 있어요.')],
         '평소 견과류 알레르기가 있어요.')
    if memory_backend == 'db':
        with transaction() as c:
            assert c.scalar(text('SELECT count(*) FROM memories')) == 0
    else:
        assert not store.state().memories


def test_memory_child_reader_scope_and_deleted(memory_backend):
    from sqlalchemy import text
    req = save(memory_backend, [CARE])
    if memory_backend == 'db':
        with transaction() as c:
            c.execute(text("UPDATE memories SET confirm_status='confirmed',confirmed_at=now()"))
    else:
        for m in store.state().memories.values():
            m.confirm_status = 'confirmed'
    assert load(memory_backend, req['child_id'], seed.PARENT)
    assert load(memory_backend, req['child_id'], seed.TEACHER)
    assert not load(memory_backend, req['child_id'], seed.TEACHER_OTHER)
    assert not load(memory_backend, req['child_id'], seed.DIRECTOR)
    assert not load(memory_backend, seed.CHILDREN[1]['id'], seed.PARENT)
    assert not load(memory_backend, req['child_id'], seed.PARENT_OTHER)
    if memory_backend == 'db':
        with transaction() as c:
            c.execute(text('UPDATE memories SET deleted_at=now()'))
    else:
        for m in store.state().memories.values():
            m.deleted_at=store.now()
    assert not load(memory_backend, req['child_id'], seed.TEACHER)


def test_memory_parent_get_scope_and_candidate_detail(client,parent,parent_other,teacher,director,memory_backend):
    req=save(memory_backend,[CARE,PREF])
    own=client.get('/api/v1/memories',headers=parent)
    assert own.status_code==200
    items=own.json()['items']
    assert {m['kind'] for m in items}=={'care_note','preference'}
    care=next(m for m in items if m['kind']=='care_note')
    assert care['child_name']==seed.CHILDREN[0]['display_name'] and care['confirm_status']=='pending'
    assert care['confirmed_at'] is None and care['title'] and care['source']=='memory'
    for headers in (parent_other,teacher,director):
        result=client.get('/api/v1/memories?kind=care_note',headers=headers)
        assert result.status_code==200 and result.json()['items']==[]
    detail=client.get(f"/api/v1/requests/{req['id']}",headers=parent)
    assert detail.status_code==200 and detail.json()['memory_candidates'][0]['id']==care['id']


def test_memory_parent_confirmation_discard_delete(client,parent,parent_other,teacher,memory_backend):
    req=save(memory_backend,[CARE])
    mid=client.get('/api/v1/memories?kind=care_note',headers=parent).json()['items'][0]['id']
    path=f'/api/v1/memories/{mid}/confirm'
    assert client.post(path,headers=parent_other,json={'decision':'remember'}).status_code==404
    assert client.post(path,headers=teacher,json={'decision':'remember'}).status_code==403
    confirmed=client.post(path,headers=parent,json={'decision':'remember'})
    assert confirmed.status_code==200 and confirmed.json()['confirmed_at']
    assert load(memory_backend,req['child_id'],seed.TEACHER)==[CARE]
    assert client.post(path,headers=parent,json={'decision':'discard'}).status_code==409
    assert client.delete(f'/api/v1/memories/{mid}',headers=parent).status_code==204
    assert not load(memory_backend,req['child_id'],seed.TEACHER)
    assert client.post(path,headers=parent,json={'decision':'remember'}).status_code==404
    save(memory_backend,[CARE])
    mid=client.get('/api/v1/memories?kind=care_note',headers=parent).json()['items'][0]['id']
    path=f'/api/v1/memories/{mid}/confirm'
    assert client.post(path,headers=parent,json={'decision':'discard'}).json()['confirm_status']=='discarded'
    row=client.get('/api/v1/memories?kind=care_note',headers=parent).json()['items'][0]
    assert row['content']=='' and row['structured']=={} and row['confirmed_at'] is None
    assert client.post(path,headers=parent,json={'decision':'remember'}).status_code==409
    assert not load(memory_backend,req['child_id'],seed.PARENT)


def test_memory_saved_answer_toggle_scope_and_invalidation(client,teacher,teacher_other,director,parent,saved_case):
    from tests.integration.api.helpers import decision
    assert decision(client,teacher,saved_case.cid).status_code==200
    listed=client.get('/api/v1/memories?kind=saved_answer',headers=teacher).json()
    assert len(listed['saved_answers'])==1 and listed['items'][0]['source']=='saved_answer'
    assert listed['items'][0]['kind']=='saved_answer'
    path='/api/v1/saved-answers/'+listed['saved_answers'][0]['id']
    assert client.patch(path,headers=teacher_other,json={'status':'off'}).status_code==404
    assert client.patch(path,headers=parent,json={'status':'off'}).status_code==403
    assert client.patch(path,headers=teacher,json={'status':'off'}).status_code==200
    assert find(saved_case) is None
    assert client.patch(path,headers=director,json={'status':'active'}).status_code==200
    assert find(saved_case)
    change(saved_case,'documents' if saved_case.mode=='db' else 'saved_answers',
           'status','superseded' if saved_case.mode=='db' else 'invalidated')
    assert client.patch(path,headers=teacher,json={'status':'active'}).status_code==409


@pytest.mark.parametrize('withdrawn, kinds', [('child_health', ['preference']), ('ai_processing', [])])
def test_memory_parent_needs_consent_for_each_kind(memory_backend, withdrawn, kinds):
    from sqlalchemy import text
    if memory_backend == 'db':
        with transaction() as c:
            c.execute(text("DELETE FROM user_consents WHERE user_id=:user AND item=:item"),
                      {'user': seed.PARENT, 'item': withdrawn})
    else:
        for key in [k for k in store.state().consents if k[1] == seed.PARENT and k[2] == withdrawn]:
            del store.state().consents[key]
    save(memory_backend, [CARE, PREF])
    if memory_backend == 'db':
        with transaction() as c:
            assert sorted(c.scalars(text("SELECT kind FROM memories"))) == kinds
            assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind='memory_candidate'")) == 0
    else:
        assert sorted(m.kind for m in store.state().memories.values()) == kinds
        assert not [n for n in store.state().notifications.values() if n.kind == 'memory_candidate']
