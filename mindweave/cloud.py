"""Supabase Auth + PostgREST, always using the signed-in user's JWT and RLS."""
import json
import os
import time
import re
from pathlib import Path
from urllib.parse import urlencode, urlparse
import requests

class CloudError(ValueError):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code, self.status = code, status

AUTH_ERRORS = {
    'email_address_not_authorized': 'Supabase cannot send confirmation email to this address with its default mail service. Configure custom SMTP in Supabase Authentication > Email settings, then try again.',
    'over_email_send_rate_limit': 'Supabase has reached its email sending limit. Wait for the limit to reset before retrying, or configure custom SMTP. Repeated signup attempts will not fix this.',
    'over_request_rate_limit': 'Supabase is temporarily limiting requests. Wait a few minutes before trying again.',
    'email_not_confirmed': 'Confirm your email using the Supabase verification link, then sign in. Check your spam folder too.',
    'invalid_credentials': 'The email or password was not accepted. If you have not registered yet, choose Create an account.',
    'user_already_exists': 'An account already exists for this email. Choose Sign in instead.',
    'email_exists': 'An account already exists for this email. Choose Sign in instead.',
    'signup_disabled': 'New account registration is disabled in Supabase. Enable new user signups in the project Authentication settings.',
    'email_provider_disabled': 'Email sign-in is disabled in Supabase. Enable the Email provider in Authentication settings.',
    'weak_password': 'This password does not meet your Supabase project password rules. Use a longer, stronger password that meets the configured requirements.',
    'email_address_invalid': 'Supabase rejected the email address format. Check the address and try again.',
    'captcha_failed': 'Supabase requires a valid CAPTCHA, but this form does not yet supply one. CAPTCHA integration must be added for this project configuration.',
    'unexpected_failure': 'Supabase encountered an internal authentication error. Check Authentication logs for email delivery failures or database-trigger errors.',
    'request_timeout': 'Supabase timed out. Wait briefly, then try again.',
}

def auth_error(response, path):
    """Expose stable provider codes, never raw error bodies, passwords, or tokens."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    code = payload.get('error_code') or payload.get('code')
    if not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', code):
        code = None
    action = 'create the account' if path.startswith('/auth/v1/signup') else 'complete authentication'
    message = AUTH_ERRORS.get(code)
    if not message:
        if response.status_code == 429:
            message = 'Supabase is rate-limiting this request. Wait before retrying and check Authentication rate limits.'
        elif response.status_code in (401,403):
            message = 'Supabase rejected authentication or the project key. Check your login details and project configuration.'
        else:
            message = f'Supabase could not {action}. Check the matching request in the project Authentication logs.'
    return CloudError(message, code=code, status=response.status_code)

def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                name, value = line.split('=', 1)
                if name.strip() in ('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'SUPABASE_ANON_KEY', 'OLLAMA_MODEL', 'MINDWEAVE_RESPONSE_MODE'):
                    os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))

class Supabase:
    def __init__(self):
        self.url = os.environ.get('SUPABASE_URL', '').rstrip('/')
        self.key = os.environ.get('SUPABASE_PUBLISHABLE_KEY') or os.environ.get('SUPABASE_ANON_KEY', '')
        self.configured = bool(self.url and self.key and 'YOUR-' not in self.url and 'YOUR-' not in self.key)
        if self.configured and (urlparse(self.url).scheme != 'https' or not urlparse(self.url).hostname):
            raise CloudError('SUPABASE_URL must be an HTTPS project URL.')
        if self.key.startswith('sb_secret_'):
            raise CloudError('Use a Supabase publishable key, never a secret/service-role key.')
        if self.key.startswith('eyJ'):
            import base64
            try:
                part = self.key.split('.')[1]
                if json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))).get('role') == 'service_role':
                    raise CloudError('Use the anon key, never a service-role key.')
            except (IndexError, json.JSONDecodeError):
                raise CloudError('Invalid Supabase key configuration.')

    def request(self, method, path, data=None, token=None, prefer=None):
        if not self.configured:
            raise CloudError('Supabase is not configured. Add the project URL and publishable key to .env, then restart.')
        headers = {'apikey': self.key, 'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if prefer:
            headers['Prefer'] = prefer
        try:
            response = requests.request(method, self.url + path, headers=headers, json=data, timeout=25)
        except requests.RequestException:
            message = 'Could not reach Supabase. Check your internet connection and try again.' if path.startswith('/auth/') else 'Could not reach Supabase. Your message has not been confirmed saved.'
            raise CloudError(message, code='connection_failed') from None
        if not response.ok:
            if path.startswith('/auth/'):
                raise auth_error(response, path)
            raise CloudError('Supabase storage request failed. Check that supabase/schema.sql is applied and your session is valid.')
        return response.json() if response.content else None

    def login(self, email, password):
        return self.request('POST', '/auth/v1/token?grant_type=password', {'email': email, 'password': password})

    def signup(self, email, password, name):
        return self.request('POST', '/auth/v1/signup', {'email': email, 'password': password, 'data': {'display_name': name}})

    def attach(self, state, session):
        user = self.request('GET', '/auth/v1/user', token=session['access_token'])
        state['auth'] = {'access_token': session['access_token'], 'refresh_token': session['refresh_token'],
                         'expires_at': time.time() + session.get('expires_in', 3600), 'user': user}
        rows = self.table(state, 'GET', 'mw_profiles', params={'user_id':'eq.' + user['id'], 'select':'*'})
        if rows:
            state['profile'] = rows[0]['preferences']
            state['display_name'] = rows[0]['display_name']
        else:
            name = str(user.get('user_metadata', {}).get('display_name', ''))[:80]
            self.table(state, 'POST', 'mw_profiles', {'user_id': user['id'], 'display_name': name})
            state['display_name'] = name

    def token(self, state):
        auth = state.get('auth')
        if not auth:
            raise CloudError('Sign in to access your saved conversations.')
        if time.time() >= auth['expires_at'] - 60:
            session = self.request('POST', '/auth/v1/token?grant_type=refresh_token', {'refresh_token': auth['refresh_token']})
            auth.update(access_token=session['access_token'], refresh_token=session['refresh_token'], expires_at=time.time()+session.get('expires_in',3600))
        return auth['access_token']

    def table(self, state, method, table, data=None, params=None, prefer=None):
        query = '?' + urlencode(params) if params else ''
        return self.request(method, '/rest/v1/' + table + query, data, self.token(state), prefer)

    def save_turn(self, state, turn):
        uid = state['auth']['user']['id']
        cid = state['conversation_id']
        # UUID upserts allow retries without duplicating conversations or turns.
        self.table(state, 'POST', 'mw_conversations', {'id': cid, 'user_id': uid, 'title': state['title']}, prefer='resolution=ignore-duplicates')
        self.table(state, 'POST', 'mw_turns', {'id':turn['id'], 'conversation_id':cid, 'user_id':uid,
            'user_message':turn['message'], 'assistant_response':turn['result']['response'], 'result':turn['result']}, prefer='resolution=ignore-duplicates')

    def list_conversations(self, state):
        return self.table(state, 'GET', 'mw_conversations', params={'user_id':'eq.'+state['auth']['user']['id'], 'select':'id,title,created_at', 'order':'created_at.desc', 'limit':100})

    def load_conversation(self, state, cid):
        from uuid import UUID
        cid = str(UUID(cid))
        owner = {'id':'eq.'+cid, 'user_id':'eq.'+state['auth']['user']['id'], 'select':'id,title'}
        conversations = self.table(state, 'GET', 'mw_conversations', params=owner)
        if not conversations:
            raise CloudError('Conversation not found for this account.')
        turns = self.table(state, 'GET', 'mw_turns', params={'conversation_id':'eq.'+cid,'user_id':'eq.'+state['auth']['user']['id'], 'order':'created_at.desc', 'limit':100})
        return conversations[0], list(reversed(turns))
