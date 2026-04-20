/**
 * sessions.js — DB-backed Chat Session Management
 * ─────────────────────────────────────────────────
 * All chat history is stored in the backend chats.sqlite3 via REST API.
 * localStorage is only used to remember the last active session ID across
 * page reloads (a trivial, stateless pointer — not the actual data).
 */

const ACTIVE_SID_KEY = 'paiks-active-sid';
let _activeSid = null;

// ── Internal fetch helpers ──────────────────────────────────────────────────
async function _apiGet(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`API ${url} failed: ${res.status}`);
    return res.json();
}

async function _apiPost(url, body = {}) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API POST ${url} failed: ${res.status}`);
    return res.json();
}

// ── Session Management ──────────────────────────────────────────────────────

/**
 * Create a new session in the DB.
 * Returns the newly created session ID.
 */
async function sessionCreate(firstMsg) {
    const id = 'sid-' + Date.now();
    const title = firstMsg.length > 80 ? firstMsg.slice(0, 80) + '…' : firstMsg;
    try {
        await _apiPost(`${API_BASE}/chat/sessions/new`, { id, title });
    } catch (e) {
        console.warn('Could not persist session to DB, continuing in memory:', e);
    }
    _activeSid = id;
    try { localStorage.setItem(ACTIVE_SID_KEY, id); } catch (_) {}
    return id;
}

window.sessionDelete = async function(id) {
    try {
        await fetch(`${API_BASE}/chat/sessions/${id}/delete`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
    } catch (e) {
        console.warn('Session delete failed:', e);
    }
    if (_activeSid === id) {
        _activeSid = null;
        try { localStorage.removeItem(ACTIVE_SID_KEY); } catch (_) {}
    }
    await renderHistoryList();
};

// ── UI Rendering ────────────────────────────────────────────────────────────

async function renderHistoryList() {
    const list = document.getElementById('history-list');
    if (!list) return;

    let sessions = [];
    try {
        const data = await _apiGet(`${API_BASE}/chat/sessions`);
        sessions = data.sessions || [];
    } catch (e) {
        console.warn('Could not load sessions:', e);
    }

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

// ── Load a Session into the Chat UI ────────────────────────────────────────

async function loadSession(id) {
    _activeSid = id;
    try { localStorage.setItem(ACTIVE_SID_KEY, id); } catch (_) {}

    const emptyState   = document.getElementById('empty-state');
    const chatMessages = document.getElementById('chat-messages');
    const chatThread   = document.getElementById('chat-thread');
    if (!chatMessages) return;

    chatMessages.innerHTML = `
        <div style="text-align:center;padding:40px;color:var(--text-dim);font-size:.85rem;">
            <div class="spinner" style="margin:0 auto 12px;"></div>
            Loading conversation…
        </div>`;

    let messages = [];
    try {
        const data = await _apiGet(`${API_BASE}/chat/sessions/${id}/messages`);
        messages = data.messages || [];
    } catch (e) {
        console.warn('Could not load messages:', e);
    }

    chatMessages.innerHTML = '';

    if (!messages.length) {
        if (emptyState) emptyState.classList.remove('hidden');
        await renderHistoryList();
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    for (const msg of messages) {
        const div = document.createElement('div');

        if (msg.role === 'user') {
            div.className = 'chat-msg chat-msg-user';
            div.innerHTML = `<div class="chat-msg-avatar">👤</div><div class="chat-msg-bubble">${escapeHtml(msg.text)}</div>`;
        } else {
            // AI message — restore formatted answer + sources using stored metadata
            const meta = msg.metadata || {};
            const results = meta.results || [];

            let answerContent = formatAnswer(msg.text);
            if (meta.answer_model) {
                answerContent += `<div style="margin-top:8px;font-size:.7rem;color:var(--text-dim);">Answered by ${escapeHtml(meta.answer_model)}</div>`;
            }

            let sourcesHtml = '';
            if (results.length > 0) {
                // Store results so the Sources Panel works if user clicks it
                window._lastSourceResults = results;
                sourcesHtml = `
                    <div style="margin-top:16px; display:flex; gap:8px;">
                        <button class="btn btn-sm btn-outline chat-sources-trigger"
                                style="font-size:0.75rem; padding:6px 14px; border-radius:12px; display:flex; align-items:center; gap:6px; background:rgba(108,92,231,0.05);"
                                onclick="window._lastSourceResults=${JSON.stringify(results).replace(/"/g,'&quot;')} !== undefined && window.openSourcesPanel()">
                            <i class="fas fa-stream" style="font-size:0.8rem; color:var(--accent);"></i>
                            View ${results.length} References
                        </button>
                    </div>`;
                // Cleaner: bind via data attribute
                sourcesHtml = `
                    <div style="margin-top:16px; display:flex; gap:8px;">
                        <button class="btn btn-sm btn-outline chat-sources-trigger"
                                style="font-size:0.75rem; padding:6px 14px; border-radius:12px; display:flex; align-items:center; gap:6px; background:rgba(108,92,231,0.05);"
                                onclick="window._lastSourceResults=${encodeURIComponent(JSON.stringify(results))} && window.openSourcesPanel()" data-restore-results="true">
                            <i class="fas fa-stream" style="font-size:0.8rem; color:var(--accent);"></i>
                            View ${results.length} References
                        </button>
                    </div>`;
            }

            div.className = 'chat-msg chat-msg-ai';
            div.innerHTML = `
                <div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div>
                <div class="chat-msg-bubble">
                    <div class="ai-answer-container">${answerContent}</div>
                    ${sourcesHtml}
                </div>`;

            // Bind sources button properly
            if (results.length > 0) {
                const btn = div.querySelector('.chat-sources-trigger');
                if (btn) {
                    const captured = results;
                    btn.onclick = () => {
                        window._lastSourceResults = captured;
                        window.openSourcesPanel();
                    };
                }
            }
        }

        chatMessages.appendChild(div);
    }

    if (chatThread) chatThread.scrollTop = chatThread.scrollHeight;
    await renderHistoryList();
}

// ── New Chat ────────────────────────────────────────────────────────────────

window.startNewChat = function() {
    _activeSid = null;
    try { localStorage.removeItem(ACTIVE_SID_KEY); } catch (_) {}
    const emptyState   = document.getElementById('empty-state');
    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages) chatMessages.innerHTML = '';
    if (emptyState) emptyState.classList.remove('hidden');
    renderHistoryList();
    const chatInput = document.getElementById('chat-input');
    if (chatInput) { chatInput.value = ''; chatInput.focus(); }
};

// ── Init: restore last active session on page load ──────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    // Restore last active session pointer from localStorage
    try {
        const lastSid = localStorage.getItem(ACTIVE_SID_KEY);
        if (lastSid) {
            _activeSid = lastSid;
            await loadSession(lastSid);
        } else {
            await renderHistoryList();
        }
    } catch (_) {
        await renderHistoryList();
    }
});
