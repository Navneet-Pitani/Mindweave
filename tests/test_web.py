import io
import json
import threading
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
import numpy as np
import pytest
import soundfile as sf
from mindweave.web import App, Server, new_state

@pytest.fixture(scope='module')
def app():
    app = App()
    app.cloud.configured = False  # Unit tests never touch real accounts or require a running LLM.
    app.generator = None
    return app

def test_web_chat_feedback_and_safety(app):
    state = new_state()
    result = app.chat(state, 'I had a good day with my friends')
    assert result['route'] == 'NORMAL'
    assert sum(result['probabilities'].values()) == pytest.approx(1)
    assert state['pending'][0] == result['feedback_id']
    state['voice'] = [1,0,0,0,0]
    result = app.chat(state, 'I am thinking about killing myself')
    assert result['route'] == 'SAFETY_ESCALATION'
    assert state['pending'] is None and state['voice'] is None

def test_web_rejects_silent_audio(app):
    audio = io.BytesIO()
    sf.write(audio, np.zeros(16000), 16000, format='WAV')
    with pytest.raises(ValueError, match='silent'):
        app.audio(audio.getvalue())

def test_http_session_feedback_and_origin(app):
    server = Server(('127.0.0.1', 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    browser = build_opener(HTTPCookieProcessor())
    def post(path, data):
        request = Request(base + '/api/' + path, json.dumps(data).encode(), headers={'Origin':base,'Content-Type':'application/json'})
        return json.load(browser.open(request))
    try:
        assert b'MINDWEAVE' in browser.open(base).read()
        result = post('chat', {'message':'Today was a good day'})
        assert post('feedback', {'id':result['feedback_id'], 'feedback':'helped'})['message']
        with pytest.raises(HTTPError) as stale:
            post('feedback', {'id':result['feedback_id'], 'feedback':'helped'})
        assert stale.value.code == 400
        with pytest.raises(HTTPError) as foreign:
            browser.open(Request(base+'/api/reset', b'{}', headers={'Origin':'https://example.com'}))
        assert foreign.value.code == 403
        assert 'New conversation' in post('reset', {})['message']
    finally:
        server.shutdown(); server.server_close(); thread.join()
