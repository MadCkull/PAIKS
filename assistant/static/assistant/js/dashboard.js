const MIME_LABELS = {
  document:     "Word / GDocs",
  plain:        "Text (.txt)",
  csv:          "CSV (.csv)",
  spreadsheet:  "Spreadsheet",
  presentation: "Presentation",
  pdf:          "PDF (.pdf)",
  "x-python":   "Python (.py)",
  python:       "Python (.py)",
  markdown:     "Markdown",
  json:         "JSON",
  docx:         "Word (.docx)",
  md:           "Markdown (.md)",
  txt:          "Plain Text (.txt)"
};

// ── SSE-driven auto-update helpers ───────────────────────────────

function _applyDriveStats(stats) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  set("stat-indexed",  stats.indexed_total || 0);
  const inProgress = (stats.syncing_total || 0) + (stats.pending_total || 0);
  set("stat-syncing",  inProgress);
  set("stat-disabled", stats.disabled_total || 0);
  set("stat-error",    stats.error_total || 0);

  const spinner = document.getElementById("dash-sync-spinner");
  if (spinner) spinner.style.display = inProgress > 0 ? "inline-block" : "none";

  // Distribution bars
  const fileTypes = stats.file_types || {};
  const entries = Object.entries(fileTypes).sort((a, b) => b[1] - a[1]);
  const distEl = document.getElementById("dist-bars");
  if (distEl && entries.length > 0) {
    const total = stats.documents_total || 1;
    distEl.innerHTML = entries.slice(0, 10).map(([type, count]) => {
      const label = MIME_LABELS[type] || type;
      const pct = Math.max(5, Math.round((count / total) * 100));
      return `
        <div class="dist-bar-row">
          <span class="dist-bar-label">${escapeHtml(label)}</span>
          <div class="dist-bar-track">
            <div class="dist-bar-fill cloud-fill" style="width:${pct}%;">${count}</div>
          </div>
          <span class="dist-bar-total">${count}</span>
        </div>`;
    }).join("");
  } else if (distEl) {
    distEl.innerHTML = `<p style="color:var(--text-dim);font-size:.85rem;">No files indexed.</p>`;
  }

  // Also update toolbar indexed count
  const countEl = document.getElementById("toolbar-indexed-count");
  if (countEl) countEl.textContent = stats.indexed_total || 0;
  
  if (window.updateToolbarStatusDot) window.updateToolbarStatusDot();
}

function _applyRagStatus(rag) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set("stat-embeddings", (rag.total_chunks || 0).toLocaleString());
  
  if (window.updateToolbarStatusDot) window.updateToolbarStatusDot();
}

function _applyLlmStatus(llm) {
  const llmEl = document.getElementById("stat-llm");
  if (llmEl) {
    llmEl.textContent = llm.reachable ? "● Online" : "● Offline";
    llmEl.style.color = llm.reachable ? "var(--color-success)" : "var(--color-error)";
  }
  const llmModel = document.getElementById("stat-llm-model");
  if (llmModel) llmModel.textContent = llm.provider ? `${llm.provider} / ${llm.current_model || " - "}` : "";
  
  if (window.updateToolbarStatusDot) window.updateToolbarStatusDot();
}


// ── Register SSE handlers (auto-update on push) ─────────────────
// These fire automatically whenever the backend pushes new data.
// No polling, no manual refresh needed.

if (typeof PAIKSEventBus !== "undefined") {
  PAIKSEventBus.on("drive_stats", _applyDriveStats);
  PAIKSEventBus.on("rag_status", _applyRagStatus);
  PAIKSEventBus.on("llm_status", _applyLlmStatus);
}


// ── On-demand fetch (initial page load fallback) ────────────────
// Called once on boot to prime the UI before SSE events start flowing.

window.updateDashboardStats = async function() {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // If SSE has already pushed fresh data, use it instead of fetching
  if (window._liveStats && window._liveStats.drive_stats) {
    _applyDriveStats(window._liveStats.drive_stats);
    if (window._liveStats.rag_status) _applyRagStatus(window._liveStats.rag_status);
    if (window._liveStats.llm_status) _applyLlmStatus(window._liveStats.llm_status);
    return;
  }

  // ── Fallback: HTTP fetch (runs only on first load) ──────────
  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    const stats = await res.json();
    _applyDriveStats(stats);
  } catch(e) {
    console.warn("Stats fetch failed:", e.message);
  }

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/status`, {}, 5000);
    const rag = await res.json();
    _applyRagStatus(rag);
  } catch(_) {
    set("stat-embeddings", " - ");
  }

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 5000);
    const llm = await res.json();
    _applyLlmStatus(llm);
  } catch(_) {
    const llmEl = document.getElementById("stat-llm");
    if (llmEl) { llmEl.textContent = "● Offline"; llmEl.style.color = "var(--color-error)"; }
  }
};

window.updateToolbarContext = async function() {
  // If SSE has already pushed data, use it
  if (window._liveStats && window._liveStats.drive_stats) {
    const countEl = document.getElementById("toolbar-indexed-count");
    if (countEl) countEl.textContent = window._liveStats.drive_stats.indexed_total || 0;
    return;
  }

  // Fallback: HTTP fetch
  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    const data = await res.json();
    const countEl = document.getElementById("toolbar-indexed-count");
    if (countEl) countEl.textContent = data.indexed_total || 0;
    
    // Seed system health for dot calculation if empty
    if (!window._liveStats) window._liveStats = {};
    window._liveStats.drive_stats = data;
    window.updateToolbarStatusDot();
  } catch (_) {}
};

window.updateToolbarStatusDot = function() {
  const dot = document.getElementById("toolbar-status-dot");
  const container = document.getElementById("toolbar-context");
  if (!dot) return;

  const ds = window._liveStats?.drive_stats || {};
  const ls = window._liveStats?.llm_status || {};
  const rs = window._liveStats?.rag_status || {};

  let state = "normal";
  let message = "System Normal";

  if (ds.error_total > 0) {
    state = "critical";
    message = `${ds.error_total} File Sync Error(s)`;
  } else if (ls.reachable === false) {
    state = "warning";
    message = "Ollama LLM Offline";
  } else if (!ds.authenticated && ds.cloud_enabled) {
    state = "warning";
    message = "Google Drive Disconnected";
  } else if ((ds.pending_total || 0) + (ds.syncing_total || 0) > 0) {
    state = "syncing";
    message = `${(ds.pending_total || 0) + (ds.syncing_total || 0)} Files Syncing...`;
  }

  // Update classes and native title
  dot.className = `status-dot status-dot-${state}`;
  if (container) {
    container.title = message;
  }
};

// handleFeatureSync removed since Sync is fully automated.

window.handleFeatureSearch = function() {
  const chatInput = document.getElementById("chat-input");
  if (chatInput) chatInput.focus();
};

