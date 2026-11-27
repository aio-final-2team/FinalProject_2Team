"""[TEST] 보낸 알림장만 아이별 문의 근거가 되고 다른 가정에는 넘어가지 않아요."""
import json
from datetime import timedelta
from uuid import uuid4, UUID
from sqlalchemy import text
from app.core.db import transaction
from app.mock import seed,store
from tests.integration.api.test_memories import memory_backend
from tests.integration.api.test_cards import create,detail
from tests.integration.api.helpers import decision


def add_note(mode,offset,child_id=seed.CHILD, status='sent'):
    day=store.now().date()-timedelta(days=offset)
    child=next(c for c in seed.CHILDREN if c['id']==child_id)
    note_teacher=seed.TEACHER if child['classroom_id']==seed.CLASS_STAR else seed.TEACHER_OTHER
    content={'items':[{'key':'day','label':'오늘 하루','value':f'[TEST] {offset}일 전 낮잠을 잘 잤어요.','source':{'type':'teacher_input'}}]}
    nid=uuid4()
    if mode=='db':
        with transaction() as c:
            iid=c.scalar(text("""INSERT INTO daily_note_inputs(org_id,classroom_id,note_date,author_id,activities,draft_status)
                VALUES (:org,:class,:day,:teacher,'[TEST] 놀이','succeeded') ON CONFLICT (classroom_id,note_date)
                DO UPDATE SET activities=EXCLUDED.activities RETURNING id"""),
                {'org':seed.ORG,'class':child['classroom_id'],'day':day,'teacher':note_teacher})
            c.execute(text("""INSERT INTO cards(org_id,kind,status,assignee_id,subject_type,subject_id,draft)
                SELECT :org,'daily_note','done',:teacher,'daily_note_batch',:input,'{}'::jsonb
                WHERE NOT EXISTS (SELECT 1 FROM cards WHERE org_id=:org AND subject_type='daily_note_batch' AND subject_id=:input)"""),
                {'org':seed.ORG,'teacher':note_teacher,'input':iid})
            c.execute(text("""INSERT INTO daily_notes(id,org_id,input_id,child_id,note_date,status,content,confirmed_by,confirmed_at,sent_at)
                VALUES (:id,:org,:input,:child,:day,:status,CAST(:body AS jsonb),:teacher,now(),now())"""),
                {'id':nid,'org':seed.ORG,'input':iid,'child':child_id,'day':day,'status':status,'body':json.dumps(content),'teacher':note_teacher})
    else:
        from app.mock.records import Note
        store.state().notes[nid]=Note(nid,seed.ORG,uuid4(),child_id,day,content,status=status)
    return str(nid)


def chunks(mode,**changes):
    req={'org_id':seed.ORG,'requester_id':seed.PARENT,'child_id':seed.CHILD,'type':'inquiry','body':'오늘 낮잠 잤나요?'}
    if mode=='db':
        from app.modules.documents.answer import daily_note_chunks
    else:
        from app.mock.documents import daily_note_chunks
    return daily_note_chunks({**req,**changes})


def test_memory_note_candidates_child_guardian_sent_and_three_days(memory_backend):
    expected={add_note(memory_backend,0),add_note(memory_backend,2)}
    add_note(memory_backend,1,status='draft')
    add_note(memory_backend,3)
    add_note(memory_backend,0,seed.CHILD_OTHER)
    found=chunks(memory_backend)
    assert {c['note_id'] for c in found}==expected
    assert all(c['source']=='daily_note' and c['chunk_id'] is None and c['title'].endswith('알림장') for c in found)
    assert chunks(memory_backend,requester_id=seed.PARENT_OTHER)==[]
    assert chunks(memory_backend,org_id=uuid4())==[]
    assert chunks(memory_backend,body='겨울방학 언제부터예요?')==[]
    assert chunks(memory_backend,child_id=None)==[]


def test_memory_note_reaches_checker_and_card_but_never_saved_answer(client,parent,teacher,memory_backend,monkeypatch):
    from agents.graphs import answer
    from app.modules.documents import answer as document_answer,search,embedding
    note_id=add_note(memory_backend,0)
    seen=[]
    class Model:
        def __init__(self,role): self.role=role
        def json(self,system,user):
            payload=json.loads(user);seen.append((self.role,payload))
            if self.role=='CHECKER': return {'passed':True,'issues':[]}
            note=next(c for c in payload['chunks'] if c.get('source')=='daily_note')
            return {'text':note['quote'],'evidence':[{'chunk_id':None,'source':'daily_note','note_id':note['note_id'],'quote':note['quote']}]}
    monkeypatch.setenv('ANSWER_WRITER','graph')
    monkeypatch.setenv('LLM_MODEL_MEMORY','')
    monkeypatch.setattr(answer,'OpenAIModel',Model)
    monkeypatch.setattr(document_answer,'search_documents',lambda *a,**kw:{'chunks':[]})
    monkeypatch.setattr(search,'search_documents',lambda *a,**kw:{'chunks':[]})
    rid,cid=create(client,parent,teacher,type='inquiry',body='오늘 낮잠 잤나요?')
    card=detail(client,teacher,cid)
    assert card['card']['draft']['note_evidence'][0]['note_id']==note_id
    assert 'no_evidence' not in card['warnings'] and not card['card']['draft']['no_evidence']
    if memory_backend=='db':
        from app.modules.requests import graph_agent
        assert any(c.get('note_id')==note_id for c in graph_agent._search_request(rid))
        state={'request_id':rid,'parallel':{'chunks':chunks('db'),'memories':[]}}
        draft=graph_agent._write_request(state)['draft']
        graph_agent._check_request({**state,'draft':draft})
        checked=[p for role,p in seen if role=='CHECKER']
        assert len(checked)==2 and all(p['evidence'][0]['note_id']==note_id for p in checked)
        assert all('child_notes' not in p and 'preferences' not in p and 'memories' not in p for p in checked)
        with transaction() as c:
            assert c.scalar(text('SELECT count(*) FROM card_evidence WHERE card_id=:id'),{'id':cid})==0
    monkeypatch.setattr(embedding,'enabled',lambda:True)
    monkeypatch.setenv('EMBEDDING_MODEL',embedding.MODEL)
    assert decision(client,teacher,cid,'edit_approve',edited_content={'text':'[TEST] 낮잠을 잘 잤어요.'}).status_code==200
    assert detail(client,teacher,cid)['card']['draft']['note_evidence'][0]['note_id']==note_id
    if memory_backend=='db':
        with transaction() as c: assert c.scalar(text('SELECT count(*) FROM saved_answers'))==0
    else:
        assert store.state().saved_answers=={}
