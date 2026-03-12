/* =========================================================================
   PAIKS – Client-side JavaScript
   ========================================================================= */

const API_BASE = "http://127.0.0.1:5001";

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
      const res = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
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
      resultsContainer.innerHTML = `<p class="text-muted mt-sm">Search failed: ${err.message}</p>`;
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
  if (document.getElementById("files-container")) loadFiles();

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
