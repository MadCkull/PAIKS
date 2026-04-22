function formatAnswer(text) {
  let html = escapeHtml(text).replace(/\n/g, '<br>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  
  // Strip any stray [Source: ...] tags the LLM may still emit (legacy cleanup)
  html = html.replace(/\[Source:\s*[^\]]+?\]/g, '');

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

  // Create a new DB session on first message
  if (typeof _activeSid !== 'undefined' && !_activeSid && typeof sessionCreate !== 'undefined') {
    await sessionCreate(query);
    if(typeof renderHistoryList !== 'undefined') renderHistoryList();
  }

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
      // Backend now owns history — we just send query + session_id
      body: JSON.stringify({ query, session_id: _activeSid || null }),
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
      window._lastSourceResults = data.results;
      sourcesHtml = `
        <div style="margin-top:16px; display:flex; gap:8px;">
            <button class="btn btn-sm btn-outline chat-sources-trigger"
                    style="font-size:0.75rem; padding:6px 14px; border-radius:12px; display:flex; align-items:center; gap:6px; background:rgba(108,92,231,0.05);"
                    onclick="window.openSourcesPanel()">
                <i class="fas fa-stream" style="font-size:0.8rem; color:var(--accent);"></i>
                View ${data.total || data.results.length} References
            </button>
        </div>`;
    }

    addChatMessage("ai", `
      <div class="chat-msg-avatar" style="background:var(--accent-bg);color:var(--accent)">🧠</div>
      <div class="chat-msg-bubble">
        <div class="ai-answer-container">${answerContent}</div>
        ${sourcesHtml}
      </div>`);

    // Backend saved everything — no sessionAddMessage needed

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
  const chatModelBtn = document.getElementById("chat-model-btn");
  const modelDropdownMenu = document.getElementById("model-dropdown-menu");

  if (chatModelBtn && modelDropdownMenu) {
    chatModelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = chatModelBtn.getAttribute("aria-expanded") === "true";
      chatModelBtn.setAttribute("aria-expanded", !isExpanded);
      modelDropdownMenu.classList.toggle("hidden", isExpanded);
    });
  }

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
// --- Side Panel Controls ---
window.openSourcesPanel = function(highlightName = null) {
    const overlay = document.getElementById("sources-panel-overlay");
    const body = document.getElementById("sources-body");
    if (!overlay || !body) return;

    const results = window._lastSourceResults || [];
    if (results.length === 0) {
        body.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-dim);">No references available for this answer.</div>`;
    } else {
        body.innerHTML = results.map(r => {
            const score = r.score ? Math.round(r.score * 100) : 0;
            const scoreClass = score > 80 ? 'score-high' : (score > 50 ? 'score-mid' : 'score-low');
            const isHighlighted = highlightName && (r.name.includes(highlightName) || highlightName.includes(r.name));
            
            return `
                <a href="${r.webViewLink || '#'}" target="_blank" class="source-card-vibrant ${isHighlighted ? 'highlighted' : ''}" id="source-${btoa(r.name).replace(/=/g,'')}">
                    <div class="card-top">
                        <div class="file-info">
                            <div class="file-icon">${getFileEmoji(r.mimeType)}</div>
                            <div>
                                <div class="file-name">${escapeHtml(r.name.split(/[\\/]/).pop())}</div>
                                <div class="source-type">${escapeHtml(r.source || 'cloud')} match</div>
                            </div>
                        </div>
                        <div class="score-badge ${scoreClass}">${score}%</div>
                    </div>
                    <div class="snippet">
                        "${escapeHtml(r.snippet || 'No excerpt available.')}"
                    </div>
                </a>
            `;
        }).join("");
    }

    overlay.classList.add("active");

    if (highlightName) {
        setTimeout(() => {
            const el = body.querySelector(".highlighted");
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 300);
    }
};

window.openSourcesFromCitation = function(name) {
    window.openSourcesPanel(name);
};

window.closeSourcesPanel = function() {
    const overlay = document.getElementById("sources-panel-overlay");
    if (overlay) overlay.classList.remove("active");
};

document.addEventListener("DOMContentLoaded", () => {
   const closeBtn = document.getElementById("btn-close-sources");
   const overlay = document.getElementById("sources-panel-overlay");
   if(closeBtn) closeBtn.onclick = window.closeSourcesPanel;
   if(overlay) {
       overlay.onclick = (e) => {
           if(e.target === overlay) window.closeSourcesPanel();
       };
   }
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        window.closeSourcesPanel();
        window.closeKnowledgeInspector();
    }
});

// --- KNOWLEDGE INSPECTOR (DEBUG) ---
window.openKnowledgeInspector = async function() {
    const modal = document.getElementById("modal-knowledge-inspector");
    const list = document.getElementById("inspector-list");
    const loading = document.getElementById("inspector-loading");
    const empty = document.getElementById("inspector-empty");
    const stat = document.getElementById("inspector-stats");
    const metricPills = document.getElementById("metric-pills");
    
    if (!modal || !list) return;
    
    modal.classList.remove("hidden");
    list.innerHTML = "";
    loading.style.display = "block";
    empty.style.display = "none";
    stat.textContent = "Traversing Qdrant...";
    if (metricPills) metricPills.innerHTML = "";

    try {
        const res = await fetch(`${API_BASE}/rag/debug/indices`);
        const data = await res.json();
        
        loading.style.display = "none";
        const files = data.files || [];
        const m = data.metrics || {};
        
        if (metricPills) {
            metricPills.innerHTML = `
                <div class="metric-pill"><i class="fas fa-file"></i> Unique Files: <b>${m.total_files || 0}</b></div>
                <div class="metric-pill"><i class="fas fa-hdd"></i> Local: <b>${m.local_count || 0}</b></div>
                <div class="metric-pill"><i class="fas fa-cloud"></i> Cloud: <b>${m.cloud_count || 0}</b></div>
                <div class="metric-pill"><i class="fas fa-layer-group"></i> Total Chunks: <b>${m.total_chunks || 0}</b></div>
                <div class="metric-pill"><i class="fas fa-scroll"></i> Summaries: <b>${m.summaries_generated || 0}</b></div>
            `;
        }

        if (files.length === 0) {
            empty.style.display = "block";
            stat.textContent = "Database is currently empty.";
        } else {
            stat.textContent = `Audit complete. Found ${files.length} unique source documents.`;
            window._cachedInspectorFiles = files; 
            renderInspectorGrouped(files);
        }
    } catch (err) {
        loading.style.display = "none";
        empty.style.display = "block";
        empty.innerHTML = `<span style="color:var(--error)">Error querying Qdrant: ${err.message}</span>`;
    }
};

window.closeKnowledgeInspector = function() {
    const modal = document.getElementById("modal-knowledge-inspector");
    if (modal) modal.classList.add("hidden");
};

function renderInspectorGrouped(files) {
    const list = document.getElementById("inspector-list");
    if (!list) return;
    
    list.innerHTML = files.map((f, idx) => {
        const chunkCount = f.chunks?.length || 0;
        const statusClass = chunkCount > 0 ? "badge-status-ok" : "badge-status-warn";
        const statusText = chunkCount > 0 ? `${chunkCount} chunks` : "EMPTY / ERROR";

        // Summary badge
        let summaryBadge;
        if (f.has_summary) {
            summaryBadge = `<button class="summary-badge has-summary" onclick="event.stopPropagation(); window.toggleInspectorRow(${idx})" title="View summary">
                <i class="fas fa-check-circle"></i> Generated
            </button>`;
        } else {
            summaryBadge = `<button class="summary-badge no-summary" id="sum-btn-${idx}" onclick="event.stopPropagation(); window.generateFileSummary(${idx})" title="Generate summary for this file">
                <i class="fas fa-magic"></i> Generate
            </button>`;
        }

        // Summary display block (shown inside expansion row)
        let summaryBlock = '';
        if (f.has_summary && f.summary_text) {
            summaryBlock = `
                <div class="summary-display" id="summary-block-${idx}">
                    <div class="summary-display-header">
                        <i class="fas fa-scroll"></i> Document Summary
                    </div>
                    <div class="summary-display-text">${escapeHtml(f.summary_text)}</div>
                </div>`;
        }
        
        return `
            <tr class="file-row" onclick="window.toggleInspectorRow(${idx})">
                <td style="text-align:center;"><i class="fas fa-chevron-right expander-icon" id="exp-icon-${idx}"></i></td>
                <td style="font-weight:600; padding-left: 0;">${escapeHtml(f.name)}</td>
                <td><span class="badge-source badge-${f.source}">${f.source}</span></td>
                <td><span class="badge-status ${statusClass}">${statusText}</span></td>
                <td>${summaryBadge}</td>
                <td style="color:var(--text-dim); font-size: 0.75rem;">${formatDate(f.modified)}</td>
            </tr>
            <tr class="chunk-expansion-row hidden" id="chunk-row-${idx}">
                <td colspan="6">
                    <div class="chunk-container" onclick="event.stopPropagation()">
                        ${summaryBlock}
                        <div id="summary-inline-${idx}"></div>
                        ${f.chunks.map((c, cIdx) => `
                            <div class="chunk-item">
                                <div class="chunk-meta">
                                    <span>Snippet #${cIdx + 1}${c.section ? ` · ${escapeHtml(c.section)}` : ''}</span>
                                    <span>ID: ${c.id?.toString().substring(0,8)}...</span>
                                </div>
                                <div class="chunk-content-raw">${escapeHtml(c.text)}</div>
                            </div>
                        `).join("")}
                        ${chunkCount === 0 ? '<div style="padding:10px; opacity:0.5; font-size:0.8rem;">Potential processing failure: No semantic chunks found.</div>' : ''}
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

window.toggleInspectorRow = function(idx) {
    const row = document.getElementById(`chunk-row-${idx}`);
    const icon = document.getElementById(`exp-icon-${idx}`);
    const parent = icon.closest('.file-row');
    
    if (row) {
        const isHidden = row.classList.toggle("hidden");
        parent.classList.toggle("expanded", !isHidden);
    }
};

// --- Summary Generation ---
window.generateFileSummary = async function(idx) {
    const files = window._cachedInspectorFiles || [];
    const f = files[idx];
    if (!f || !f.file_id || !f.collection) return;

    const btn = document.getElementById(`sum-btn-${idx}`);
    if (btn) {
        btn.className = "summary-badge generating";
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating…';
    }

    try {
        const res = await fetchWithTimeout(`${API_BASE}/rag/summary/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
            body: JSON.stringify({ file_id: f.file_id, collection: f.collection }),
        }, 120000);

        const data = await res.json();

        if (data.error) {
            if (btn) {
                btn.className = "summary-badge no-summary";
                btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
            }
            showToast(`Summary failed: ${data.error}`, "error");
            return;
        }

        // Update cached data
        f.has_summary = true;
        f.summary_text = data.summary;

        // Update the button to show success
        if (btn) {
            btn.className = "summary-badge has-summary";
            btn.innerHTML = '<i class="fas fa-check-circle"></i> Generated';
            btn.onclick = function(e) { e.stopPropagation(); window.toggleInspectorRow(idx); };
        }

        // Insert the summary display inline
        const inlineTarget = document.getElementById(`summary-inline-${idx}`);
        if (inlineTarget) {
            inlineTarget.innerHTML = `
                <div class="summary-display">
                    <div class="summary-display-header">
                        <i class="fas fa-scroll"></i> Document Summary
                    </div>
                    <div class="summary-display-text">${escapeHtml(data.summary)}</div>
                </div>`;
        }

        // Expand the row to show the summary
        const row = document.getElementById(`chunk-row-${idx}`);
        if (row && row.classList.contains("hidden")) {
            window.toggleInspectorRow(idx);
        }

        showToast(`Summary generated for "${f.name}"`, "success");

    } catch (err) {
        if (btn) {
            btn.className = "summary-badge no-summary";
            btn.innerHTML = '<i class="fas fa-magic"></i> Retry';
        }
        showToast(`Summary generation failed: ${err.message}`, "error");
    }
};

// Search Filter
document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("inspector-search");
    if (searchInput) {
        searchInput.oninput = () => {
            const val = searchInput.value.toLowerCase();
            const filtered = (window._cachedInspectorFiles || []).filter(f => 
                (f.name && f.name.toLowerCase().includes(val)) || 
                (f.chunks && f.chunks.some(c => c.text.toLowerCase().includes(val)))
            );
            renderInspectorGrouped(filtered);
        };
    }

    const inspectBtn = document.getElementById("btn-inspect-knowledge");
    if (inspectBtn) {
        inspectBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            window.openKnowledgeInspector();
        };
    }
});
