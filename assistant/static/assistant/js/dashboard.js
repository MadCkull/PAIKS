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
};

window.loadDashboardStats = async function() {
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

window.updateDashboardStats = async function() {
  try {
    const res = await fetch(`${API_BASE}/drive/stats`);
    const data = await res.json();
    const total = data.documents_total || 0;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("stat-total",       total);
    set("stat-cloud",       total);
    set("stat-local",       0);
    set("stat-sync",        timeAgo(data.synced_at));
    set("stat-sync-cloud",  timeAgo(data.synced_at));

    const fileTypes = data.file_types || {};
    const entries = Object.entries(fileTypes).sort((a, b) => b[1] - a[1]);
    const distEl = document.getElementById("dist-bars");
    if (distEl && entries.length > 0) {
      distEl.innerHTML = entries.slice(0, 8).map(([type, count]) => {
        const label = MIME_LABELS[type] || type;
        const pct = Math.max(4, Math.round((count / total) * 80));
        return `<div class="dist-bar-row">
          <span class="dist-bar-label">${escapeHtml(label)}</span>
          <div class="dist-bar-track">
            <div class="dist-bar-fill cloud-fill" style="width:${pct}%;">${count}</div>
          </div>
          <span class="dist-bar-total">${count}</span>
        </div>`;
      }).join("");
    } else if (distEl) {
      distEl.innerHTML = `<p style="color:var(--text-dim);font-size:.85rem;">No files indexed yet.</p>`;
    }

    const totalBytes = (data.total_size_bytes || 0);
    set("stat-storage",       totalBytes ? formatSize(totalBytes) : "—");
    set("stat-storage-cloud", totalBytes ? formatSize(totalBytes) : "—");
    set("stat-storage-local", "0 B");
  } catch (_) {}

  try {
    const res = await fetch(`${API_BASE}/rag/status`);
    const data = await res.json();
    const chunks = data.total_chunks || 0;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("stat-embeddings",   chunks.toLocaleString());
    set("stat-emb-cloud",    chunks.toLocaleString());
    set("stat-emb-local",    "0");
  } catch (_) {}

  try {
    const res = await fetch(`${API_BASE}/rag/llm/status`);
    const data = await res.json();
    const llmEl    = document.getElementById("stat-llm");
    const llmModel = document.getElementById("stat-llm-model");
    if (llmEl) {
      llmEl.textContent  = data.reachable ? "● Online" : "● Offline";
      llmEl.style.color  = data.reachable ? "var(--color-success)" : "var(--color-error)";
    }
    if (llmModel) llmModel.textContent = data.provider
      ? `${data.provider} / ${data.current_model || "—"}` : "";
  } catch (_) {}
}

window.updateToolbarContext = async function() {
  try {
    const res = await fetch(`${API_BASE}/drive/stats`);
    const data = await res.json();
    const cloud = data.cloud_total || data.documents_total || 0;
    const local = data.local_total || 0;
    const ctx = document.getElementById("toolbar-context");
    if (!ctx) return;
    const cloudEl = ctx.querySelector(".cloud-count");
    const localEl = ctx.querySelector(".local-count");
    const sep = ctx.querySelector(".sep");
    if (cloudEl) cloudEl.textContent = cloud;
    if (localEl) localEl.textContent = local;
    if (sep) sep.style.display = (cloud > 0 && local > 0) ? "" : "none";
  } catch (_) {}
}

window.handleFeatureSync = async function() {
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
      setTimeout(() => { openModal("dashboard-overlay"); updateDashboardStats(); }, 1200);
    }
  } catch (err) {
    showToast("Sync failed: " + err.message, "error");
  } finally {
    if (card) card.classList.remove("feature-card-loading");
    if (icon) icon.textContent = "🔄";
  }
}

window.handleFeatureSearch = function() {
  const chatInput = document.getElementById("chat-input");
  if(chatInput) {
      chatInput.focus();
  }
}
