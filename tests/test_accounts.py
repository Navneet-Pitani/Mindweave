"""HTTP boundary tests with a simulated provider; live Supabase RLS needs two real accounts."""
import json
import threading
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
import pytest
from mindweave.web import App, Server
from mindweave.cloud import CloudError, Supabase

class FakeCloud:
    configured = True
    def __init__(self):self.rows={};self.fail=False
    def login(self,email,password):return {'email':email,'access_token':'fake'}
    def attach(self,state,session):
        state['auth']={'user':{'id':session['email'],'email':session['email']}}
        state['display_name']=session['email']
    def token(self,state):return 'fake'
    def request(self,*args,**kwargs):return None
    def save_turn(self,state,turn):
        if self.fail:raise CloudError('Simulated outage')
        key=(state['auth']['user']['id'],state['conversation_id'])
        self.rows.setdefault(key,{'title':state['title'],'turns':{}})['turns'][turn['id']]=turn
    def list_conversations(self,state):
        return [{'id':cid,'title':row['title']} for (uid,cid),row in self.rows.items() if uid==state['auth']['user']['id']]
    def load_conversation(self,state,cid):
        row=self.rows.get((state['auth']['user']['id'],cid))
        if not row:raise CloudError('Not found')
        return {'id':cid,'title':row['title']},[{'id':t['id'],'user_message':t['message'],'result':t['result']} for t in row['turns'].values()]

def test_login_rotation_session_isolation_and_unsaved_reply(monkeypatch):
    app=App();app.cloud=FakeCloud();app.generator=None
    server=Server(('127.0.0.1',0),app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    a,b=build_opener(HTTPCookieProcessor()),build_opener(HTTPCookieProcessor())
    def post(browser,path,body):
        return json.load(browser.open(Request(base+'/api/'+path,json.dumps(body).encode(),headers={'Origin':base,'Content-Type':'application/json'})))
    try:
        with pytest.raises(HTTPError) as unauth:post(a,'chat',{'message':'hello'})
        assert unauth.value.code==401
        post(a,'login',{'email':'a@example.test','password':'example-test-only'})
        post(b,'login',{'email':'b@example.test','password':'example-test-only'})
        post(a,'chat',{'message':'My exam is tomorrow and I feel nervous'})
        assert json.load(a.open(base+'/api/session'))['history']
        assert json.load(b.open(base+'/api/session'))['history']==[]
        post(a,'history-setting',{'enabled':True})
        saved=post(a,'chat',{'message':'I feel lonely at college'})
        assert saved['saved'] is True
        conversations=post(a,'conversations',{})['conversations']
        assert len(conversations)==1
        assert post(b,'conversations',{})['conversations']==[]
        with pytest.raises(HTTPError):post(b,'open-conversation',{'id':conversations[0]['id']})
        post(a,'reset',{})
        restored=post(a,'open-conversation',{'id':conversations[0]['id']})
        assert restored['history'][0]['message']=='I feel lonely at college'
        app.cloud.fail=True
        result=post(a,'chat',{'message':'My assignment is due tomorrow'})
        assert result['response'] and result['saved'] is False and result['storage_warning']
        assert json.load(a.open(base+'/api/session'))['history'][-1]['message']=='My assignment is due tomorrow'
        post(a,'logout',{})
        assert json.load(a.open(base+'/api/session'))['user'] is None
        assert json.load(b.open(base+'/api/session'))['user']['email']=='b@example.test'
        with pytest.raises(HTTPError):post(a,'chat',{'message':'hello'})
    finally:server.shutdown();server.server_close();thread.join()

def test_database_requests_use_user_token_and_owner_filter(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_test')
    cloud=Supabase();calls=[]
    monkeypatch.setattr(cloud,'token',lambda state:'alice-jwt')
    monkeypatch.setattr(cloud,'request',lambda *args,**kwargs:calls.append(args) or [])
    cloud.list_conversations({'auth':{'user':{'id':'alice'}}})
    assert calls[0][3]=='alice-jwt'
    assert 'user_id=eq.alice' in calls[0][1]

def test_remote_generator_not_configurable(monkeypatch):
    from mindweave.generator import LocalGenerator
    monkeypatch.setenv('OLLAMA_HOST','https://example.com')
    assert LocalGenerator().url=='http://127.0.0.1:11434'
