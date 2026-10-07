"""Local UI: python -m mindweave.web (http://127.0.0.1:8000)."""
import argparse
import io
import json
import secrets
import threading
import copy
import uuid
import os
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import joblib
import soundfile as sf
from mindweave.core import align_voice, fuse, safety_route, safety_response, choose_strategy, update_profile
from mindweave.data import LABELS, VOICE_LABELS
from mindweave.responses import context, retrieve
from mindweave.training import probabilities
from mindweave.cloud import Supabase, CloudError, load_env
from mindweave.generator import LocalGenerator

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / 'static'

class App:
    def __init__(self):
        load_env(ROOT / '.env')
        self.cloud = Supabase()
        self.generator = LocalGenerator() if os.environ.get('MINDWEAVE_RESPONSE_MODE', 'ollama') == 'ollama' else None
        self.text = joblib.load(ROOT / 'artifacts/text/model.joblib')
        self.voice = joblib.load(ROOT / 'artifacts/voice/model.joblib')
        self.responses = joblib.load(ROOT / 'artifacts/responses.joblib')

    def audio(self, content):
        from mindweave.voice import features
        with sf.SoundFile(io.BytesIO(content)) as audio:
            if not 0.15 <= audio.frames / audio.samplerate <= 60:
                raise ValueError('Use an audio clip between 0.15 and 60 seconds.')
        p = align_voice(probabilities(self.voice, [features(io.BytesIO(content))], VOICE_LABELS))
        return p.tolist()

    def chat(self, state, message):
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            raise ValueError('Enter a message of 1–4000 characters. For audio, add what you said so the words can be checked too.')
        state['pending'] = None
        voice, state['voice'] = state['voice'], None
        route = safety_route(message)
        if route != 'NORMAL':
            return {'response': safety_response(route), 'route': route, 'probabilities': None, 'feedback_id': None}
        p = fuse(probabilities(self.text, [message], LABELS), voice)
        emotion = LABELS[int(p.argmax())]
        topic, stress = context(self.responses, message)
        strategy = choose_strategy(emotion, topic, state['profile'])
        if self.generator:
            response = self.generator.reply(message, state['history'], emotion, topic, strategy)
            source = 'local-model:' + self.generator.model
        else:
            response, source = retrieve(self.responses, message, emotion, strategy, state['history'], topic)
            matched = next((r for r in self.responses['rows'] if r['id'] == source), None)
            if matched:
                strategy = matched['intervention']
        turn = secrets.token_urlsafe(16)
        state['pending'] = (turn, emotion, topic, strategy)
        state['turns'] += 1
        return {'response': response, 'route': route, 'probabilities': dict(zip(LABELS, p.tolist())),
                'emotion': emotion, 'topic': topic, 'stress': stress, 'strategy': strategy,
                'modalities': 'Text + voice' if voice is not None else 'Text', 'feedback_id': turn, 'turns': state['turns'],
                'response_source': source}

def new_state():
    return {'profile': {}, 'pending': None, 'voice': None, 'turns': 0, 'history': [], 'auth': None,
            'conversation_id': str(uuid.uuid4()), 'title': '', 'save_history': False, 'display_name': ''}

class Server(ThreadingHTTPServer):
    def __init__(self, address, app):
        super().__init__(address, Handler)
        self.app, self.sessions, self.lock = app, {}, threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No conversation or request logs.

    def reply(self, code, payload, cookie=None, mime='application/json'):
        body = json.dumps(payload).encode() if mime == 'application/json' else payload
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        if cookie:
            self.send_header('Set-Cookie', f'mw_session={cookie}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookies = SimpleCookie(self.headers.get('Cookie', ''))
        sid = cookies['mw_session'].value if 'mw_session' in cookies else ''
        if sid not in self.server.sessions:
            sid = secrets.token_urlsafe(32)
            self.server.sessions[sid] = new_state()
        return sid, self.server.sessions[sid]

    def public_state(self, state):
        auth = state.get('auth')
        return {'configured': self.server.app.cloud.configured,
                'user': {'email': auth['user'].get('email'), 'name': state['display_name']} if auth else None,
                'save_history':state['save_history'], 'history':state['history'], 'conversation_id':state['conversation_id'],
                'generation': self.server.app.generator.status() if self.server.app.generator else {'ready':True, 'model':'retrieval baseline'}}

    def do_GET(self):
        request_path = urlparse(self.path).path
        if request_path == '/api/session':
            with self.server.lock:
                sid, state = self.session()
                result = self.public_state(state)
            return self.reply(200, result, sid)
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/login': ('login.html', 'text/html; charset=utf-8'),
                 '/login.js': ('login.js', 'text/javascript'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if request_path not in files:
            return self.reply(404, {'error': 'Not found'})
        name, mime = files[request_path]
        with self.server.lock:
            sid, _ = self.session()
        self.reply(200, (STATIC / name).read_bytes(), sid, mime)

    def do_POST(self):
        port = self.server.server_port
        allowed = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}
        if self.headers.get('Origin') not in allowed or self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
            return self.reply(403, {'error': 'Use this app from its local browser address.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 12 * 1024 * 1024:
                return self.reply(413, {'error': 'The upload is empty or exceeds 12 MB.'})
            content = self.rfile.read(length)
            with self.server.lock:
                sid, state = self.session()
                cloud = self.server.app.cloud
                if self.path not in ('/api/login', '/api/signup', '/api/logout') and cloud.configured and not state['auth']:
                    return self.reply(401, {'error': 'Sign in to continue.'})
                if self.path == '/api/audio':
                    state['voice'] = None
                    state['voice'] = self.server.app.audio(content)
                    result = {'probabilities': dict(zip(LABELS, state['voice'])), 'message': 'Voice analyzed. Add your words and send to combine both signals.'}
                else:
                    body = json.loads(content)
                    if not isinstance(body, dict):
                        raise ValueError('Invalid request')
                    if self.path in ('/api/login', '/api/signup'):
                        email, password = body.get('email'), body.get('password')
                        if not isinstance(email, str) or '@' not in email or len(email)>254 or not isinstance(password, str) or not 8 <= len(password) <= 256:
                            raise ValueError('Enter a valid email and a password of at least 8 characters.')
                        name = body.get('name', '')
                        if not isinstance(name, str) or len(name)>80:
                            raise ValueError('Use a name of at most 80 characters.')
                        session = cloud.signup(email.strip(), password, name) if self.path == '/api/signup' else cloud.login(email.strip(), password)
                        if not session.get('access_token'):
                            return self.reply(200, {'confirmation_required':True, 'message':'Check your email to confirm your account, then sign in.'})
                        fresh = new_state()
                        cloud.attach(fresh, session)
                        self.server.sessions.pop(sid, None)
                        sid = secrets.token_urlsafe(32)  # Rotate session ID on authentication.
                        self.server.sessions[sid] = state = fresh
                        result = self.public_state(state)
                    elif self.path == '/api/logout':
                        if state['auth']:
                            try:
                                cloud.request('POST', '/auth/v1/logout?scope=local', token=cloud.token(state))
                            except CloudError:
                                pass  # Always clear local credentials even if the provider is unavailable.
                        self.server.sessions.pop(sid, None)
                        sid = secrets.token_urlsafe(32)
                        self.server.sessions[sid] = new_state()
                        result = {'message':'Signed out'}
                    elif self.path == '/api/chat':
                        trial = copy.deepcopy(state)
                        result = self.server.app.chat(trial, body.get('message'))
                        turn = {'id':str(uuid.uuid4()), 'message':body['message'], 'result':result}
                        trial['title'] = trial['title'] or body['message'][:80]
                        result['saved'] = False
                        if trial['save_history']:
                            try:
                                cloud.save_turn(trial, turn)
                                result['saved'] = True
                            except CloudError:
                                result['storage_warning'] = 'Reply shown, but saving failed. It remains in this session only. Use Retry save.'
                        trial['history'].append(turn)
                        trial['history'] = trial['history'][-100:]
                        state.clear(); state.update(trial)
                        result['turn_id'] = turn['id']
                    elif self.path == '/api/history-setting':
                        enabled = body.get('enabled')
                        if not isinstance(enabled, bool):
                            raise ValueError('Choose whether to save future messages.')
                        if enabled and not state['auth']:
                            raise ValueError('Sign in before enabling saved history.')
                        state['save_history'] = enabled
                        # New boundary prevents unsaved older content being uploaded implicitly.
                        state['conversation_id'] = str(uuid.uuid4()); state['title'] = ''
                        state['history'] = []; state['pending'] = None; state['voice'] = None
                        result = {'message':'Future turns will be saved to your Supabase account.' if enabled else 'Future turns stay in server memory only.'}
                    elif self.path == '/api/retry-save':
                        if not state['save_history']:
                            raise ValueError('Enable saved history first.')
                        turn = next((t for t in state['history'] if t['id'] == body.get('id')), None)
                        if not turn:
                            raise ValueError('Turn not found in this session.')
                        cloud.save_turn(state, turn); turn['result']['saved'] = True
                        turn['result'].pop('storage_warning', None)
                        result = {'message':'Saved to Supabase.'}
                    elif self.path == '/api/conversations':
                        result = {'conversations':cloud.list_conversations(state)}
                    elif self.path == '/api/open-conversation':
                        conversation, rows = cloud.load_conversation(state, body.get('id', ''))
                        state.update(conversation_id=conversation['id'], title=conversation['title'], save_history=True, pending=None, voice=None,
                                     history=[{'id':r['id'],'message':r['user_message'],'result':dict(r['result'],saved=True,feedback_id=None)} for r in rows])
                        result = self.public_state(state)
                    elif self.path == '/api/delete-conversation':
                        cid = str(uuid.UUID(body.get('id', '')))
                        cloud.table(state, 'DELETE', 'mw_conversations', params={'id':'eq.'+cid,'user_id':'eq.'+state['auth']['user']['id']})
                        if cid == state['conversation_id']:
                            state.update(conversation_id=str(uuid.uuid4()), title='', history=[], pending=None, voice=None)
                        result = {'message':'Conversation deleted.'}
                    elif self.path == '/api/feedback':
                        pending = state['pending']
                        if not pending or body.get('id') != pending[0]:
                            raise ValueError('Feedback is only available for the latest ordinary response.')
                        if body.get('feedback') not in ('helped', 'a_little', 'not_helped'):
                            raise ValueError('Choose a feedback option.')
                        profile = copy.deepcopy(state['profile'])
                        update_profile(profile, *pending[1:], body['feedback'])
                        if state['auth'] and state['save_history']:
                            cloud.table(state, 'PATCH', 'mw_profiles', {'preferences':profile}, params={'user_id':'eq.'+state['auth']['user']['id']})
                        state['profile'] = profile
                        state['pending'] = None
                        result = {'message': 'Thank you. Your next suggestions will use this feedback.'}
                    elif self.path == '/api/reset':
                        state.update(conversation_id=str(uuid.uuid4()), title='', history=[], pending=None, voice=None, turns=0)
                        result = {'message': 'New conversation started. Saved conversations are still in History.'}
                    elif self.path == '/api/clear-audio':
                        state['voice'] = None
                        result = {'message': 'Audio removed'}
                    else:
                        return self.reply(404, {'error': 'Not found'})
                self.reply(200, result, sid)
        except CloudError as error:
            self.reply(400, {'error':str(error), 'code':error.code, 'provider_status':error.status})
        except (ValueError, RuntimeError, OSError) as error:
            self.reply(400, {'error': str(error)})
        except Exception:
            self.reply(500, {'error': 'Unable to process this input. Try a shorter message or another audio clip.'})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = Server(('127.0.0.1', args.port), App())
    print(f'MINDWEAVE is ready at http://127.0.0.1:{args.port}', flush=True)
    print('Keep this terminal open. Press Ctrl+C to stop. Sign in; Supabase history is opt-in.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
