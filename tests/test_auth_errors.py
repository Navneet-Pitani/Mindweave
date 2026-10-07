import pytest
from mindweave.cloud import auth_error, CloudError, Supabase

class Response:
    ok=False
    status_code=422
    def __init__(self,payload,status=422):self.payload=payload;self.status_code=status
    def json(self):return self.payload

@pytest.mark.parametrize('code,expected',[
    ('email_address_not_authorized','custom SMTP'),
    ('over_email_send_rate_limit','sending limit'),
    ('email_not_confirmed','Confirm your email'),
    ('signup_disabled','registration is disabled'),
    ('weak_password','password rules'),
    ('captcha_failed','CAPTCHA'),
])
def test_specific_provider_error(code,expected):
    error=auth_error(Response({'error_code':code}),'/auth/v1/signup')
    assert error.code==code and expected in str(error)

def test_unknown_error_does_not_expose_provider_payload():
    error=auth_error(Response({'code':'unknown_error','msg':'private-email secret-password access_token'}),'/auth/v1/signup')
    assert 'private-email' not in str(error) and 'secret-password' not in str(error)
    assert 'create the account' in str(error) and error.code=='unknown_error'

def test_non_json_or_invalid_code_is_safe():
    assert auth_error(Response({'code':'token=PRIVATE'}),'/auth/v1/signup').code is None
    assert auth_error(Response(['secret']),'/auth/v1/signup').code is None

def test_request_preserves_auth_error(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_test')
    monkeypatch.setattr('mindweave.cloud.requests.request',lambda *args,**kwargs:Response({'error_code':'over_email_send_rate_limit'},429))
    with pytest.raises(CloudError) as caught:Supabase().signup('example@example.test','not-a-real-password','Example')
    assert caught.value.code=='over_email_send_rate_limit' and caught.value.status==429
