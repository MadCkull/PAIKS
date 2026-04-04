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

    set("stat-total",  stats.documents_total || 0);
    set("stat-cloud",  stats.cloud_total || 0);
    set("stat-local",  stats.local_total || 0);
    set("stat-sync",   timeAgo(stats.synced_at));
    set("stat-sync-cloud", timeAgo(stats.synced_at));

    const totalBytes = stats.total_size_bytes || 0;
    set("stat-storage", formatSize(totalBytes));

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
    set("stat-embeddings", "—");
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
    if (llmModel) llmModel.textContent = llm.provider ? `${llm.provider} / ${llm.current_model || "—"}` : "";
  } catch(_) {
    const llmEl = document.getElementById("stat-llm");
    if (llmEl) { llmEl.textContent = "● Offline"; llmEl.style.color = "var(--color-error)"; }
  }
};

window.updateToolbarContext = async function() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    const data = await res.json();
    const cloud = data.cloud_total || 0;
    const local = data.local_total || 0;

    const cloudEl = document.querySelector("#toolbar-context .cloud-count");
    const localEl = document.querySelector("#toolbar-context .local-count");
    const sep     = document.querySelector("#toolbar-context .sep");

    if (cloudEl) cloudEl.textContent = cloud;
    if (localEl) localEl.textContent = local;
    if (sep) sep.style.display = (cloud > 0 && local > 0) ? "" : "none";
  } catch (_) {}
};

window.handleFeatureSync = async function() {
  const card = document.getElementById("card-sync");
  const icon = document.getElementById("sync-icon");
  if (card) card.classList.add("feature-card-loading");
  if (icon) icon.textContent = "⏳";

  try {
    if (window.triggerSync) {
      await window.triggerSync();
    } else {
      await fetchWithTimeout(`${API_BASE}/rag/ingest`, { method: "POST", headers: { "X-CSRFToken": getCsrfToken() } }, 600000);
    }
    showToast("Sync completed", "success");
    setTimeout(() => { openModal("dashboard-overlay"); updateDashboardStats(); }, 500);
  } catch (err) {
    showToast("Sync failed", "error");
  } finally {
    if (card) card.classList.remove("feature-card-loading");
    if (icon) icon.textContent = "🔄";
  }
};

window.handleFeatureSearch = function() {
  const chatInput = document.getElementById("chat-input");
  if (chatInput) chatInput.focus();
};
