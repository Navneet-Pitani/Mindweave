const $ = id => document.getElementById(id);
let busy = false, recording = false, stream, audioContext, source, processor, chunks = [], frames = 0, timer, previewURL;
let authenticated = false;
const notice = (text, error = false) => { $('notice').textContent = text; $('notice').classList.toggle('error', error); };
function setBusy(value) {
  busy = value;
  for (const id of ['send', 'upload', 'record', 'reset', 'remove-audio']) $(id).disabled = value;
  for (const id of ['save-history','history-toggle','logout']) $(id).disabled = value || !authenticated;
  document.querySelectorAll('.feedback button').forEach(b => b.disabled = value);
}
async function api(path, data, raw = false) {
  const response = await fetch('/api/' + path, {method: 'POST', headers: {'Content-Type': raw ? 'audio/wav' : 'application/json'}, body: raw ? data : JSON.stringify(data)});
  const result = await response.json();
  if (response.status === 401) { location.assign('/login'); throw new Error('Please sign in again.'); }
  if (!response.ok) throw new Error(result.error || 'Something went wrong. Please try again.');
  return result;
}
function bubble(text, who, safety = false) {
  const element = document.createElement('div');
  element.className = 'bubble ' + who + (safety ? ' safety' : '');
  const name = document.createElement('span'); name.className = 'speaker'; name.textContent = who === 'user' ? 'YOU' : 'MINDWEAVE';
  element.append(name, document.createTextNode(text)); $('messages').append(element);
  $('messages').scrollTop = $('messages').scrollHeight;
}
function showProbabilities(values) {
  $('bars').replaceChildren(); $('bars').hidden = !values;
  if (!values) return;
  for (const [label, probability] of Object.entries(values)) {
    const row = document.createElement('div'); row.className = 'bar-row';
    const heading = document.createElement('div'); heading.className = 'bar-label';
    const title = document.createElement('span'); title.textContent = label;
    const score = document.createElement('span'); score.textContent = Math.round(probability * 100) + '%';
    heading.append(title, score);
    const track = document.createElement('div'); track.className = 'track';
    const fill = document.createElement('div'); fill.className = 'fill'; fill.style.width = probability * 100 + '%';
    track.append(fill); row.append(heading, track); $('bars').append(row);
  }
}
function clearPreview() {
  $('audio-box').hidden = true; $('playback').pause(); $('playback').removeAttribute('src');
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = null;
}
function addFeedback(id) {
  const buttons = document.createElement('div'); buttons.className = 'feedback';
  for (const [label, feedback] of [['That helped', 'helped'], ['A little', 'a_little'], ['Not really', 'not_helped']]) {
    const button = document.createElement('button'); button.textContent = label;
    button.onclick = async () => {
      if (busy) return; setBusy(true);
      try { const result = await api('feedback', {id, feedback}); buttons.remove(); notice(result.message); }
      catch (error) { notice(error.message, true); }
      finally { setBusy(false); }
    };
    buttons.append(button);
  }
  $('messages').append(buttons); $('messages').scrollTop = $('messages').scrollHeight;
}
function saveStatus(turn) {
  const status = document.createElement('div'); status.className = 'save-status';
  const source = turn.result.response_source?.startsWith('local-model:') ? 'Reply generated on this computer' : 'Local response library';
  status.textContent = source + ' · ' + (turn.result.saved ? 'Saved to your Supabase account' : 'Session only');
  if(turn.result.storage_warning) {
    status.textContent = turn.result.storage_warning + ' ';
    const retry = document.createElement('button'); retry.textContent = 'Retry save';
    retry.onclick = async () => { retry.disabled = true; try { await api('retry-save',{id:turn.id}); status.textContent = 'Saved to your Supabase account'; } catch(e) { notice(e.message,true); retry.disabled=false; } };
    status.append(retry);
  }
  $('messages').append(status);
}
function renderHistory(history) {
  if(history.length) $('messages').replaceChildren();
  for(const turn of history) { bubble(turn.message,'user'); bubble(turn.result.response,'assistant',turn.result.route!=='NORMAL'); saveStatus(turn); }
  $('messages').scrollTop = $('messages').scrollHeight;
}
function storageLabel(enabled) {
  $('save-history').checked = enabled;
  $('session-storage').textContent = enabled ? 'SAVED TO SUPABASE' : 'SESSION ONLY';
  $('storage-copy').textContent = enabled ? 'Future messages and replies are saved to your Supabase account. Audio is never saved.' : 'Unsaved messages stay in this server session. Raw audio is never stored in Supabase.';
}
$('save-history').onchange = async () => {
  if(busy || recording) return;
  const enabled = $('save-history').checked;
  if(document.querySelector('.bubble') && !confirm('Changing history saving starts a new conversation. Unsaved messages will be cleared; existing saved chats remain in History.')) { $('save-history').checked = !enabled; return; }
  setBusy(true);
  try { const data = await api('history-setting',{enabled}); $('messages').replaceChildren(); clearPreview(); showProbabilities(null); storageLabel(enabled); notice(data.message); }
  catch(e) { $('save-history').checked = !enabled; notice(e.message,true); }
  finally { setBusy(false); }
};
async function listHistory() {
  const data = await api('conversations',{}); $('history-list').replaceChildren(); $('history-list').hidden=false;
  if(!data.conversations.length) $('history-list').textContent = 'No saved conversations yet.';
  for(const conversation of data.conversations) {
    const row=document.createElement('div'); row.className='history-item';
    const open=document.createElement('button'); open.textContent=conversation.title; open.title=conversation.created_at;
    open.onclick=async()=>{ if(busy || recording)return; setBusy(true); try {const data=await api('open-conversation',{id:conversation.id}); $('messages').replaceChildren(); renderHistory(data.history); clearPreview(); showProbabilities(null); storageLabel(true); notice('Saved conversation opened. New replies will be saved to this conversation.');}catch(e){notice(e.message,true);}finally{setBusy(false);} };
    const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label','Delete '+conversation.title);
    remove.onclick=async()=>{if(busy || recording)return;if(!confirm('Permanently delete this saved conversation and its messages?'))return;setBusy(true);try{await api('delete-conversation',{id:conversation.id});location.reload();}catch(e){notice(e.message,true);setBusy(false);} };
    row.append(open,remove);$('history-list').append(row);
  }
}
$('history-toggle').onclick=async()=>{if(busy || recording)return;setBusy(true);try{await listHistory();}catch(e){notice(e.message,true);}finally{setBusy(false);} };
$('logout').onclick=async()=>{if(busy || recording)return;setBusy(true);try{await api('logout',{});location.assign('/login');}catch(e){notice(e.message,true);setBusy(false);} };
(async()=>{
  setBusy(true);
  try {
    const response=await fetch('/api/session');const state=await response.json();
    if(state.configured && !state.user) return location.replace('/login');
    if(!state.configured && !new URLSearchParams(location.search).has('demo')) return location.replace('/login');
    authenticated = !!state.user;
    $('account-name').textContent=state.user?.name || state.user?.email || 'Local demo';
    $('logout').hidden=!state.user;$('save-history').disabled=!state.user;$('history-toggle').disabled=!state.user;
    storageLabel(state.save_history);renderHistory(state.history);
    document.querySelector('.status').textContent=state.generation.ready ? '● '+state.generation.model+' · local' : 'Local reply model offline';
    notice(state.generation.ready ? 'Replies use your recent conversation. Voice analyzes tone; add the words you said.' : 'Start Ollama to generate replies. Your chat will not be sent to a hosted AI.');
  }catch(e){notice('Unable to load your session. Check the server and reload.',true);}
  finally{setBusy(false);}
})();
$('composer').onsubmit = async event => {
  event.preventDefault(); if (busy || recording) return;
  const message = $('message').value.trim();
  if (!message) { notice('Add a message, or type what you said in the recording.', true); $('message').focus(); return; }
  setBusy(true); notice('Taking a moment with your message…');
  try {
    const result = await api('chat', {message});
    document.querySelector('.welcome')?.remove(); document.querySelectorAll('.feedback').forEach(e => e.remove());
    bubble(message, 'user'); bubble(result.response, 'assistant', result.route !== 'NORMAL'); $('message').value = ''; clearPreview();
    saveStatus({id:result.turn_id,result});
    showProbabilities(result.probabilities);
    $('emotion').textContent = result.emotion ? 'A hint of ' + result.emotion.toLowerCase() : 'Your safety comes first';
    $('insight-copy').textContent = result.emotion ? 'An estimate from this check-in. It may not capture everything you’re feeling.' : 'Let’s pause ordinary suggestions and check what support you need right now.';
    $('modality').textContent = result.modalities || 'Safety check';
    $('strategy').textContent = result.strategy ? result.strategy.toLowerCase().replaceAll('_', ' ') : 'Support and connection';
    if (result.feedback_id) addFeedback(result.feedback_id);
    notice(result.storage_warning || 'You can share more, or tell me whether that response helped.', !!result.storage_warning);
  } catch (error) { notice(error.message, true); }
  finally { setBusy(false); $('message').focus(); }
};
$('message').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('composer').requestSubmit(); } };
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { $('message').value = button.dataset.prompt; $('message').focus(); });
function wav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (offset, value) => { for (let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i)); };
  text(0,'RIFF'); view.setUint32(4,36+samples.length*2,true); text(8,'WAVE'); text(12,'fmt ');
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true); view.setUint32(24,sampleRate,true);
  view.setUint32(28,sampleRate*2,true); view.setUint16(32,2,true); view.setUint16(34,16,true); text(36,'data'); view.setUint32(40,samples.length*2,true);
  for (let i=0;i<samples.length;i++) { const s = Math.max(-1, Math.min(1,samples[i])); view.setInt16(44+i*2,s<0?s*32768:s*32767,true); }
  return new Blob([buffer], {type:'audio/wav'});
}
async function submitAudio(blob) {
  setBusy(true); notice('Listening to the tone of your voice… The first analysis can take a moment.');
  try {
    const result = await api('audio', blob, true);
    clearPreview(); previewURL = URL.createObjectURL(blob); $('playback').src = previewURL; $('audio-box').hidden = false;
    showProbabilities(result.probabilities);
    $('emotion').textContent = 'Your voice, a little closer'; $('modality').textContent = 'Voice ready to combine with text';
    $('insight-copy').textContent = 'These estimates describe tone, not the words in your recording. Add your words before sending.';
    notice(result.message); $('message').focus();
  } catch(error) { clearPreview(); showProbabilities(null); notice(error.message, true); }
  finally { setBusy(false); }
}
$('upload').onclick = () => $('file').click();
$('file').onchange = async () => {
  const file = $('file').files[0]; $('file').value = ''; if (!file || busy) return;
  if (file.size > 12 * 1024 * 1024) { notice('Please choose an audio file smaller than 12 MB.', true); return; }
  setBusy(true); let decoder;
  try {
    decoder = new AudioContext(); const decoded = await decoder.decodeAudioData(await file.arrayBuffer());
    if (decoded.duration > 60 || decoded.duration < .15) throw new Error('Choose an audio clip between 0.15 and 60 seconds.');
    const mono = new Float32Array(decoded.length);
    for (let channel=0;channel<decoded.numberOfChannels;channel++) { const data = decoded.getChannelData(channel); for(let i=0;i<mono.length;i++) mono[i] += data[i] / decoded.numberOfChannels; }
    await submitAudio(wav(mono, decoded.sampleRate));
  } catch(error) { notice('Could not read this audio. Try WAV, MP3, or M4A supported by your browser. ' + error.message, true); }
  finally { if (decoder) await decoder.close(); setBusy(false); }
};
async function stopRecording() {
  if (!recording) return; recording = false; clearInterval(timer);
  processor.disconnect(); source.disconnect(); stream.getTracks().forEach(track => track.stop());
  const sampleRate = audioContext.sampleRate; await audioContext.close();
  $('record').classList.remove('recording'); $('record').textContent = '●  Record';
  const samples = new Float32Array(frames); let offset = 0;
  for (const chunk of chunks) { samples.set(chunk, offset); offset += chunk.length; }
  chunks = []; await submitAudio(wav(samples, sampleRate));
}
$('record').onclick = async () => {
  if (recording) return stopRecording(); if (busy) return;
  setBusy(true);
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone recording requires localhost and a supported browser. You can upload a clip instead.');
    stream = await navigator.mediaDevices.getUserMedia({audio:true}); audioContext = new AudioContext(); await audioContext.resume();
    source = audioContext.createMediaStreamSource(stream); processor = audioContext.createScriptProcessor(4096,1,1);
    chunks = []; frames = 0; recording = true;
    $('record').disabled = false;
    processor.onaudioprocess = event => { if (!recording) return; const chunk = new Float32Array(event.inputBuffer.getChannelData(0)); chunks.push(chunk); frames += chunk.length; };
    source.connect(processor); processor.connect(audioContext.destination);
    $('record').textContent = '■  Stop recording'; $('record').classList.add('recording');
    for (const id of ['send','upload','reset','remove-audio']) $(id).disabled = true;
    const started = Date.now(); notice('Recording… Tap Stop recording when you’re done.');
    timer = setInterval(() => { const seconds = Math.floor((Date.now()-started)/1000); notice(`Recording ${seconds}s / 60s · Tap Stop recording when you’re done.`); if(seconds>=59) stopRecording(); }, 500);
  } catch(error) { stream?.getTracks().forEach(t => t.stop()); if(audioContext && audioContext.state !== 'closed') await audioContext.close(); recording = false; setBusy(false); notice('Microphone unavailable. Allow microphone access or upload audio. ' + error.message, true); }
};
$('remove-audio').onclick = async () => { setBusy(true); try { await api('clear-audio', {}); clearPreview(); showProbabilities(null); $('modality').textContent = 'Text only'; notice('Audio removed.'); } catch(e) { notice(e.message,true); } finally { setBusy(false); } };
$('reset').onclick = async () => { if (!confirm('Start a new conversation? Unsaved messages will be cleared. Saved conversations remain in History.')) return; setBusy(true); try { await api('reset',{}); location.reload(); } catch(e) { notice(e.message,true); setBusy(false); } };
window.addEventListener('beforeunload', () => stream?.getTracks().forEach(t => t.stop()));
