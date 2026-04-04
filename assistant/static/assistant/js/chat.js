function formatAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/\[([^\]]+)\]/g, '<strong style="color:var(--accent-light);">[$1]</strong>');
  html = html.replace(/\n/g, '<br>');
  html = html.replace(/(?:^|<br>)[-•]\s+(.+?)(?=<br>|$)/g, '<li>$1</li>');
  if (html.includes('<li>')) {
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
  }
  return html;
}

function addChatMessage(type, content) {
  const container = document.getElementById("chat-messages");
  if (!container) return;
  const welcome = container.querySelector(".chat-welcome");
  if (welcome) welcome.remove();

  const msg = document.createElement("div");
  msg.className = `chat-msg chat-msg-${type}`;
  msg.innerHTML = content;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
  return msg;
}

function showTypingIndicator() {
  const container = document.getElementById("chat-messages");
  if (!container) return null;
  const typing = document.createElement("div");
  typing.className = "chat-typing chat-msg chat-msg-ai";
  typing.id = "chat-typing-indicator";
  typing.innerHTML = `
    <div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div>
    <div class="chat-msg-bubble" style="display:flex;align-items:center;">
        <div class="typing-indicator" style="display:flex;gap:4px">
            <div class="typing-dot" style="width:6px;height:6px;border-radius:50%;background:var(--text-dim);animation:bounce 1.4s infinite ease-in-out both;"></div>
            <div class="typing-dot" style="width:6px;height:6px;border-radius:50%;background:var(--text-dim);animation:bounce 1.4s infinite ease-in-out both;animation-delay:-0.32s"></div>
            <div class="typing-dot" style="width:6px;height:6px;border-radius:50%;background:var(--text-dim);animation:bounce 1.4s infinite ease-in-out both;animation-delay:-0.16s"></div>
        </div>
    </div>`;
  container.appendChild(typing);
  container.scrollTop = container.scrollHeight;
  return typing;
}

function removeTypingIndicator() {
  const el = document.getElementById("chat-typing-indicator");
  if (el) el.remove();
}

async function ragSearch(queryOverride) {
  const input = document.getElementById("rag-input") || document.getElementById("chat-input");
  const btn = document.getElementById("rag-btn") || document.getElementById("btn-send");
  if (!input) return;

  const query = queryOverride || input.value.trim();
  if (!query) return;

  const emptyState = document.getElementById("empty-state");
  if (emptyState && !emptyState.classList.contains("hidden")) {
    emptyState.classList.add("hidden");
  }

  if (typeof _activeSid !== 'undefined' && !_activeSid && typeof sessionCreate !== 'undefined') {
    sessionCreate(query);
    if(typeof renderHistoryList !== 'undefined') renderHistoryList();
  }
  if(typeof sessionAddMessage !== 'undefined') sessionAddMessage('user', query);

  addChatMessage("user", `
    <div class="chat-msg-avatar">👤</div>
    <div class="chat-msg-bubble">${escapeHtml(query)}</div>`);

  input.value = "";
  if (input.style.height) input.style.height = "auto";
  if (btn) btn.disabled = true;

  const typing = showTypingIndicator();

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }, 300000); 
    const data = await res.json();
    removeTypingIndicator();

    let answerContent = "";

    if (data.error) {
      answerContent = escapeHtml(data.error);
    } else if (data.answer) {
      answerContent = formatAnswer(data.answer);
      if (data.answer_model) {
        answerContent += `<div style="margin-top:8px;font-size:.7rem;color:var(--text-dim);">Answered by ${escapeHtml(data.answer_model)}</div>`;
      }
    } else if (data.answer_error) {
      answerContent = `<span style="color:var(--color-error);">LLM unavailable: ${escapeHtml(data.answer_error)}</span><br><em style="font-size:.8rem;color:var(--text-dim);">Make sure Ollama is running.</em>`;
    } else if (!data.results || data.results.length === 0) {
      answerContent = `No matching documents found for <strong>"${escapeHtml(query)}"</strong>. Index your documents first.`;
    } else {
      answerContent = "I found relevant documents but couldn't generate an answer (LLM unavailable).";
    }

    let sourcesHtml = "";
    if (data.results && data.results.length > 0) {
      const isSemantic = data.source === "semantic";
      const sourceItems = data.results.map(r => {
        const scoreLabel = (isSemantic && r.score != null) ? `<span class="chat-source-score" style="font-size:0.75rem;padding:2px 6px;border-radius:12px;background:var(--accent-bg);color:var(--accent);margin-left:auto">${Math.round(r.score * 100)}%</span>` : "";
        return `
          <a href="${r.webViewLink || '#'}" target="_blank" rel="noopener" class="chat-source-item" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--border-dim);border-radius:8px;text-decoration:none;color:var(--text);margin-top:8px">
            <span class="chat-source-icon">${getFileEmoji(r.mimeType || '')}</span>
            <span class="chat-source-name" style="font-size:0.85rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(r.name || '')}</span>
            ${scoreLabel}
          </a>`;
      }).join("");

      sourcesHtml = `
        <div style="margin-top:12px">
            <button class="chat-sources-toggle btn btn-sm btn-outline" style="font-size:0.8rem;padding:4px 10px;" onclick="this.nextElementSibling.classList.toggle('hidden');">
            ▶ ${data.total || data.results.length} source(s)
            </button>
            <div class="chat-sources-list hidden" style="margin-top:8px">${sourceItems}</div>
        </div>`;
    }

    addChatMessage("ai", `
      <div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div>
      <div class="chat-msg-bubble">
        ${answerContent}
        ${sourcesHtml}
      </div>`);

    if(typeof sessionAddMessage !== 'undefined') {
       sessionAddMessage('ai', data.answer || answerContent.replace(/<[^>]+>/g, ''));
    }

  } catch (err) {
    removeTypingIndicator();
    const errorMsg = err.name === "AbortError" ? "Request timed out." : "Search failed: " + err.message;
    addChatMessage("ai chat-msg-error", `
      <div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div>
      <div class="chat-msg-bubble">${escapeHtml(errorMsg)}</div>`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initNewChatInput() {
  const chatInput = document.getElementById("chat-input");
  const btnSend   = document.getElementById("btn-send");
  
  if (!chatInput || !btnSend) return;

  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
    btnSend.disabled = chatInput.value.trim().length === 0;
  });

  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ragSearch();
    }
  });
  
  btnSend.addEventListener("click", () => ragSearch());

  const ragInput = document.getElementById("rag-input");
  if (ragInput) {
    ragInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") ragSearch();
    });
  }
}

function initChatUI() {
  const chatInput = document.getElementById("chat-input");
  const modernInputBox = document.querySelector(".modern-input-box");
  const chatThread = document.getElementById("chat-thread");

  if (chatInput && modernInputBox) {
    let isFocused = false;
    let isHovered = false;

    const updateExpandedState = () => {
      if (isFocused || isHovered) {
        modernInputBox.classList.add("is-expanded");
        chatInput.style.setProperty("height", "24px", "important");
        const newHeight = Math.min(chatInput.scrollHeight, 380);
        chatInput.style.setProperty("height", newHeight + "px", "important");
        modernInputBox.style.setProperty("--dynamic-height", newHeight + "px");
      } else {
        const chatModelBtn = document.getElementById("chat-model-btn");
        if (chatModelBtn && chatModelBtn.getAttribute("aria-expanded") === "true") return;
        modernInputBox.classList.remove("is-expanded");
      }
    };

    chatInput.addEventListener("input", updateExpandedState);

    modernInputBox.addEventListener("mouseenter", () => { isHovered = true; updateExpandedState(); });
    modernInputBox.addEventListener("mouseleave", () => { isHovered = false; updateExpandedState(); });
    modernInputBox.addEventListener("focusin", () => { isFocused = true; updateExpandedState(); });
    modernInputBox.addEventListener("focusout", (e) => {
      if (!modernInputBox.contains(e.relatedTarget)) {
        isFocused = false;
        updateExpandedState();
      }
    });

    document.addEventListener("mousedown", (e) => {
      if (!modernInputBox.contains(e.target)) {
        isFocused = false;
        isHovered = false;
        const chatModelMenu = document.getElementById("model-dropdown-menu");
        const chatModelBtn = document.getElementById("chat-model-btn");
        if (chatModelMenu) chatModelMenu.classList.add("hidden");
        if (chatModelBtn) chatModelBtn.setAttribute("aria-expanded", "false");
        updateExpandedState();
      }
    });

    if (chatThread) {
      const handleScrollBlur = () => {
        isFocused = false;
        isHovered = false;
        chatInput.blur();
        updateExpandedState();
      };
      chatThread.addEventListener("wheel", handleScrollBlur, { passive: true });
      chatThread.addEventListener("touchmove", handleScrollBlur, { passive: true });
    }
  }
}

window.setInput = function(val) {
  const chatInput = document.getElementById("chat-input");
  if (!chatInput) return;
  chatInput.value = val;
  chatInput.dispatchEvent(new Event("input"));
  chatInput.focus();
};

window.useSuggestion = function(btn) {
  if(btn && btn.textContent) {
      setInput(btn.textContent.trim());
      ragSearch();
  }
}

async function loadRagStatus() {
  const badge = document.getElementById("rag-status-badge");
  const ingestBtn = document.getElementById("btn-ingest");
  if (!badge) return;

  try {
    const res = await fetch(`${API_BASE}/rag/status`);
    const data = await res.json();

    if (data.ingest_running) {
      const pct = data.ingest_progress?.total
        ? Math.round((data.ingest_progress.processed / data.ingest_progress.total) * 100) : 0;
      badge.className = "badge badge-dim";
      badge.textContent = `Indexing… ${pct}%`;
      if (ingestBtn) ingestBtn.disabled = true;
      setTimeout(loadRagStatus, 2000);
      return;
    }

    if (data.indexed) {
      badge.className = "badge badge-green";
      badge.textContent = `✓ ${data.total_chunks.toLocaleString()} chunks indexed`;
      if (ingestBtn) {
        ingestBtn.disabled = false;
        const label = document.getElementById("ingest-btn-label");
        if(label) label.textContent = "⚡ Re-index";
      }
    } else {
      badge.className = "badge badge-dim";
      badge.textContent = "Not indexed";
      if (ingestBtn) ingestBtn.disabled = false;
    }
  } catch {
    if (badge) badge.textContent = "Index unavailable";
  }
}

window.ragIngest = async function() {
  const btn = document.getElementById("btn-ingest") || document.querySelector(".source-card [onclick='ragIngest()']");
  const badge = document.getElementById("rag-status-badge");

  if (btn) btn.disabled = true;
  if(btn && !btn.id) btn.innerHTML = '<span class="spinner spinner-sm"></span>';
  if (badge) { badge.className = "badge badge-dim"; badge.textContent = "Indexing…"; }

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/ingest`, { method: "POST", headers: { "X-CSRFToken": getCsrfToken() } }, 600000);
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    showToast(`Indexed ${data.files_processed || 0} files · ${data.total_chunks || 0} chunks created`, "success");
  } catch (err) {
    showToast("Indexing failed: " + err.message, "error");
  } finally {
    if(btn && !btn.id) btn.innerHTML = '⚡ Index';
    if(btn && btn.id) btn.disabled = false;
    await loadRagStatus();
  }
}
