import joblib
from mindweave.responses import retrieve
from mindweave.web import ROOT

def test_wrong_emotion_does_not_block_specific_match():
    bundle=joblib.load(ROOT/'artifacts/responses.joblib')
    response,source=retrieve(bundle, "my exam is tomorrow and my brain won't stop panicking.", 'Neutral','EXPLORATION')
    assert 'exam' in response
    assert source.startswith('TRN_')

def test_recent_response_not_repeated():
    bundle=joblib.load(ROOT/'artifacts/responses.joblib')
    message='my exam is tomorrow and my brain won\'t stop panicking.'
    first,_=retrieve(bundle,message,'Anxiety','GROUNDING')
    history=[{'message':message,'result':{'response':first,'topic':'exam'}}]
    second,_=retrieve(bundle,message,'Anxiety','GROUNDING',history,'exam')
    assert first != second

def test_local_generator_receives_history_without_network(monkeypatch):
    from mindweave.generator import LocalGenerator
    payloads=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'message':{'content':'Let us focus on the closest deadline.'}}
    def post(url,**kwargs):
        assert url=='http://127.0.0.1:11434/api/chat'
        payloads.append(kwargs['json']);return Response()
    monkeypatch.setattr('mindweave.generator.requests.post',post)
    history=[{'message':'I have three deadlines','result':{'response':'Which comes first?'}}]
    result=LocalGenerator().reply('The essay tomorrow',history,'Anxiety','assignment','PROBLEM_SOLVING')
    assert 'deadline' in result
    assert [m['role'] for m in payloads[0]['messages']]==['system','user','assistant','user']
    assert payloads[0]['messages'][1]['content']=='I have three deadlines'

def test_risk_bypasses_local_generator():
    from mindweave.web import App,new_state
    app=App()
    class Never:
        def reply(self,*args):raise AssertionError('Safety must bypass generation')
    app.generator=Never()
    assert app.chat(new_state(),'I want to kill myself')['route']=='SAFETY_ESCALATION'
