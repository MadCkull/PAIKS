let _driveFiles = [];
let _localTree  = null;
let _activeTab  = "cloud";

function driveFileIcon(mime, name = "") {
  if (mime && mime.includes("folder")) return "📁";
  const ext = name.split('.').pop().toLowerCase();
  if (mime?.includes("pdf") || ext === "pdf") return "📕";
  if (mime?.includes("spreadsheet") || mime?.includes("excel") || ext === "csv") return "📊";
  if (mime?.includes("presentation") || mime?.includes("slide")) return "📽️";
  if (mime?.includes("image")) return "🖼️";
  if (mime?.includes("python") || ext === "py") return "🐍";
  if (mime?.includes("document") || mime?.includes("doc") || mime?.includes("text") || ext === "md" || ext === "txt") return "📝";
  return "📄";
}

function renderTree(containerId, treeData, query = "", source = "cloud") {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!treeData || (Array.isArray(treeData) && treeData.length === 0)) {
    const icon = source === "cloud" ? "☁️" : "💻";
    const msg  = source === "cloud" ? "Connect Google Drive to see files." : "Select a local root folder in Settings.";
    container.innerHTML = `
      <div style="text-align:center;padding:40px 20px;">
        <div style="font-size:2rem;margin-bottom:12px;">${icon}</div>
        <p style="color:var(--text-secondary);">${msg}</p>
      </div>`;
    return;
  }

  function buildHtml(node, isRoot = false) {
    const isDir = node.type === "dir" || (node.mimeType && node.mimeType.includes("folder"));
    const name  = node.name || "Untitled";

    if (query && !isRoot) {
      const match = name.toLowerCase().includes(query.toLowerCase());
      if (!match && (!node.children || node.children.length === 0)) return "";
    }

    const icon = isDir ? "📁" : driveFileIcon(node.mimeType, name);
    const accent = source === "cloud" ? "var(--cloud)" : "var(--local)";

    let childHtml = "";
    if (node.children && node.children.length > 0) {
      childHtml = node.children.map(c => buildHtml(c)).join("");
    } else if (source === "cloud" && isRoot && Array.isArray(node.files)) {
      childHtml = node.files.map(f => buildHtml({...f, type: "file"})).join("");
    }

    if (query && isDir && !childHtml && !isRoot) return "";

    return `
      <div class="tree-node" style="${isRoot ? 'font-weight:600;' : ''}">
        <input type="checkbox" checked style="accent-color:${accent};">
        <span>${icon}</span>
        <span class="name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
        ${node.size ? `<span class="meta">${formatSize(node.size)}</span>` : ""}
      </div>
      <div class="tree-children" style="padding-left:20px;">
        ${childHtml}
      </div>
    `;
  }

  let rootNode = treeData;
  if (Array.isArray(treeData)) {
    rootNode = { name: "Google Drive", type: "dir", children: treeData };
  }

  container.innerHTML = buildHtml(rootNode, true);
}

window.updateDriveModal = async function() {
  const searchInput = document.getElementById("drive-search-input");
  const query = searchInput ? searchInput.value.trim() : "";
  const localMode = localStorage.getItem("paiks-mode") === "local";

  let settings = {};
  let stats = {};

  // Fetch settings & stats independently
  try {
    const res = await fetchWithTimeout(`${API_BASE}/system/settings`, {}, 5000);
    settings = await res.json();
  } catch(_) {}

  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    stats = await res.json();
  } catch(_) {}

  // ── CLOUD TREE ──────────────────────────────────────────
  if (!localMode && stats.authenticated && settings.cloud_enabled) {
    try {
      const filesRes = await fetchWithTimeout(`${API_BASE}/drive/files?pageSize=100`, {}, 10000);
      const filesData = await filesRes.json();
      _driveFiles = filesData.files || [];
      const rootName = filesData.folder?.name || stats.folder?.name || "Google Drive";
      renderTree("tree-cloud", { name: rootName, type: "dir", children: _driveFiles }, query, "cloud");
    } catch(e) {
      renderTree("tree-cloud", null, "", "cloud");
    }
  } else {
    renderTree("tree-cloud", null, "", "cloud");
    // Auto-switch to local tab if in local mode
    if (localMode) {
      const localTab = document.querySelector('#drive-tabs [data-tab="local"]');
      if (localTab) localTab.click();
    }
  }

  // ── LOCAL TREE ──────────────────────────────────────────
  if (settings.local_enabled && settings.local_root_path) {
    try {
      const localRes = await fetchWithTimeout(`${API_BASE}/local/tree`, {}, 10000);
      _localTree = await localRes.json();
      renderTree("tree-local", _localTree, query, "local");
    } catch (e) {
      renderTree("tree-local", null, "", "local");
    }
  } else {
    renderTree("tree-local", null, "", "local");
  }

  // ── CONSOLE LOGS ────────────────────────────────────────
  const el = document.getElementById("sync-console");
  if (el) {
    el.innerHTML = "";
    if (stats.authenticated && !localMode) consoleLog(`[OK] Cloud: ${stats.cloud_total || 0} files indexed`, "ok");
    if (localMode && !stats.authenticated) consoleLog(`[INFO] Running in local mode`, "info");
    if (settings.local_root_path) consoleLog(`[OK] Local: Root set to ${settings.local_root_path}`, "ok");
    if (stats.synced_at && stats.synced_at !== "Not synced yet") consoleLog(`[INFO] Last sync: ${timeAgo(stats.synced_at)}`, "info");
  }
};

// ── TAB & SEARCH LOGIC ───────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll("#drive-tabs .pill-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active", "cloud-active", "local-active"));
      const type = tab.dataset.tab;
      _activeTab = type;
      tab.classList.add("active", `${type}-active`);

      const cloudTree = document.getElementById("tree-cloud");
      const localTree = document.getElementById("tree-local");
      if (cloudTree) cloudTree.style.display = type === "cloud" ? "" : "none";
      if (localTree) localTree.style.display = type === "local" ? "" : "none";
    });
  });

  const searchInput = document.getElementById("drive-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim();
      if (_activeTab === "cloud") {
        updateDriveModal();
      } else {
        renderTree("tree-local", _localTree, q, "local");
      }
    });
  }
});

function consoleLog(msg, type = "info") {
  const el = document.getElementById("sync-console");
  if (!el) return;
  const cls = { ok: "log-ok", warn: "log-warn", info: "log-info" }[type] || "log-info";
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

window.triggerSync = async function() {
  const btn = document.getElementById("btn-sync-now");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Syncing…"; }
  consoleLog("[INFO] Starting sync & ingest…", "info");

  const localMode = localStorage.getItem("paiks-mode") === "local";

  try {
    // Only sync cloud if NOT in local-only mode and authenticated
    if (!localMode) {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/drive/sync`, {
          method: "POST",
          headers: { "X-CSRFToken": getCsrfToken() }
        }, 60000);
        const data = await res.json();
        if (data.error) {
          consoleLog(`[WARN] Cloud: ${data.error}`, "warn");
        } else {
          consoleLog(`[OK] Cloud sync: ${data.total} files`, "ok");
        }
      } catch(e) {
        consoleLog(`[WARN] Cloud sync skipped: ${e.message}`, "warn");
      }
    } else {
      consoleLog("[INFO] Cloud sync skipped (local mode)", "info");
    }

    // Always run ingest (handles both sources)
    consoleLog("[INFO] Creating embeddings…", "info");
    const ingestRes = await fetchWithTimeout(`${API_BASE}/rag/ingest`, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() }
    }, 600000);
    const ingestData = await ingestRes.json();

    if (ingestData.error) {
      consoleLog(`[WARN] ${ingestData.error}`, "warn");
    } else {
      consoleLog(`[OK] ${ingestData.files_processed} files processed, ${ingestData.total_chunks} chunks`, "ok");
      consoleLog("[DONE] All sources up to date", "ok");
    }
    await updateDriveModal();
  } catch (e) {
    consoleLog(`[ERROR] Sync failed: ${e.message}`, "warn");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🔄 Sync Now"; }
  }
};

window.loadFiles = async function(query = "") {
  const container = document.getElementById("files-container");
  if (!container) return;
  container.innerHTML = Array(3).fill('<div class="skeleton skeleton-block"></div>').join("");

  try {
    const url = new URL(`${window.location.origin}${API_BASE}/drive/files`);
    if (query) url.searchParams.set("q", query);
    const res = await fetchWithTimeout(url, {}, 10000);
    const data = await res.json();

    if (data.error || !data.files?.length) {
      container.innerHTML = `<div class="text-center p-lg color-dim">No files found.</div>`;
      return;
    }

    container.innerHTML = data.files.map(f => `
      <a href="${f.webViewLink || '#'}" target="_blank" class="file-card">
        <div class="file-icon ${getFileClass(f.mimeType)}">${getFileEmoji(f.mimeType)}</div>
        <div class="file-info">
          <div class="file-name">${escapeHtml(f.name)}</div>
          <div class="file-meta">${formatMimeType(f.mimeType)} · ${formatSize(f.size)}</div>
        </div>
      </a>
    `).join("");
  } catch (e) {
    container.innerHTML = `<div class="text-center p-lg color-dim">Could not load files.</div>`;
  }
};
