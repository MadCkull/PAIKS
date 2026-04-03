const SESSIONS_KEY    = 'paiks-sessions';
const ACTIVE_SID_KEY  = 'paiks-active-sid';
let _activeSid = null;

function sessionsGet() {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY)) || []; }
  catch { return []; }
}
function sessionsSave(sessions) {
  try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions.slice(0, 40))); }
  catch {}
}
function sessionCreate(firstMsg) {
  const id    = 'sid-' + Date.now();
  const title = firstMsg.length > 50 ? firstMsg.slice(0, 50) + '…' : firstMsg;
  const sessions = sessionsGet();
  sessions.unshift({ id, title, createdAt: Date.now(), messages: [] });
  sessionsSave(sessions);
  _activeSid = id;
  try { localStorage.setItem(ACTIVE_SID_KEY, id); } catch {}
  return id;
}
function sessionAddMessage(role, text) {
  if (!_activeSid) return;
  const sessions = sessionsGet();
  const idx = sessions.findIndex(s => s.id === _activeSid);
  if (idx < 0) return;
  sessions[idx].messages.push({ role, text, time: Date.now() });
  sessionsSave(sessions);
}
window.sessionDelete = function(id) {
  sessionsSave(sessionsGet().filter(s => s.id !== id));
  if (_activeSid === id) {
    _activeSid = null;
    try { localStorage.removeItem(ACTIVE_SID_KEY); } catch {}
  }
  renderHistoryList();
};

function renderHistoryList() {
  const list = document.getElementById('history-list');
  if (!list) return;
  const sessions = sessionsGet();
  if (!sessions.length) {
    list.innerHTML = '<p style="font-size:.78rem;color:var(--text-dim);padding:8px 12px;">No chats yet</p>';
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="history-item${s.id === _activeSid ? ' active' : ''}" data-sid="${s.id}">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <div class="history-item-body">
        <div class="history-item-title">${escapeHtml(s.title)}</div>
        <div class="history-item-time">${timeAgo(s.createdAt)}</div>
      </div>
      <button class="history-item-del" title="Delete" onclick="event.stopPropagation();sessionDelete('${s.id}')">✕</button>
    </div>
  `).join('');
  list.querySelectorAll('.history-item[data-sid]').forEach(el => {
    el.addEventListener('click', () => loadSession(el.dataset.sid));
  });
}

function loadSession(id) {
  const session = sessionsGet().find(s => s.id === id);
  if (!session) return;
  _activeSid = id;
  try { localStorage.setItem(ACTIVE_SID_KEY, id); } catch {}

  const emptyState   = document.getElementById('empty-state');
  const chatMessages = document.getElementById('chat-messages');
  const chatThread   = document.getElementById('chat-thread');
  if (!chatMessages) return;

  chatMessages.innerHTML = '';

  if (!session.messages.length) {
    if (emptyState) emptyState.classList.remove('hidden');
    renderHistoryList();
    return;
  }

  if (emptyState) emptyState.classList.add('hidden');
  session.messages.forEach(msg => {
    const div = document.createElement('div');
    div.className = 'chat-msg chat-msg-' + (msg.role==='user'?'user':'ai');
    if (msg.role === 'user') {
      div.innerHTML = `<div class="chat-msg-avatar">👤</div><div class="chat-msg-bubble">${escapeHtml(msg.text)}</div>`;
    } else {
      div.innerHTML = `<div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div><div class="chat-msg-bubble">${formatAnswer(msg.text)}</div>`;
    }
    chatMessages.appendChild(div);
  });
  if (chatThread) chatThread.scrollTop = chatThread.scrollHeight;
  renderHistoryList();
}

window.startNewChat = function() {
  _activeSid = null;
  try { localStorage.removeItem(ACTIVE_SID_KEY); } catch {}
  const emptyState   = document.getElementById('empty-state');
  const chatMessages = document.getElementById('chat-messages');
  if (chatMessages) chatMessages.innerHTML = '';
  if (emptyState) emptyState.classList.remove('hidden');
  renderHistoryList();
  const chatInput = document.getElementById('chat-input');
  if (chatInput) { chatInput.value = ''; chatInput.focus(); }
};
