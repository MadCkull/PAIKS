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

window.updateDashboardStats = async function() {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // ── File Stats (independent) ───────────────────────────────
  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    const stats = await res.json();

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
  } catch(e) {
    console.warn("Stats fetch failed:", e.message);
  }

  // ── Embeddings (independent) ───────────────────────────────
  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/status`, {}, 5000);
    const rag = await res.json();
    set("stat-embeddings", (rag.total_chunks || 0).toLocaleString());
  } catch(_) {
    set("stat-embeddings", " - ");
  }

  // ── LLM Status (independent) ───────────────────────────────
  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 5000);
    const llm = await res.json();
    const llmEl = document.getElementById("stat-llm");
    if (llmEl) {
      llmEl.textContent = llm.reachable ? "● Online" : "● Offline";
      llmEl.style.color = llm.reachable ? "var(--color-success)" : "var(--color-error)";
    }
    const llmModel = document.getElementById("stat-llm-model");
    if (llmModel) llmModel.textContent = llm.provider ? `${llm.provider} / ${llm.current_model || " - "}` : "";
  } catch(_) {
    const llmEl = document.getElementById("stat-llm");
    if (llmEl) { llmEl.textContent = "● Offline"; llmEl.style.color = "var(--color-error)"; }
  }
};

window.updateToolbarContext = async function() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    const data = await res.json();
    
    const countEl = document.getElementById("toolbar-indexed-count");
    if (countEl) countEl.textContent = data.indexed_total || 0;
  } catch (_) {}
};

// handleFeatureSync removed since Sync is fully automated.

window.handleFeatureSearch = function() {
  const chatInput = document.getElementById("chat-input");
  if (chatInput) chatInput.focus();
};
