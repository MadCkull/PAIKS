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
async function fetchAuthState() {
  try {
    const res = await fetch(`${API_BASE}/auth/status`);
    return await res.json();
  } catch {
    return { authenticated: false, user: null };
  }
}

async function checkAuthStatus() {
  const data = await fetchAuthState();
  return !!data.authenticated;
}

/** Extract up to 2 initials from a display name or email. */
function getInitials(name) {
  if (!name) return "?";
  const clean = name.trim();
  // If it looks like an email, use first letter before @
  if (clean.includes("@")) return clean[0].toUpperCase();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

/** Sidebar: populate user name next to Clerk avatar. */
function syncSidebarIdentity(connected, user) {
  const nameEl = document.getElementById("sidebar-user-name");
  if (!nameEl) return;

  let displayName = "Guest";
  if (typeof window.Clerk !== "undefined" && window.Clerk.user) {
    const u = window.Clerk.user;
    displayName =
      u.fullName ||
      [u.firstName, u.lastName].filter(Boolean).join(" ").trim() ||
      u.primaryEmailAddress?.emailAddress ||
      u.username ||
      "Signed in";
  } else if (connected && user) {
    displayName = (user.display_name || user.email || "Guest").trim();
  }

  nameEl.textContent = displayName;
}

async function updateConnectionUI() {
  const data = await fetchAuthState();
  const connected = !!data.authenticated;
  const user = (data.user && typeof data.user === "object") ? data.user : {};

  const sidebarDot = document.getElementById("sidebar-connection-dot");
  if (sidebarDot) {
    sidebarDot.className = `connection-dot ${connected ? "connected" : "disconnected"}`;
  }

  const subEl = document.getElementById("connection-label");
  const badgeEl = document.getElementById("drive-profile-badge");
  const driveTitle = document.getElementById("drive-link-title");
  if (driveTitle) {
    driveTitle.textContent = "Google Drive";
  }
  if (subEl) {
    if (connected) {
      const email = (user.email || "").trim();
      const gname = (user.display_name || "").trim();
      subEl.textContent = gname && email ? `${gname} · ${email}` : email || gname || "Linked to your account";
    } else {
      subEl.textContent = "Not linked — connect from Home";
    }
  }
  if (badgeEl) {
    badgeEl.textContent = connected ? "Linked" : "";
    badgeEl.hidden = !connected;
  }

  syncSidebarIdentity(connected, user);

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
// Dashboard modal stats (new UI) — real data
// ---------------------------------------------------------------------------
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

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function timeAgo(isoString) {
  if (!isoString || isoString === "Not synced yet") return "Never";
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (diff < 60)   return diff + "s ago";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
}

async function updateDashboardStats() {
  // 1. Drive stats
  try {
    const res = await fetch(`${API_BASE}/drive/stats`);
    const data = await res.json();
    const total = data.documents_total || 0;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("stat-total",       total);
    set("stat-cloud",       total);   // all indexed files are from Drive (cloud)
    set("stat-local",       0);
    set("stat-sync",        timeAgo(data.synced_at));
    set("stat-sync-cloud",  timeAgo(data.synced_at));

    // File type distribution bars
    const fileTypes = data.file_types || {};
    const entries = Object.entries(fileTypes).sort((a, b) => b[1] - a[1]);
    const maxCount = entries.length ? entries[0][1] : 1;
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

    // Storage estimate (size field may not exist — show placeholder)
    const totalBytes = (data.total_size_bytes || 0);
    set("stat-storage",       totalBytes ? formatBytes(totalBytes) : "—");
    set("stat-storage-cloud", totalBytes ? formatBytes(totalBytes) : "—");
    set("stat-storage-local", "0 B");
  } catch (_) {}

  // 2. ChromaDB embeddings
  try {
    const res = await fetch(`${API_BASE}/rag/status`);
    const data = await res.json();
    const chunks = data.total_chunks || 0;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("stat-embeddings",   chunks.toLocaleString());
    set("stat-emb-cloud",    chunks.toLocaleString());
    set("stat-emb-local",    "0");
  } catch (_) {}

  // 3. LLM status
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

// ---------------------------------------------------------------------------
// Settings modal — populate with real data
// ---------------------------------------------------------------------------
async function updateSettingsModal() {
  // 1. Drive connection status
  try {
    const [authRes, statsRes] = await Promise.all([
      fetch(`${API_BASE}/auth/status`),
      fetch(`${API_BASE}/drive/stats`),
    ]);
    const auth  = await authRes.json();
    const stats = await statsRes.json();
    const connected = !!auth.authenticated;

    const folderEl  = document.getElementById("settings-drive-folder");
    const statusEl  = document.getElementById("settings-drive-status");
    const connectBtn    = document.getElementById("btn-connect-settings") || document.querySelector("#settings-overlay .btn-sm[onclick='connectDrive()']");
    const disconnectBtn = document.getElementById("btn-disconnect-settings");

    if (folderEl) {
      const folder = stats.folder?.name || stats.folder || null;
      folderEl.textContent = connected
        ? (folder ? `📁 ${folder}` : "Connected") + (stats.documents_total ? ` · ${stats.documents_total} files` : "")
        : "Not connected";
    }
    if (statusEl) {
      statusEl.textContent = connected ? `✓ Connected · ${stats.documents_total || 0} files indexed` : "Not connected";
      statusEl.style.color = connected ? "var(--color-success)" : "var(--text-dim)";
    }
    if (connectBtn)    connectBtn.style.display    = connected ? "none"  : "";
    if (disconnectBtn) disconnectBtn.style.display = connected ? ""      : "none";
  } catch (_) {}

  // 2. LLM status — populate model dropdown + restore saved config
  try {
    const res  = await fetch(`${API_BASE}/rag/llm/status`);
    const data = await res.json();

    const urlInput      = document.getElementById("llm-url-input");
    const providerSelect = document.getElementById("llm-provider-select");
    const modelSelect   = document.getElementById("llm-model-select");
    const modelInput    = document.getElementById("llm-model-input");

    if (urlInput && data.base_url)    urlInput.value       = data.base_url;
    if (providerSelect && data.provider) providerSelect.value = data.provider;

    if (data.reachable && data.available_models?.length) {
      // Show dropdown, hide manual input
      if (modelSelect) {
        modelSelect.innerHTML = data.available_models
          .map(m => `<option value="${m}"${m === data.current_model ? " selected" : ""}>${m}</option>`)
          .join("");
        modelSelect.style.display = "";
      }
      if (modelInput) modelInput.style.display = "none";
    } else {
      // LLM not reachable — show manual text input with saved model
      if (modelSelect) modelSelect.style.display = "none";
      if (modelInput) {
        modelInput.style.display = "";
        modelInput.value = data.current_model || "";
        modelInput.placeholder = data.reachable ? "type model name" : "LLM not reachable — type model name";
      }
    }

    if (typeof onProviderChange === "function") onProviderChange();
  } catch (_) {}
}

// ---------------------------------------------------------------------------
// Drive Manager modal — real data
// ---------------------------------------------------------------------------
let _driveFiles = [];   // cached for search filtering
let _ragFiles   = [];   // cached local rag files

function driveFileIcon(mime) {
  if (!mime) return "📄";
  if (mime.includes("folder"))          return "📁";
  if (mime.includes("spreadsheet") || mime.includes("excel") || mime.includes("csv")) return "📊";
  if (mime.includes("presentation") || mime.includes("slide")) return "📽️";
  if (mime.includes("pdf"))             return "📕";
  if (mime.includes("image"))           return "🖼️";
  if (mime.includes("python") || mime.endsWith(".py")) return "🐍";
  if (mime.includes("document") || mime.includes("doc") || mime.includes("text")) return "📝";
  return "📄";
}

function formatSize(bytes) {
  if (!bytes) return "";
  const b = parseInt(bytes);
  if (b < 1024)       return b + " B";
  if (b < 1048576)    return Math.round(b / 1024) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function renderCloudTree(files, folderName, query = "") {
  const cloudEl = document.getElementById("tree-cloud");
  if (!cloudEl) return;

  if (!files || files.length === 0) {
    cloudEl.innerHTML = `
      <div style="text-align:center;padding:40px 20px;">
        <div style="font-size:2rem;margin-bottom:12px;">☁️</div>
        <p style="color:var(--text-secondary);margin-bottom:16px;">
          ${_driveFiles.length === 0 ? "Connect Google Drive to see your files." : "No files match your search."}
        </p>
        ${_driveFiles.length === 0 ? `<button class="btn-primary" style="width:auto;padding:10px 24px;" onclick="connectDrive()">Connect Drive</button>` : ""}
      </div>`;
    return;
  }

  const filtered = query
    ? files.filter(f => f.name.toLowerCase().includes(query.toLowerCase()))
    : files;

  const root = folderName || "Google Drive";
  let html = `
    <div class="tree-node" style="font-weight:600;">
      <input type="checkbox" checked style="accent-color:var(--cloud);">
      <span>📁</span>
      <span class="name">${escapeHtml(root)}</span>
      <span class="meta" style="color:var(--cloud);">${filtered.length} files</span>
    </div>
    <div style="padding-left:24px;">`;

  filtered.forEach(f => {
    const icon = driveFileIcon(f.mimeType);
    const size = formatSize(f.size);
    html += `
      <div class="tree-node">
        <input type="checkbox" checked style="accent-color:var(--cloud);">
        <span>${icon}</span>
        <span class="name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
        ${size ? `<span class="meta">${size}</span>` : ""}
      </div>`;
  });

  html += `</div>`;
  cloudEl.innerHTML = html;
}

function renderLocalTree(ragStatus) {
  const localEl = document.getElementById("tree-local");
  if (!localEl) return;

  const count = ragStatus?.total_chunks || 0;
  const indexed = ragStatus?.indexed || false;

  if (!indexed) {
    localEl.innerHTML = `
      <div style="text-align:center;padding:40px 20px;">
        <div style="font-size:2rem;margin-bottom:12px;">💻</div>
        <p style="color:var(--text-secondary);margin-bottom:16px;">No local documents indexed yet.</p>
        <button class="btn-primary" style="width:auto;padding:10px 24px;" onclick="ragIngest()">⚡ Index Now</button>
      </div>`;
    return;
  }

  localEl.innerHTML = `
    <div class="tree-node" style="font-weight:600;">
      <input type="checkbox" checked style="accent-color:var(--local);">
      <span>💻</span>
      <span class="name">Local Documents</span>
      <span class="meta" style="color:var(--local);">${count} chunks indexed</span>
    </div>
    <div style="padding-left:24px;">
      <div class="tree-node">
        <input type="checkbox" checked style="accent-color:var(--local);">
        <span>📦</span>
        <span class="name">ChromaDB Vector Store</span>
        <span class="meta" style="color:var(--local);">${count.toLocaleString()} embeddings</span>
      </div>
    </div>`;
}

function consoleLog(msg, type = "info") {
  const el = document.getElementById("sync-console");
  if (!el) return;
  const cls = { ok: "log-ok", warn: "log-warn", info: "log-info", done: "log-ok" }[type] || "log-info";
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

async function updateDriveModal() {
  // Load cloud files
  try {
    const statsRes = await fetch(`${API_BASE}/drive/stats`);
    const stats = await statsRes.json();

    if (!stats.authenticated) {
      renderCloudTree([], null);
      const el = document.getElementById("sync-console");
      if (el) el.innerHTML = `<div class="log-warn">[WARN] Not connected to Google Drive.</div>`;
    } else {
      const filesRes = await fetch(`${API_BASE}/drive/files?pageSize=100`);
      const filesData = await filesRes.json();
      _driveFiles = filesData.files || [];
      const folderName = filesData.folder?.name || stats.folder?.name || "Google Drive";
      renderCloudTree(_driveFiles, folderName);

      const el = document.getElementById("sync-console");
      if (el) {
        el.innerHTML = "";
        consoleLog(`[OK] Connected to Google Drive`, "ok");
        consoleLog(`[INFO] Folder: ${folderName}`, "info");
        consoleLog(`[INFO] ${_driveFiles.length} files in cache`, "info");
        if (stats.synced_at && stats.synced_at !== "Not synced yet") {
          consoleLog(`[OK] Last sync: ${timeAgo(stats.synced_at)}`, "ok");
        } else {
          consoleLog(`[INFO] Not synced yet — click Sync Now`, "info");
        }
      }
    }
  } catch (e) {
    renderCloudTree([], null);
    consoleLog(`[ERROR] ${e.message}`, "warn");
  }

  // Load local/RAG status
  try {
    const ragRes = await fetch(`${API_BASE}/rag/status`);
    const ragData = await ragRes.json();
    renderLocalTree(ragData);
    if (ragData.indexed) {
      consoleLog(`[OK] ChromaDB: ${ragData.total_chunks} embeddings stored`, "ok");
    }
  } catch (_) {
    renderLocalTree(null);
  }

  // Search filtering
  const searchInput = document.getElementById("drive-search-input");
  if (searchInput) {
    searchInput.value = "";
    searchInput.oninput = () => {
      const q = searchInput.value.trim();
      const statsRes2 = fetch(`${API_BASE}/drive/stats`)
        .then(r => r.json())
        .then(s => renderCloudTree(_driveFiles, s.folder?.name || "Google Drive", q))
        .catch(() => {});
    };
  }
}

// ---------------------------------------------------------------------------
// Sync Now — triggers Drive sync then RAG ingest with console output
// ---------------------------------------------------------------------------
async function triggerSync() {
  const btn = document.getElementById("btn-sync-now");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Syncing…"; }

  const el = document.getElementById("sync-console");
  if (el) el.innerHTML = "";

  consoleLog("[INFO] Starting Google Drive sync…", "info");

  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/sync`, { method: "POST" }, 60000);
    const data = await res.json();

    if (data.error) {
      consoleLog(`[ERROR] ${data.error}`, "warn");
    } else {
      consoleLog(`[OK] Drive sync complete — ${data.total} files indexed`, "ok");
      consoleLog(`[INFO] Synced at: ${timeAgo(data.synced_at)}`, "info");
      _driveFiles = [];  // clear cache so tree reloads
      await updateDriveModal();  // reload tree

      // Also start RAG ingest
      consoleLog("[INFO] Starting RAG ingest…", "info");
      try {
        const ingestRes = await fetchWithTimeout(`${API_BASE}/rag/ingest`, { method: "POST" }, 300000);
        const ingestData = await ingestRes.json();
        if (ingestData.error) {
          consoleLog(`[WARN] Ingest: ${ingestData.error}`, "warn");
        } else {
          consoleLog(`[OK] RAG ingest complete — ${ingestData.total_chunks || "?"} chunks`, "ok");
          consoleLog("[DONE] Full sync completed", "ok");
        }
      } catch (ie) {
        consoleLog(`[WARN] Ingest: ${ie.message}`, "warn");
      }
    }
  } catch (e) {
    consoleLog(`[ERROR] Sync failed: ${e.message}`, "warn");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🔄 Sync Now"; }
    updateToolbarContext();
    updateDashboardStats();
  }
}

// Also update toolbar context with file counts
async function updateToolbarContext() {
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
  window.location.href = "/files/#ai-assistant-chat";
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
    if (guard) guard.remove();
    syncSidebarIdentity(false, {});
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
    syncSidebarIdentity(false, {});
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

  syncSidebarIdentity(false, {});

  // Remove auth guard overlay
  if (guard) {
    guard.style.transition = "opacity .3s ease";
    guard.style.opacity = "0";
    setTimeout(() => guard.remove(), 300);
  }

  return true;
}

// ---------------------------------------------------------------------------
// Chat Session Persistence (localStorage)
// ---------------------------------------------------------------------------
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
    div.className = 'message ' + msg.role;
    if (msg.role === 'user') {
      div.innerHTML = `<div class="message-avatar">U</div><div class="message-content">${escapeHtml(msg.text)}</div>`;
    } else {
      div.innerHTML = `<div class="message-avatar">✨</div><div class="message-content"><p>${escapeHtml(msg.text)}</p></div>`;
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

// ---------------------------------------------------------------------------
// Mobile sidebar toggle
// ---------------------------------------------------------------------------
function initMobileToggle() {
  const toggle = document.querySelector(".mobile-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
}

const SIDEBAR_COLLAPSED_KEY = "paiks-sidebar-collapsed";

function initSidebarCollapse() {
  const btn = document.getElementById("sidebar-collapse-toggle");
  const sidebar = document.getElementById("app-sidebar");
  if (!btn || !sidebar) return;

  const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  if (saved) sidebar.classList.add("collapsed");

  btn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebar.classList.contains("collapsed") ? "1" : "0");
    } catch (_) {}
  });
}

// ---------------------------------------------------------------------------
// Modal helpers
// ---------------------------------------------------------------------------
window.openModal = function(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
};
window.closeModal = function(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
};

// ---------------------------------------------------------------------------
// Toolbar — hover expand + click actions
// ---------------------------------------------------------------------------
function initToolbar() {
  const toolbar = document.getElementById("toolbarComponent");
  if (!toolbar) return;

  const tabBtns = toolbar.querySelectorAll(".tab-btn");

  // Hover: expand label of hovered button, collapse others
  tabBtns.forEach(btn => {
    btn.addEventListener("mouseenter", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
  toolbar.addEventListener("mouseleave", () => {
    tabBtns.forEach(b => b.classList.remove("active"));
  });

  // Click actions
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "settings")  { openModal("settings-overlay");  updateSettingsModal(); }
      if (action === "drive")     { openModal("drive-overlay");     updateDriveModal(); }
      if (action === "dashboard") { openModal("dashboard-overlay"); updateDashboardStats(); }
      if (action === "theme")     { toggleTheme(); }
    });
  });

  // Close overlays when clicking backdrop
  document.querySelectorAll(".overlay").forEach(ov => {
    ov.addEventListener("click", e => {
      if (e.target === ov) ov.classList.add("hidden");
    });
  });

  // Drive tabs (cloud / local)
  const driveTabs = document.getElementById("drive-tabs");
  if (driveTabs) {
    driveTabs.querySelectorAll(".pill-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        driveTabs.querySelectorAll(".pill-btn").forEach(b =>
          b.classList.remove("active", "cloud-active", "local-active"));
        btn.classList.add("active");
        if (btn.dataset.tab === "cloud") {
          btn.classList.add("cloud-active");
          document.getElementById("tree-cloud").style.display = "";
          document.getElementById("tree-local").style.display = "none";
        } else {
          btn.classList.add("local-active");
          document.getElementById("tree-cloud").style.display = "none";
          document.getElementById("tree-local").style.display = "";
        }
      });
    });
  }

  // Dashboard filter tabs
  const dashFilter = document.getElementById("dash-filter");
  if (dashFilter) {
    dashFilter.querySelectorAll(".pill-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        dashFilter.querySelectorAll(".pill-btn").forEach(b =>
          b.classList.remove("active", "cloud-active", "local-active"));
        btn.classList.add("active");
        if (btn.dataset.filter === "cloud") btn.classList.add("cloud-active");
        if (btn.dataset.filter === "local") btn.classList.add("local-active");
      });
    });
  }

  // Workspace switching
  document.querySelectorAll(".workspace-item").forEach(ws => {
    ws.addEventListener("click", () => {
      document.querySelectorAll(".workspace-item").forEach(w => w.classList.remove("active"));
      ws.classList.add("active");
    });
  });
}

// ---------------------------------------------------------------------------
// Theme toggle (toolbar button)
// ---------------------------------------------------------------------------
let _isDark = (localStorage.getItem("paiks-theme") || "dark") === "dark";

function toggleTheme() {
  _isDark = !_isDark;
  const theme = _isDark ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("paiks-theme", theme);

  const icon = document.getElementById("theme-icon");
  const label = document.getElementById("theme-label");
  if (icon) {
    icon.innerHTML = _isDark
      ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
      : '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  }
  if (label) label.textContent = _isDark ? "Light Mode" : "Dark Mode";

  // Sync legacy theme toggle buttons
  document.querySelectorAll(".theme-toggle-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-theme") === theme);
  });
}

// ---------------------------------------------------------------------------
// New chat input (files page — #chat-input textarea)
// ---------------------------------------------------------------------------
function initNewChatInput() {
  const chatInput = document.getElementById("chat-input");
  const btnSend   = document.getElementById("btn-send");
  const emptyState  = document.getElementById("empty-state");
  const chatMessages = document.getElementById("chat-messages");
  const chatThread   = document.getElementById("chat-thread");
  if (!chatInput || !btnSend) return;

  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
    btnSend.disabled = chatInput.value.trim().length === 0;
  });

  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleNewSend();
    }
  });
  btnSend.addEventListener("click", handleNewSend);

  function handleNewSend() {
    const text = chatInput.value.trim();
    if (!text) return;
    if (emptyState && !emptyState.classList.contains("hidden")) {
      emptyState.classList.add("hidden");
    }

    // Create session on first message
    if (!_activeSid) {
      sessionCreate(text);
      renderHistoryList();
    }
    sessionAddMessage('user', text);

    // Append user message
    const userDiv = document.createElement("div");
    userDiv.className = "message user";
    userDiv.innerHTML = `<div class="message-avatar">U</div><div class="message-content">${escapeHtml(text)}</div>`;
    chatMessages.appendChild(userDiv);

    chatInput.value = "";
    chatInput.style.height = "auto";
    btnSend.disabled = true;
    chatThread.scrollTop = chatThread.scrollHeight;

    // Typing indicator
    const typingId = "typing-" + Date.now();
    const typingDiv = document.createElement("div");
    typingDiv.id = typingId;
    typingDiv.className = "message ai";
    typingDiv.innerHTML = `<div class="message-avatar">✨</div><div class="message-content"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
    chatMessages.appendChild(typingDiv);
    chatThread.scrollTop = chatThread.scrollHeight;

    // Fire actual RAG call then replace typing indicator
    (async () => {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/rag/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: text, top_k: 5 }),
        }, 300000);
        const data = await res.json();
        const el = document.getElementById(typingId);
        if (el) el.remove();

        const aiDiv = document.createElement("div");
        aiDiv.className = "message ai";
        const answer = data.answer || data.error || "No response.";
        aiDiv.innerHTML = `<div class="message-avatar">✨</div><div class="message-content"><p>${escapeHtml(answer)}</p></div>`;
        chatMessages.appendChild(aiDiv);
        sessionAddMessage('ai', answer);
        renderHistoryList();
        chatThread.scrollTop = chatThread.scrollHeight;
      } catch (err) {
        const el = document.getElementById(typingId);
        if (el) el.remove();
        const errDiv = document.createElement("div");
        errDiv.className = "message ai";
        errDiv.innerHTML = `<div class="message-avatar">✨</div><div class="message-content"><p style="color:var(--color-error)">Error: ${escapeHtml(err.message)}</p></div>`;
        chatMessages.appendChild(errDiv);
        chatThread.scrollTop = chatThread.scrollHeight;
      }
    })();
  }
}

// Suggestion card helper
window.setInput = function(val) {
  const chatInput = document.getElementById("chat-input");
  if (!chatInput) return;
  chatInput.value = val;
  chatInput.dispatchEvent(new Event("input"));
  chatInput.focus();
};

// ---------------------------------------------------------------------------
// Init on page load
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  initMobileToggle();
  initSidebarCollapse();
  initToolbar();
  initNewChatInput();

  // Chat history sidebar
  renderHistoryList();
  const newChatBtn = document.querySelector(".btn-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", e => {
      e.preventDefault();
      startNewChat();
    });
  }

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
  if (document.getElementById("chat-thread")) {
    loadRagStatus();
    loadLLMStatus();
    updateDashboardStats();
    updateToolbarContext();
    updateSettingsModal();
  }

  if (document.getElementById("files-container")) {
    loadFiles();
    loadRagStatus();
    loadLLMStatus();
    if (window.location.hash === "#ai-assistant-chat") {
      requestAnimationFrame(() => {
        const chat = document.getElementById("ai-assistant-chat");
        if (chat) chat.scrollIntoView({ behavior: "smooth", block: "start" });
        const rag = document.getElementById("rag-input");
        if (rag) setTimeout(() => rag.focus(), 400);
      });
    }
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
