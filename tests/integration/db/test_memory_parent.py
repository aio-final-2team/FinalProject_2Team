"""[TEST] 모델은 가짜로 두고 커밋 뒤 추출·작성 입력·시드를 확인해요."""
import json
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import text
from agents.graphs import answer, daily_note
from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed
from app.modules.memories import memories
from app.modules.requests import graph_agent
from app.modules.daily_notes.runner import _payload
from tests.integration.db.test_answer_t33 import create_card
from tests.integration.db.test_memory_learning import approve
from tests.integration.api.test_memory_parent import CARE, PREF


def test_memory_parent_after_commit_and_input_isolation(db_client, monkeypatch):
    monkeypatch.setenv('LLM_MODEL_MEMORY','fake-memory')
    calls=[]
    def extract(system, user):
        calls.append(json.loads(user))
        with transaction() as c:
            assert c.scalar(text("SELECT count(*) FROM approvals")) == 1
            assert c.scalar(text("SELECT count(*) FROM requests WHERE status='sent_or_booked'")) == 1
        return {'candidates':[CARE,PREF]}
    monkeypatch.setattr(memories,'OpenAIModel',lambda role: SimpleNamespace(json=extract))
    card,_,_=create_card(db_client, CARE['content']+' '+PREF['content'])
    approve(db_client,card,'approve')
    assert len(calls)==1 and 'parent_body' in calls[0]
    seen=[]
    monkeypatch.setenv('ANSWER_WRITER','graph')
    monkeypatch.setattr(answer,'OpenAIModel',lambda role: SimpleNamespace(json=lambda s,u: seen.append((role,json.loads(u))) or
                        ({'text':'','evidence':[]} if role=='DOCUMENT' else {'passed':True,'issues':[]})))
    state={'request_id':card['request_id'],'parallel':{'chunks':[],'memories':[]}}
    draft=graph_agent._write_request(state)['draft']
    assert seen[-1][1]['child_notes']==[] and seen[-1][1]['preferences'][0]['content']==PREF['content']
    entry={'id':'[TEST]','org_id':seed.ORG,'classroom_id':seed.CLASS_STAR,'author_id':seed.TEACHER,
           'note_date':datetime.now(KST).date(),'child_memos':[],'activities':'[TEST] 놀이','supplies':''}
    with transaction() as c:
        payload=_payload(c,entry)
        assert all(child['care_notes']==[] for child in payload['children'])
        c.execute(text("UPDATE memories SET confirm_status='confirmed',confirmed_at=now() WHERE kind='care_note'"))
    graph_agent._write_request(state)
    assert seen[-1][1]['child_notes']==[CARE]
    graph_agent._check_request({**state,'draft':draft})
    assert all(key not in seen[-1][1] for key in ('preferences','child_notes','memories'))
    with transaction() as c:
        payload=_payload(c,entry)
    own=next(x for x in payload['children'] if x['child_id']==str(seed.CHILD))
    assert own['care_notes']==[CARE]
    assert all(x['care_notes']==[] for x in payload['children'] if x!=own)
    model=SimpleNamespace(json=lambda s,u: seen.append(('daily',json.loads(u))) or {'child':'','checks':[]})
    daily_note.write(model,payload,own,[])
    assert seen[-1][1]['care_notes']==[CARE]
    daily_note.review(model,payload,own,[])
    assert 'care_notes' not in seen[-1][1]


def test_memory_parent_disabled_and_failure_use_fallback_without_changing_request(db_client, monkeypatch):
    """[TEST] 모델 없음·실패 대역: 낱말 후보를 같은 선으로 저장하고, 요청 상태는 그대로예요."""
    monkeypatch.setenv('LLM_MODEL_MEMORY','')
    monkeypatch.setattr(memories,'OpenAIModel',lambda role: (_ for _ in ()).throw(RuntimeError('[TEST] fail')))
    care='[TEST] 평소 낮잠 전에 책을 읽어 줘요.'
    card,_,_=create_card(db_client,care)
    approve(db_client,card,'approve')
    with transaction() as c:
        assert c.execute(text('SELECT kind,confirm_status,content FROM memories')).all()==[('care_note','pending',care)]
        assert c.scalar(text("SELECT count(*) FROM events WHERE agent_name='memory' AND action='tool_failed'"))==0
        c.execute(text('DELETE FROM notifications'))
        c.execute(text('DELETE FROM memories'))
    monkeypatch.setenv('LLM_MODEL_MEMORY','fake-memory')
    memories.after_request(card['request_id'])
    with transaction() as c:
        assert c.scalar(text("SELECT count(*) FROM events WHERE agent_name='memory' AND action='tool_failed'"))==1
        assert c.execute(text('SELECT kind,confirm_status FROM memories')).all()==[('care_note','pending')]
        assert c.scalar(text('SELECT status FROM requests WHERE id=:id'),{'id':card['request_id']})=='sent_or_booked'


def test_memory_parent_model_is_asked_without_keywords_and_may_answer_none(db_client, monkeypatch):
    """[TEST] 낱말이 없어도 동의가 있으면 기억 AI에 묻고, AI가 0개라 하면 대역 낱말로 덮지 않아요."""
    monkeypatch.setenv('LLM_MODEL_MEMORY','fake-memory')
    calls=[]
    monkeypatch.setattr(memories,'OpenAIModel',lambda role: SimpleNamespace(
        json=lambda s,u: calls.append(json.loads(u)) or {'candidates':[]}))
    card,_,_=create_card(db_client,'[TEST] 준비물 알려 주세요. '+CARE['content'])
    approve(db_client,card,'approve')
    assert len(calls)==1 and calls[0]['parent_body'].startswith('[TEST] 준비물')
    with transaction() as c:
        assert c.scalar(text('SELECT count(*) FROM memories'))==0
        c.execute(text("DELETE FROM user_consents WHERE user_id=:user AND item='ai_processing'"),{'user':seed.PARENT})
    memories.after_request(card['request_id'])
    assert len(calls)==1


def test_memory_parent_seed_and_migration_roundtrip(seeded_db,alembic_config):
    from alembic import command
    from db.seeds.care_notes import seed_care_notes
    with transaction() as c:
        seed_care_notes(c)
        seed_care_notes(c)
        assert c.scalar(text("SELECT count(DISTINCT child_id) FROM memories WHERE confirm_status='confirmed'"))==12
        assert c.scalar(text("SELECT count(*) FROM memories WHERE confirm_status='pending'"))==3
        assert c.scalar(text("SELECT count(*) FROM memories WHERE owner_id=:id AND confirm_status='pending'"),{'id':seed.PARENT})==1
        assert c.scalar(text("SELECT bool_and((structured->>'is_virtual')::bool) FROM memories"))
    command.downgrade(alembic_config,'0016')
    with transaction() as c:
        c.execute(text("INSERT INTO memories(org_id,owner_id,kind,content) VALUES (:org,:owner,'tone','[TEST] 기존 기억')"),
                  {'org':seed.ORG,'owner':seed.TEACHER})
    command.upgrade(alembic_config,'head')
    with transaction() as c:
        assert c.execute(text('SELECT confirm_status,child_id,confirmed_at FROM memories')).one()==('confirmed',None,None)


def test_memory_parent_consultation_explicit_time_wins(seeded_db,monkeypatch):
    from app.modules.consultations import slots
    from tests.integration.api.test_memory_parent import save
    from app import backend
    monkeypatch.setattr(backend,'memories',memories)
    req=save('db',[PREF])
    seen=[]
    monkeypatch.setattr(slots,'find_consult_slots',lambda *a,**kw: seen.append(kw['preference']) or [])
    with transaction() as c:
        slots.propose_slots(c,{**req,'body':'상담 부탁해요.'},{'id':None},seed.TEACHER)
        assert seen[-1]=={'after':'16:00'}
        slots.propose_slots(c,{**req,'body':'오후 2시 상담 부탁해요.'},{'id':None},seed.TEACHER)
        assert seen[-1]=={'after':'14:00','before':'14:30'}  # 모델 없음 정규식 대역


def test_consultation_time_ai_value_reaches_slot_search(seeded_db,monkeypatch):
    """[TEST] 감독 모델이 켜져 있으면 상담 후보를 만들 때 작은 AI 호출의 구조값을 써요."""
    from app.modules.consultations import slots
    from tests.integration.api.test_memory_parent import save
    from app import backend
    monkeypatch.setattr(backend,'memories',memories)
    req=save('db',[PREF])
    monkeypatch.setenv('LLM_MODEL_SUPERVISOR','fake-model')
    texts,seen=[],[]
    monkeypatch.setattr(slots,'OpenAIModel',lambda role,timeout=None: SimpleNamespace(
        json=lambda s,u: texts.append(json.loads(u)['text']) or {'weekdays':[3],'part_of_day':'pm'}))
    monkeypatch.setattr(slots,'find_consult_slots',lambda *a,**kw: seen.append(kw['preference']) or [])
    with transaction() as c:
        slots.propose_slots(c,{**req,'body':'[TEST] 목요일 느지막이 뵙고 싶어요.'},{'id':None},seed.TEACHER)
    assert texts==['[TEST] 목요일 느지막이 뵙고 싶어요.'] and seen[-1]=={'weekdays':[3],'part_of_day':'pm'}
