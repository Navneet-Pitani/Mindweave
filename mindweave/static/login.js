const el = id => document.getElementById(id);
let creating = false;
el('auth-toggle').onclick = () => {
  creating = !creating; el('name-label').hidden = !creating; el('name').required = creating;
  el('auth-title').textContent = creating ? 'A space of your own.' : 'Your space, your pace.';
  el('auth-description').textContent = creating ? 'Create an account with your email. You may need to confirm it before signing in.' : 'Sign in to continue your check-in.';
  el('auth-submit').textContent = creating ? 'Create account ↗' : 'Sign in ↗';
  el('auth-toggle').textContent = creating ? 'Already registered? Sign in' : 'New here? Create an account';
  el('password').autocomplete = creating ? 'new-password' : 'current-password';
};
el('auth-form').onsubmit = async event => {
  event.preventDefault(); el('auth-submit').disabled = true; el('auth-toggle').disabled = true;
  el('auth-status').textContent = creating ? 'Creating your account…' : 'Signing in…';
  try {
    const response = await fetch('/api/' + (creating ? 'signup' : 'login'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:el('email').value,password:el('password').value,name:el('name').value})});
    const data = await response.json();
    if(!response.ok) {
      const detail = data.code ? ' [' + data.code + ']' : (data.provider_status ? ' [Supabase HTTP ' + data.provider_status + ']' : '');
      throw new Error(data.error + detail);
    }
    el('password').value = '';
    if(data.confirmation_required) el('auth-status').textContent = data.message;
    else location.assign('/');
  } catch(error) { el('auth-status').textContent = error.message || 'Unable to sign in. Please try again.'; }
  finally { el('auth-submit').disabled = false; el('auth-toggle').disabled = false; }
};
(async () => {
  try {
    const response = await fetch('/api/session'); const data = await response.json();
    if(data.user) return location.replace('/');
    el('auth-status').textContent = data.configured ? 'Your password is handled by Supabase Auth.' : 'Account setup is pending. Configure Supabase to enable login.';
    el('auth-submit').disabled = !data.configured;
    el('demo-link').hidden = data.configured;
  } catch { el('auth-status').textContent = 'The local server is unavailable. Start it and reload.'; }
})();
