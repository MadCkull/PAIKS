/* =========================================================================
   PAIKS – Client-side JavaScript
   ========================================================================= */

const API_BASE = "http://127.0.0.1:5001";

// Helper: fetch with timeout (default 30s)
function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal })
    .finally(() => clearTimeout(id));
}

// ---------------------------------------------------------------------------
// Toast Notifications
// ---------------------------------------------------------------------------
function showToast(message, type = "info") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(40px)";
    toast.style.transition = "all .3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------
async function checkAuthStatus() {
  try {
    const res = await fetch(`${API_BASE}/auth/status`);
    const data = await res.json();
    return data.authenticated;
  } catch {
    return false;
  }
}

async function updateConnectionUI() {
  const connected = await checkAuthStatus();
  // Update sidebar dot
  const dot = document.querySelector(".connection-dot");
  if (dot) {
    dot.className = `connection-dot ${connected ? "connected" : "disconnected"}`;
  }
  const statusLabel = document.getElementById("connection-label");
  if (statusLabel) {
    statusLabel.textContent = connected ? "Google Drive Connected" : "Not Connected";
  }

  // Toggle connect / disconnect buttons
  const connectBtn = document.getElementById("btn-connect");
  const disconnectBtn = document.getElementById("btn-disconnect");
  if (connectBtn) connectBtn.classList.toggle("hidden", connected);
  if (disconnectBtn) disconnectBtn.classList.toggle("hidden", !connected);

  // Badge on home hero
  const statusBadge = document.getElementById("auth-status-badge");
  if (statusBadge) {
    statusBadge.className = `badge ${connected ? "badge-green" : "badge-dim"}`;
    statusBadge.innerHTML = connected
      ? '<span class="connection-dot connected"></span> Connected'
      : '<span class="connection-dot disconnected"></span> Not Connected';
  }

  return connected;
}

async function connectDrive() {
  try {
    const res = await fetch(`${API_BASE}/auth/url`);
    const data = await res.json();
    if (data.url) {
      window.location.href = data.url;
    } else {
      showToast(data.error || "Could not get auth URL", "error");
    }
  } catch (err) {
    showToast("Failed to connect: " + err.message, "error");
  }
}

async function disconnectDrive() {
  try {
    await fetch(`${API_BASE}/auth/disconnect`, { method: "POST" });
    showToast("Google Drive disconnected", "info");
    updateConnectionUI();
    // Reload page to reset state
    setTimeout(() => location.reload(), 800);
  } catch (err) {
    showToast("Disconnect failed: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
let searchTimeout;

function initSearch() {
  const input = document.getElementById("search-input");
  const btn = document.getElementById("search-btn");
  const resultsContainer = document.getElementById("search-results");
  if (!input || !resultsContainer) return;

  const performSearch = async () => {
    const query = input.value.trim();
    if (!query) {
      resultsContainer.innerHTML = "";
      return;
    }

    resultsContainer.innerHTML = '<div class="flex-center mt-md"><div class="spinner"></div></div>';

    try {
      const res = await fetchWithTimeout(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      }, 15000);
      const data = await res.json();

      if (data.error) {
        resultsContainer.innerHTML = `<p class="text-muted mt-sm">${data.error}</p>`;
        return;
      }

      if (!data.results || data.results.length === 0) {
        resultsContainer.innerHTML = '<p class="text-muted mt-sm">No results found.</p>';
        return;
      }

      resultsContainer.innerHTML = data.results
        .map(
          (r, i) => `
          <a href="${r.webViewLink || "#"}" target="_blank" rel="noopener" class="result-item" style="animation-delay:${i * 0.06}s">
            <div class="result-icon">${getFileEmoji(r.mimeType || r.name || "")}</div>
            <div class="result-info">
              <div class="result-name">${escapeHtml(r.name || r.title || "")}</div>
              <div class="result-meta">${r.mimeType ? formatMimeType(r.mimeType) : ""} ${r.modifiedTime ? "· " + formatDate(r.modifiedTime) : ""}</div>
            </div>
          </a>`
        )
        .join("");
    } catch (err) {
      const msg = err.name === "AbortError" ? "Search timed out. Try again." : "Search failed: " + err.message;
      resultsContainer.innerHTML = `<p class="text-muted mt-sm">${msg}</p>`;
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(performSearch, 400);
  });

  if (btn) btn.addEventListener("click", performSearch);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(searchTimeout);
      performSearch();
    }
  });
}

// ---------------------------------------------------------------------------
// Sync
// ---------------------------------------------------------------------------
async function triggerSync() {
  const btn = document.getElementById("btn-sync");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Syncing…';
  }

  try {
    const res = await fetch(`${API_BASE}/drive/sync`, { method: "POST" });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, "error");
    } else {
      showToast(`Synced ${data.total} files!`, "success");
      setTimeout(() => location.reload(), 1000);
    }
  } catch (err) {
    showToast("Sync failed: " + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "🔄 Sync Now";
    }
  }
}

// ---------------------------------------------------------------------------
// Dashboard Stats
// ---------------------------------------------------------------------------
async function loadDashboardStats() {
  const totalEl = document.getElementById("stat-total");
  const syncedEl = document.getElementById("stat-synced");
  const typesEl = document.getElementById("stat-types");
  if (!totalEl) return;

  try {
    const res = await fetch(`${API_BASE}/drive/stats`);
    const data = await res.json();

    totalEl.textContent = data.documents_total || 0;

    if (syncedEl) {
      syncedEl.textContent = data.synced_at && data.synced_at !== "Not synced yet"
        ? formatDate(data.synced_at)
        : "Not synced yet";
    }

    if (typesEl && data.file_types) {
      typesEl.innerHTML = Object.entries(data.file_types)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 12)
        .map(([type, count]) => `<span class="badge badge-dim">${type} <strong>${count}</strong></span>`)
        .join("");
    }
  } catch (err) {
    if (totalEl) totalEl.textContent = "—";
    console.error("Stats error:", err);
  }
}

// ---------------------------------------------------------------------------
// File Browser
// ---------------------------------------------------------------------------
async function loadFiles(query = "") {
  const container = document.getElementById("files-container");
  if (!container) return;

  container.innerHTML = Array(6)
    .fill('<div class="skeleton skeleton-block" style="height:80px"></div>')
    .join("");

  try {
    const url = new URL(`${API_BASE}/drive/files`);
    if (query) url.searchParams.set("q", query);

    const res = await fetch(url);
    const data = await res.json();

    if (data.error) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔒</div>
          <p><strong>Not connected</strong></p>
          <p>Connect your Google Drive to browse files.</p>
        </div>`;
      return;
    }

    if (!data.files || data.files.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📁</div>
          <p>No files found.</p>
        </div>`;
      return;
    }

    container.innerHTML = data.files
      .map(
        (f, i) => `
        <a href="${f.webViewLink || "#"}" target="_blank" rel="noopener" class="file-card" style="animation-delay:${i * 0.04}s">
          <div class="file-icon ${getFileClass(f.mimeType)}">${getFileEmoji(f.mimeType)}</div>
          <div class="file-info">
            <div class="file-name">${escapeHtml(f.name)}</div>
            <div class="file-meta">
              ${formatMimeType(f.mimeType)}
              ${f.modifiedTime ? " · " + formatDate(f.modifiedTime) : ""}
              ${f.size ? " · " + formatSize(f.size) : ""}
            </div>
          </div>
        </a>`
      )
      .join("");
  } catch (err) {
    container.innerHTML = `<p class="text-muted">Failed to load files: ${err.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

function formatSize(bytes) {
  bytes = parseInt(bytes, 10);
  if (isNaN(bytes)) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i++;
  }
  return bytes.toFixed(i === 0 ? 0 : 1) + " " + units[i];
}

function formatMimeType(mime) {
  if (!mime) return "File";
  const map = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.folder": "Folder",
    "application/vnd.google-apps.form": "Google Form",
    "application/pdf": "PDF",
    "image/jpeg": "JPEG Image",
    "image/png": "PNG Image",
    "video/mp4": "MP4 Video",
    "text/plain": "Text File",
  };
  return map[mime] || mime.split("/").pop().split(".").pop();
}

function getFileEmoji(mime) {
  if (!mime) return "📄";
  if (mime.includes("folder")) return "📁";
  if (mime.includes("document") || mime.includes("doc")) return "📝";
  if (mime.includes("spreadsheet") || mime.includes("sheet") || mime.includes("excel")) return "📊";
  if (mime.includes("presentation") || mime.includes("slide") || mime.includes("powerpoint")) return "📽️";
  if (mime.includes("pdf")) return "📕";
  if (mime.includes("image")) return "🖼️";
  if (mime.includes("video")) return "🎬";
  if (mime.includes("audio")) return "🎵";
  if (mime.includes("zip") || mime.includes("archive") || mime.includes("compressed")) return "📦";
  if (mime.includes("form")) return "📋";
  return "📄";
}

function getFileClass(mime) {
  if (!mime) return "other";
  if (mime.includes("folder")) return "folder";
  if (mime.includes("document") || mime.includes("doc")) return "doc";
  if (mime.includes("spreadsheet") || mime.includes("sheet")) return "sheet";
  if (mime.includes("presentation") || mime.includes("slide")) return "slide";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("image")) return "img";
  return "other";
}

// ---------------------------------------------------------------------------
// Feature card handlers (home page)
// ---------------------------------------------------------------------------
async function handleFeatureSync() {
  const card = document.getElementById("card-sync");
  const icon = document.getElementById("sync-icon");
  if (card) card.classList.add("feature-card-loading");
  if (icon) icon.textContent = "⏳";

  try {
    const res = await fetch(`${API_BASE}/drive/sync`, { method: "POST" });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, "error");
    } else {
      showToast(`Synced ${data.total} files! Opening dashboard…`, "success");
      setTimeout(() => { window.location.href = "/dashboard/"; }, 1200);
    }
  } catch (err) {
    showToast("Sync failed: " + err.message, "error");
  } finally {
    if (card) card.classList.remove("feature-card-loading");
    if (icon) icon.textContent = "🔄";
  }
}

function handleFeatureSearch() {
  const input = document.getElementById("search-input");
  if (!input) return;
  input.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => input.focus(), 400);
}

// ---------------------------------------------------------------------------
// Local LLM – status, model picker, config
// ---------------------------------------------------------------------------
async function loadLLMStatus() {
  const dot = document.getElementById("llm-status-dot");
  const label = document.getElementById("llm-status-label");
  const modelSelect = document.getElementById("llm-model-select");
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  if (!dot) return;

  try {
    const res = await fetch(`${API_BASE}/rag/llm/status`);
    const data = await res.json();

    // Restore saved URL + provider into the form
    if (urlInput && data.base_url) urlInput.value = data.base_url;
    if (providerSelect && data.provider) providerSelect.value = data.provider;
    onProviderChange();

    if (data.reachable) {
      dot.className = "connection-dot connected";
      label.textContent = `Local LLM: ${data.current_model || "connected"}`;

      // Populate model dropdown
      if (modelSelect && data.available_models?.length) {
        modelSelect.innerHTML = data.available_models
          .map(m => `<option value="${m}"${m === data.current_model ? " selected" : ""}>${m}</option>`)
          .join("");
        modelSelect.style.display = "";
        const manualInput = document.getElementById("llm-model-input");
        if (manualInput) manualInput.style.display = "none";
      }
    } else {
      dot.className = "connection-dot disconnected";
      label.textContent = "Local LLM: not running";
      if (modelSelect) modelSelect.innerHTML = '<option value="">— not reachable —</option>';
      // Show manual input so user can type a model name
      const manualInput = document.getElementById("llm-model-input");
      if (manualInput) { manualInput.style.display = ""; manualInput.value = data.current_model || ""; }
      if (modelSelect) modelSelect.style.display = "none";
    }
  } catch {
    if (dot) dot.className = "connection-dot disconnected";
    if (label) label.textContent = "Local LLM: unavailable";
  }
}

function onProviderChange() {
  const provider = document.getElementById("llm-provider-select")?.value;
  const urlInput = document.getElementById("llm-url-input");
  if (!urlInput) return;
  const current = urlInput.value.trim();
  if (provider === "ollama" && (!current || current.includes("1234"))) {
    urlInput.value = "http://localhost:11434";
  } else if (provider === "openai_compat" && (!current || current.includes("11434"))) {
    urlInput.value = "http://localhost:1234";
  }
}

async function saveLLMConfig() {
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  const modelSelect = document.getElementById("llm-model-select");
  const modelInput = document.getElementById("llm-model-input");

  const base_url = urlInput?.value.trim();
  const provider = providerSelect?.value || "ollama";
  const model = (modelSelect?.style.display !== "none" ? modelSelect?.value : "")
    || modelInput?.value.trim()
    || modelSelect?.value;

  if (!base_url || !model) {
    showToast("Set a URL and model name first.", "error");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/rag/llm/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, model, provider }),
    });
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    showToast(`LLM set to ${model}`, "success");
    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to save LLM config: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// RAG – Index status + ingest
// ---------------------------------------------------------------------------
async function loadRagStatus() {
  const badge = document.getElementById("rag-status-badge");
  const ingestBtn = document.getElementById("btn-ingest");
  if (!badge) return;

  try {
    const res = await fetch(`${API_BASE}/rag/status`);
    const data = await res.json();

    if (data.ingest_running) {
      const pct = data.ingest_progress?.total
        ? Math.round((data.ingest_progress.processed / data.ingest_progress.total) * 100)
        : 0;
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
        document.getElementById("ingest-btn-label").textContent = "⚡ Re-index";
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

async function ragIngest() {
  const btn = document.getElementById("btn-ingest");
  const label = document.getElementById("ingest-btn-label");
  const badge = document.getElementById("rag-status-badge");

  if (btn) btn.disabled = true;
  if (label) label.innerHTML = '<span class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:5px;"></span>Indexing…';
  if (badge) { badge.className = "badge badge-dim"; badge.textContent = "Indexing…"; }

  try {
    const res = await fetch(`${API_BASE}/rag/ingest`, { method: "POST" });
    const data = await res.json();

    if (data.error) {
      showToast(data.error, "error");
      if (label) label.textContent = "⚡ Index Documents";
      if (btn) btn.disabled = false;
      return;
    }

    showToast(
      `Indexed ${data.files_processed} files · ${data.total_chunks} chunks created`,
      "success"
    );
    if (data.errors && data.errors.length > 0) {
      console.warn("Ingest errors:", data.errors);
    }
  } catch (err) {
    showToast("Indexing failed: " + err.message, "error");
  } finally {
    await loadRagStatus();
  }
}

// ---------------------------------------------------------------------------
// RAG Chat Search
// ---------------------------------------------------------------------------

function toggleLLMConfig() {
  const panel = document.getElementById("llm-config-panel");
  if (panel) panel.classList.toggle("hidden");
}

function useSuggestion(btn) {
  const input = document.getElementById("rag-input");
  if (input) {
    input.value = btn.textContent;
    ragSearch();
  }
}

function formatAnswer(text) {
  // Simple markdown-like formatting for LLM answers
  let html = escapeHtml(text);
  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic: *text*
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // [Source Name] citations — highlight them
  html = html.replace(/\[([^\]]+)\]/g, '<strong style="color:var(--accent-light);">[$1]</strong>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  // Bullet points
  html = html.replace(/(?:^|<br>)[-•]\s+(.+?)(?=<br>|$)/g, '<li>$1</li>');
  if (html.includes('<li>')) {
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
  }
  return html;
}

function addChatMessage(type, content) {
  const container = document.getElementById("chat-messages");
  if (!container) return;
  // Remove welcome screen on first message
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
  typing.className = "chat-typing";
  typing.id = "chat-typing-indicator";
  typing.innerHTML = `
    <div class="chat-msg-avatar" style="background:linear-gradient(135deg,#6c5ce7,#a855f7);">🧠</div>
    <div class="chat-typing-dots"><span></span><span></span><span></span></div>`;
  container.appendChild(typing);
  container.scrollTop = container.scrollHeight;
  return typing;
}

function removeTypingIndicator() {
  const el = document.getElementById("chat-typing-indicator");
  if (el) el.remove();
}

async function ragSearch() {
  const input = document.getElementById("rag-input");
  const btn = document.getElementById("rag-btn");
  const btnLabel = document.getElementById("rag-btn-label");
  if (!input) return;

  const query = input.value.trim();
  if (!query) return;

  // Add user message bubble
  addChatMessage("user", `
    <div class="chat-msg-avatar">👤</div>
    <div class="chat-msg-bubble">${escapeHtml(query)}</div>`);

  input.value = "";
  if (btn) btn.disabled = true;
  if (btnLabel) btnLabel.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px;"></span>';

  const typing = showTypingIndicator();

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }, 300000);  // 5min for RAG (local LLM on CPU can be slow)
    const data = await res.json();
    removeTypingIndicator();

    if (data.error) {
      addChatMessage("ai chat-msg-error", `
        <div class="chat-msg-avatar">🧠</div>
        <div class="chat-msg-bubble">${escapeHtml(data.error)}</div>`);
      return;
    }

    // Build AI response
    let answerContent = "";

    if (data.answer) {
      answerContent = formatAnswer(data.answer);
      if (data.answer_model) {
        answerContent += `<div style="margin-top:8px;font-size:.7rem;color:var(--text-dim);">Answered by ${escapeHtml(data.answer_model)}</div>`;
      }
    } else if (data.answer_error) {
      answerContent = `<span style="color:#fca5a5;">LLM unavailable: ${escapeHtml(data.answer_error)}</span><br><em style="font-size:.8rem;color:var(--text-dim);">Make sure Ollama is running.</em>`;
    } else if (!data.results || data.results.length === 0) {
      answerContent = `No matching documents found for <strong>"${escapeHtml(query)}"</strong>. ${
        data.indexed ? "Try rephrasing your question." : "Index your documents first using ⚡ Index Docs."
      }`;
    } else {
      answerContent = "I found relevant documents but couldn't generate an answer. Configure a local LLM in the settings below.";
    }

    // Build sources section
    const isSemantic = data.source === "semantic";
    let sourcesHtml = "";
    if (data.results && data.results.length > 0) {
      const uid = "src-" + Date.now();
      const sourceItems = data.results.map(r => {
        const scoreLabel = (isSemantic && r.score != null)
          ? `<span class="chat-source-score">${Math.round(r.score * 100)}%</span>`
          : "";
        return `
          <a href="${r.webViewLink || '#'}" target="_blank" rel="noopener" class="chat-source-item">
            <span class="chat-source-icon">${getFileEmoji(r.mimeType)}</span>
            <span class="chat-source-name">${escapeHtml(r.name)}</span>
            ${scoreLabel}
            <span style="color:var(--text-dim);font-size:.8rem;">↗</span>
          </a>`;
      }).join("");

      sourcesHtml = `
        <button class="chat-sources-toggle" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open');">
          <span class="arrow">▶</span> ${data.total} source${data.total !== 1 ? "s" : ""} found
        </button>
        <div class="chat-sources-list">${sourceItems}</div>`;
    }

    addChatMessage("ai", `
      <div class="chat-msg-avatar">🧠</div>
      <div class="chat-msg-bubble">
        ${answerContent}
        ${sourcesHtml}
      </div>`);

  } catch (err) {
    removeTypingIndicator();
    const isTimeout = err.name === "AbortError";
    const errorMsg = isTimeout
      ? "Request timed out. The LLM may be slow or not running. Try a shorter question or check your LLM config."
      : "Search failed: " + err.message;
    addChatMessage("ai chat-msg-error", `
      <div class="chat-msg-avatar">🧠</div>
      <div class="chat-msg-bubble">${escapeHtml(errorMsg)}</div>`);
  } finally {
    if (btn) btn.disabled = false;
    if (btnLabel) btnLabel.innerHTML = "&#10148;";
  }
}

// ---------------------------------------------------------------------------
// Folder Picker
// ---------------------------------------------------------------------------

function openFolderPicker() {
  // Remove any stale modal
  const existing = document.getElementById("folder-picker-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "folder-picker-modal";
  modal.innerHTML = `
    <div class="modal-backdrop" id="folder-modal-backdrop"></div>
    <div class="modal-box">
      <div class="modal-header">
        <div>
          <h2 class="modal-title">Choose a Folder to Sync</h2>
          <p class="modal-subtitle">Only files inside the selected folder will be fetched and searched.</p>
        </div>
        <button class="modal-close" id="folder-modal-close">✕</button>
      </div>
      <div class="modal-search-row">
        <input id="folder-filter-input" class="search-input" placeholder="Filter folders…" autocomplete="off" />
      </div>
      <div id="folder-list" class="folder-list">
        <div class="flex-center mt-md"><div class="spinner"></div></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline btn-sm" id="btn-use-all-drive">Use entire Drive (no folder filter)</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  const closeModal = () => modal.remove();
  document.getElementById("folder-modal-close").addEventListener("click", closeModal);
  document.getElementById("folder-modal-backdrop").addEventListener("click", closeModal);

  let allFolders = [];

  const renderFolders = (folders) => {
    const list = document.getElementById("folder-list");
    if (!list) return;
    if (folders.length === 0) {
      list.innerHTML = '<p class="text-muted" style="padding:12px 0;">No folders found.</p>';
      return;
    }
    list.innerHTML = folders.map(f => `
      <button class="folder-item" data-id="${escapeHtml(f.id)}" data-name="${escapeHtml(f.name)}">
        <span class="folder-item-icon">📁</span>
        <span class="folder-item-name">${escapeHtml(f.name)}</span>
        <span class="folder-item-arrow">→</span>
      </button>`).join("");

    list.querySelectorAll(".folder-item").forEach(btn => {
      btn.addEventListener("click", () => {
        selectFolder(btn.dataset.id, btn.dataset.name);
        closeModal();
      });
    });
  };

  // Load folders from API
  fetch(`${API_BASE}/drive/folders`)
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        document.getElementById("folder-list").innerHTML =
          `<p class="text-muted" style="padding:12px 0;">${data.error}</p>`;
        return;
      }
      allFolders = data.folders || [];
      renderFolders(allFolders);

      // Pre-select current folder in the list
      if (data.current_folder?.folder_id) {
        setTimeout(() => {
          const active = document.querySelector(`.folder-item[data-id="${data.current_folder.folder_id}"]`);
          if (active) {
            active.classList.add("folder-item-active");
            active.scrollIntoView({ block: "nearest" });
          }
        }, 50);
      }
    })
    .catch(err => {
      document.getElementById("folder-list").innerHTML =
        `<p class="text-muted" style="padding:12px 0;">Failed to load folders: ${err.message}</p>`;
    });

  // Live filter
  document.getElementById("folder-filter-input").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    renderFolders(q ? allFolders.filter(f => f.name.toLowerCase().includes(q)) : allFolders);
  });

  // Clear folder → use entire Drive
  document.getElementById("btn-use-all-drive").addEventListener("click", () => {
    clearFolderFilter();
    closeModal();
  });
}

async function selectFolder(folderId, folderName) {
  try {
    const res = await fetch(`${API_BASE}/drive/set-folder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId, folder_name: folderName }),
    });
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    showToast(`Sync scope set to: ${folderName}`, "success");
    updateFolderBadge({ folder_id: folderId, folder_name: folderName });
  } catch (err) {
    showToast("Failed to set folder: " + err.message, "error");
  }
}

async function clearFolderFilter() {
  try {
    await fetch(`${API_BASE}/drive/set-folder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    showToast("Sync scope reset to entire Drive", "info");
    updateFolderBadge(null);
  } catch (err) {
    showToast("Failed to reset folder: " + err.message, "error");
  }
}

function updateFolderBadge(folderCfg) {
  const badge = document.getElementById("folder-scope-badge");
  const name = document.getElementById("folder-scope-name");
  if (!badge) return;
  if (folderCfg?.folder_name) {
    badge.className = "badge badge-green";
    if (name) name.textContent = `📁 ${folderCfg.folder_name}`;
  } else {
    badge.className = "badge badge-dim";
    if (name) name.textContent = "Entire Drive";
  }
}

async function loadFolderBadge() {
  try {
    const res = await fetch(`${API_BASE}/drive/folder-config`);
    const data = await res.json();
    updateFolderBadge(data?.folder_id ? data : null);
  } catch {
    updateFolderBadge(null);
  }
}

// ---------------------------------------------------------------------------
// Clerk Auth Guard
// ---------------------------------------------------------------------------
async function initClerkAuth() {
  const guard = document.getElementById("auth-guard");

  // Check if Clerk config is set
  if (typeof CLERK_FRONTEND_API === "undefined" || CLERK_FRONTEND_API === "YOUR_FRONTEND_API_URL") {
    // Clerk not configured — skip auth, remove guard
    if (guard) guard.remove();
    return true;
  }

  // Wait for Clerk global to be available
  await new Promise((resolve) => {
    if (window.Clerk) return resolve();
    const interval = setInterval(() => {
      if (window.Clerk) { clearInterval(interval); resolve(); }
    }, 100);
    // Timeout after 10 seconds
    setTimeout(() => { clearInterval(interval); resolve(); }, 10000);
  });

  if (!window.Clerk) {
    console.warn("Clerk SDK failed to load");
    if (guard) guard.remove();
    return true;
  }

  await Clerk.load();

  if (!Clerk.isSignedIn) {
    // Redirect to login page
    window.location.href = "/login/";
    return false;
  }

  // Mount UserButton in sidebar
  const userBtnDiv = document.getElementById("clerk-user-button");
  if (userBtnDiv) {
    Clerk.mountUserButton(userBtnDiv, {
      afterSignOutUrl: "/login/",
    });
  }

  // Remove auth guard overlay
  if (guard) {
    guard.style.transition = "opacity .3s ease";
    guard.style.opacity = "0";
    setTimeout(() => guard.remove(), 300);
  }

  return true;
}

// ---------------------------------------------------------------------------
// Mobile sidebar toggle
// ---------------------------------------------------------------------------
function initMobileToggle() {
  const toggle = document.querySelector(".mobile-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
}

// ---------------------------------------------------------------------------
// Init on page load
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  initMobileToggle();

  // Clerk auth guard — blocks until verified
  const authed = await initClerkAuth();
  if (!authed) return; // Redirecting to login

  // Now init the rest of the app
  await updateConnectionUI();
  initSearch();

  // Page-specific init
  if (document.getElementById("stat-total")) {
    loadDashboardStats();
    loadFolderBadge();
  }
  if (document.getElementById("files-container")) {
    loadFiles();
    loadRagStatus();
    loadLLMStatus();
  }

  // RAG search — Enter key support
  const ragInput = document.getElementById("rag-input");
  if (ragInput) {
    ragInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") ragSearch();
    });
  }

  // File search on files page
  const fileSearchInput = document.getElementById("file-search-input");
  if (fileSearchInput) {
    let timeout;
    fileSearchInput.addEventListener("input", () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => loadFiles(fileSearchInput.value.trim()), 500);
    });
  }

  // Show success toast if redirected after auth
  const params = new URLSearchParams(window.location.search);
  if (params.get("connected") === "1") {
    showToast("Google Drive connected successfully!", "success");
    window.history.replaceState({}, "", window.location.pathname);
  }
});
