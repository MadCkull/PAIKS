let _driveFiles = [];
let _localTree  = null;
let _activeTab  = "cloud";
let _selections = { selected: [], disabled: [], errors: [], synced: [] };

const SUPPORTED_EXTS = ["pdf", "csv", "xlsx", "xls", "ppt", "pptx", "png", "jpg", "jpeg", "webp", "py", "md", "txt", "doc", "docx"];

function isSupportedFile(node, name) {
  if (node.type === "dir" || (node.mimeType && node.mimeType.includes("folder"))) return true;
  const ext = name.split('.').pop().toLowerCase();
  if (SUPPORTED_EXTS.includes(ext)) return true;
  if (node.mimeType) {
    if (node.mimeType.includes("text") || node.mimeType.includes("pdf") || node.mimeType.includes("document")) return true;
  }
  return false;
}

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

// ── Helpers ─────────────────────────────────────────────────────
function _getFileId(node, source) {
  if (source === "local") return node.id || `local__${node.path || node.local_path || node.name || ""}`;
  return `cloud__${node.id}`;
}

function _isDir(node) {
  return node.type === "dir" || (node.mimeType && node.mimeType.includes("folder"));
}

function _isFileChecked(fileId) {
  return !_selections.disabled.includes(fileId);
}

function _hasError(fileId) {
  return _selections.errors.includes(fileId);
}

function _isSynced(fileId) {
  return _selections.synced.includes(fileId);
}

// ── Tree Rendering ─────────────────────────────────────────────
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
    const isDir = _isDir(node);
    const name  = node.name || "Untitled";

    if (query && !isRoot) {
      const match = name.toLowerCase().includes(query.toLowerCase());
      if (!match && (!node.children || node.children.length === 0)) return "";
    }

    const icon = isDir ? "📁" : driveFileIcon(node.mimeType, name);
    const isSupported = isSupportedFile(node, name);

    let childHtml = "";
    if (node.children && node.children.length > 0) {
      childHtml = node.children.map(c => buildHtml(c)).join("");
    } else if (source === "cloud" && isRoot && Array.isArray(node.files)) {
      childHtml = node.files.map(f => buildHtml({...f, type: "file"})).join("");
    }

    if (query && isDir && !childHtml && !isRoot) return "";

    const fileId = _getFileId(node, source);
    const isChecked = isSupported && _isFileChecked(fileId);
    const hasError = _hasError(fileId);
    const isSynced = !isDir && _isSynced(fileId);
    const disabledAttr = !isSupported ? "disabled" : "";
    const opac = !isSupported ? "opacity:0.35; pointer-events:none;" : "";

    // Status indicator for files
    let statusIcon = "";
    if (!isDir && isSupported && isChecked && hasError) {
      statusIcon = `<i class="status-icon fas fa-exclamation-circle" style="color:#fb923c;font-size:0.7rem;margin-left:6px;" title="Indexing failed"></i>`;
    }

    const checkboxHtml = `
      <input type="checkbox" class="paiks-cb" ${isChecked ? "checked" : ""} ${disabledAttr}
             data-id="${escapeHtml(fileId)}" data-isdir="${isDir}" data-source="${source}"
             onchange="toggleSelection(this)">
    `;

    // ── Root node: separated header card ──
    if (isRoot) {
      return `
        <div class="tree-root-header">
          ${checkboxHtml}
          <span class="tree-root-icon">${icon}</span>
          <span class="tree-root-name">${escapeHtml(name)}</span>
        </div>
        <div class="tree-body">${childHtml}</div>
      `;
    }

    // ── Directory node ──
    if (isDir) {
      // Use btoa unconditionally to safely persist states regardless of special path characters
      let safeKey = "open_folder";
      try { safeKey = "open_" + btoa(unescape(encodeURIComponent(fileId))).replace(/=/g, ''); } catch(e) {}
      const openState = localStorage.getItem(safeKey) === "true" ? "open" : "";
      
      return `
        <details class="tree-details" ${openState} ontoggle="localStorage.setItem('${safeKey}', this.open)">
          <summary class="tree-node tree-node-dir" style="${opac}">
            ${checkboxHtml}
            <span class="tree-icon">${icon}</span>
            <span class="tree-name">${escapeHtml(name)}</span>
          </summary>
          <div class="tree-children">
            ${childHtml}
          </div>
        </details>
      `;
    }

    // ── File node ──
    return `
      <div class="tree-node tree-node-file" style="${opac}">
        ${checkboxHtml}
        <span class="tree-icon">${icon}</span>
        <span class="tree-name">${escapeHtml(name)}</span>
        ${statusIcon}
        ${node.size ? `<span class="tree-meta">${formatSize(node.size)}</span>` : ""}
        ${!isSupported ? `<span class="tree-meta" style="color:#f87171;">(Unsupported)</span>` : ""}
      </div>
    `;
  }

  let rootNode = treeData;
  if (Array.isArray(treeData)) {
    rootNode = { name: "Google Drive", type: "dir", children: treeData };
  }

  container.innerHTML = buildHtml(rootNode, true);

  // After rendering, compute folder indeterminate states
  _updateAllFolderStates(container);
}

// ── Three-state folder checkbox logic ──────────────────────────
function _updateAllFolderStates(container) {
  // Walk all <details> elements bottom-up
  const allDetails = Array.from(container.querySelectorAll('.tree-details'));
  // Reverse so we process deepest folders first
  allDetails.reverse().forEach(det => {
    const folderCb = det.querySelector(':scope > summary > .paiks-cb');
    if (!folderCb) return;
    _computeFolderState(folderCb);
  });
  // Also handle root checkbox
  const rootCb = container.querySelector('.tree-root-header > .paiks-cb');
  if (rootCb) _computeFolderState(rootCb);
}

function _computeFolderState(folderCb) {
  // Find the children container
  let childContainer;
  const rootHeader = folderCb.closest('.tree-root-header');
  if (rootHeader) {
    childContainer = rootHeader.nextElementSibling; // .tree-body
  } else {
    const details = folderCb.closest('.tree-details');
    if (details) childContainer = details.querySelector('.tree-children');
  }
  if (!childContainer) return;

  const childCbs = childContainer.querySelectorAll('.paiks-cb:not([disabled])');
  if (childCbs.length === 0) return;

  let checkedCount = 0;
  let totalCount = 0;
  childCbs.forEach(cb => {
    totalCount++;
    if (cb.checked) checkedCount++;
  });

  if (checkedCount === 0) {
    folderCb.checked = false;
    folderCb.indeterminate = false;
  } else if (checkedCount === totalCount) {
    folderCb.checked = true;
    folderCb.indeterminate = false;
  } else {
    folderCb.checked = false;
    folderCb.indeterminate = true;
  }
}

// ── Background Data Preloading ─────────────────────────────────
let _bgPreloadPromise = null;

window.revalidateFileTree = async function() {
  _bgPreloadPromise = null; // Invalidate cache
  await window.preloadDriveBackground();
  
  // If the drive modal is open, silently redraw it
  const modal = document.getElementById("drive-modal-overlay");
  if (modal && !modal.classList.contains("hidden")) {
      window.updateDriveModal(); // Will draw immediately because preloadDriveBackground just finished
  }
};

window.preloadDriveBackground = function() {
  if (_bgPreloadPromise) return _bgPreloadPromise;
  
  _bgPreloadPromise = (async () => {
    const localMode = localStorage.getItem("paiks-mode") === "local";
    let settings = {}, stats = {};
    
    try {
      const [sRes, setRes, stRes] = await Promise.all([
        fetchWithTimeout(`${API_BASE}/drive/selections`, {}, 5000).catch(()=>({ json:()=>({selected:[],disabled:[],errors:[],synced:[]}) })),
        fetchWithTimeout(`${API_BASE}/system/settings`, {}, 5000).catch(()=>({ json:()=>({}) })),
        fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000).catch(()=>({ json:()=>({}) }))
      ]);
      _selections = await sRes.json();
      if (!_selections.errors) _selections.errors = [];
      if (!_selections.synced) _selections.synced = [];
      settings = await setRes.json();
      stats = await stRes.json();
      
      const fetchPromises = [];
      if (!localMode && stats.authenticated && settings.cloud_enabled) {
        fetchPromises.push(
          fetchWithTimeout(`${API_BASE}/drive/files?pageSize=100`, {}, 10000)
          .then(r => r.json())
          .then(data => {
            _driveFiles = data.files || [];
            _activeRootCloudName = data.folder?.name || stats.folder?.name || "Google Drive";
          }).catch(()=>{})
        );
      }
      if (settings.local_enabled && settings.local_root_path) {
        fetchPromises.push(
          fetchWithTimeout(`${API_BASE}/local/tree`, {}, 10000)
          .then(r => r.json())
          .then(data => { _localTree = data; }).catch(()=>{})
        );
      }
      await Promise.all(fetchPromises);
    } catch(e) {}
  })();
  return _bgPreloadPromise;
};

let _activeRootCloudName = "Google Drive";

window.updateDriveModal = async function() {
  const searchInput = document.getElementById("drive-search-input");
  const query = searchInput ? searchInput.value.trim() : "";
  const localMode = localStorage.getItem("paiks-mode") === "local";

  // Guarantee preloads are finished
  await window.preloadDriveBackground();

  // Render instantly from memory caches
  if (_driveFiles.length > 0) {
    renderTree("tree-cloud", { name: _activeRootCloudName, type: "dir", children: _driveFiles }, query, "cloud");
  } else {
    renderTree("tree-cloud", null, "", "cloud");
    if (localMode) {
       const localTab = document.querySelector('#drive-tabs [data-tab="local"]');
       if (localTab) localTab.click();
    }
  }

  if (_localTree) {
    renderTree("tree-local", _localTree, query, "local");
  } else {
    renderTree("tree-local", null, "", "local");
  }

  

  // Background silent refresh of selections to ensure accuracy if modified externally
  fetchWithTimeout(`${API_BASE}/drive/selections`, {}, 5000)
    .then(r => r.json())
    .then(data => {
       _selections = data;
       if (!_selections.errors) _selections.errors = [];
       if (!_selections.synced) _selections.synced = [];
    }).catch(()=>{});
};

document.addEventListener("DOMContentLoaded", () => {
  preloadDriveBackground(); // Kicks off loading the trees the second the app opens

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

// ── SSE & Real-time Log Console ────────────────────────────────
let _eventSource = null;

window.openLogConsole = async function() {
    const con = document.getElementById("drive-log-console");
    if(con) {
        con.classList.remove("hidden");
        try {
            const res = await fetchWithTimeout(`${API_BASE}/system/logs`, {}, 5000);
            const data = await res.json();
            const logBody = document.getElementById("drive-log-body");
            if (logBody) {
                logBody.innerHTML = (data.logs || []).map(line => {
                    let color = "#a0aec0";
                    let msg = line;
                    let timeStr = "";
                    const match = line.match(/^\[(.*?)\] (.*?): (.*)$/);
                    if (match) {
                        timeStr = match[1];
                        const lvl = match[2].toLowerCase();
                        msg = match[3];
                        if (lvl.includes("error") || lvl.includes("critical")) color = "#f87171";
                        else if (lvl.includes("warn")) color = "#fbbf24";
                        else if (msg.toLowerCase().includes("indexed") || msg.toLowerCase().includes("removed") || msg.toLowerCase().includes("deleted")) color = "#34d399";
                    }
                    return `<div style="color:${color}; margin-bottom:5px; line-height:1.4; cursor:default;" title="${timeStr}">${escapeHtml(msg)}</div>`;
                }).join("");
                logBody.scrollTop = logBody.scrollHeight;
            }
        } catch(e) { }
    }
};

window.closeLogConsole = function() {
    const con = document.getElementById("drive-log-console");
    if(con) con.classList.add("hidden");
};

window.clearLogs = async function() {
    try {
        await fetch(`${API_BASE}/system/logs`, { method: "POST", headers: {"X-CSRFToken": getCsrfToken()} });
        const logBody = document.getElementById("drive-log-body");
        if(logBody) logBody.innerHTML = "";
    } catch(e) {}
};

// ── Badge System ───────────────────────────────────────────────
let _badgeTimer = null;
let _currentBadgeState = "synced";

function setBadge(state) {
    const badges = document.getElementById("drive-badges");
    if (!badges) return;

    if (_badgeTimer) clearTimeout(_badgeTimer);

    const applyBadge = (s) => {
        _currentBadgeState = s;
        let html = "";
        if (s === "syncing") {
            html = `<div class="badge badge-syncing" onclick="openLogConsole()"><i class="fas fa-sync-alt fa-spin"></i> SYNCING</div>`;
        } else if (s === "synced") {
            html = `<div class="badge badge-success" onclick="openLogConsole()"><i class="fas fa-check-circle"></i> SYNCED</div>`;
        } else if (s === "warning") {
            html = `<div class="badge badge-warning" onclick="openLogConsole()"><i class="fas fa-exclamation-circle"></i> SYNCED</div>`;
        } else if (s === "error") {
            html = `<div class="badge badge-error" onclick="openLogConsole()"><i class="fas fa-times-circle"></i> ERROR</div>`;
        }
        badges.innerHTML = html;
    };

    if (state !== "syncing" && _currentBadgeState === "syncing") {
        _badgeTimer = setTimeout(() => applyBadge(state), 700);
    } else {
        applyBadge(state);
    }
}

function _registerDriveSSEHandlers() {
  if (typeof PAIKSEventBus === "undefined") return;

  PAIKSEventBus.on("system_health", function(data) {
      setBadge(data.state);
  });

  // Revalidate the DOM silently when backend stats actively change
  PAIKSEventBus.on("drive_stats", function(data) {
      if (typeof window.revalidateFileTree === "function") {
          window.revalidateFileTree();
      }
  });

  PAIKSEventBus.on("sync_update", function(data) {
      if (data.status === "syncing") {
         setBadge("syncing");
      }
      
      // Dynamically inject/remove error icons in tree without full re-render
      if (data.file_id) {
         const safeId = data.file_id.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
         const cb = document.querySelector(`.paiks-cb[data-id="${safeId}"]`);
         if (cb) {
            const nodeFile = cb.closest('.tree-node-file');
            if (nodeFile) {
               let icon = nodeFile.querySelector('.status-icon');
               if (data.status === "error") {
                   if (!icon) {
                       icon = document.createElement("i");
                       icon.className = "status-icon fas fa-exclamation-circle";
                       icon.style.cssText = "color:#fb923c;font-size:0.7rem;margin-left:6px;";
                       icon.title = "Indexing failed";
                       const meta = nodeFile.querySelector('.tree-meta');
                       if (meta) { nodeFile.insertBefore(icon, meta); } 
                       else { nodeFile.appendChild(icon); }
                   }
               } else {
                   if (icon) icon.remove();
               }
            }
         }
      }
  });

  PAIKSEventBus.on("system_log", function(data) {
      const logBody = document.getElementById("drive-log-body");
      if (logBody) {
          const div = document.createElement("div");
          let color = "#a0aec0";
          if (data.level === "success") color = "#34d399";
          else if (data.level === "warning") color = "#fbbf24";
          else if (data.level === "error") color = "#f87171";
          div.style.cssText = `color:${color}; margin-bottom:5px; line-height:1.4; cursor:default;`;
          div.title = data.time || "";
          div.textContent = data.msg;
          logBody.appendChild(div);
          logBody.scrollTop = logBody.scrollHeight;
      }
  });
}

// Register them once on load
_registerDriveSSEHandlers();

// ── Selection Toggle (Professional three-state system) ─────────

window.toggleSelection = async function(checkboxEl) {
  const isSelected = checkboxEl.checked;
  const isDir = checkboxEl.getAttribute("data-isdir") === "true";

  // Collect ONLY actual file IDs (never directories)
  let idsToUpdate = [];

  if (!isDir) {
    idsToUpdate.push(checkboxEl.getAttribute("data-id"));
  }

  if (isDir) {
    // Find child container
    let childContainer;
    const rootHeader = checkboxEl.closest('.tree-root-header');
    if (rootHeader) {
      childContainer = rootHeader.nextElementSibling;
    } else {
      const detailsTag = checkboxEl.closest('.tree-details');
      if (detailsTag) childContainer = detailsTag.querySelector('.tree-children');
    }

    if (childContainer) {
      const childCBs = childContainer.querySelectorAll('.paiks-cb:not([disabled])');
      childCBs.forEach(cb => {
        cb.checked = isSelected;
        cb.indeterminate = false;
        if (cb.getAttribute("data-isdir") !== "true") {
          idsToUpdate.push(cb.getAttribute("data-id"));
        }
      });
    }
  }

  // Propagate upward: update ALL parent folder checkboxes
  _propagateUp(checkboxEl);

  if (idsToUpdate.length === 0) return;

  // Update local cache
  if (isSelected) {
    _selections.disabled = _selections.disabled.filter(id => !idsToUpdate.includes(id));
  } else {
    idsToUpdate.forEach(id => {
      if (!_selections.disabled.includes(id)) _selections.disabled.push(id);
    });
  }

  try {
    setBadge("syncing");
    await fetchWithTimeout(`${API_BASE}/drive/selection`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      body: JSON.stringify({ file_ids: idsToUpdate, is_selected: isSelected })
    });
    // Dashboard stats will be updated automatically via SSE broadcast from the backend
  } catch(e) {
    console.error("Selection failed", e);
    setBadge("error");
  }
};

function _propagateUp(checkboxEl) {
  // Walk up the DOM to find parent folder checkboxes and recompute their state
  let currentEl = checkboxEl;
  while (currentEl) {
    // Find the parent tree-children container
    const parentChildren = currentEl.closest('.tree-children') || currentEl.closest('.tree-body');
    if (!parentChildren) break;

    // Find the parent folder's checkbox
    let parentCb = null;
    const parentDetails = parentChildren.closest('.tree-details');
    if (parentDetails) {
      parentCb = parentDetails.querySelector(':scope > summary > .paiks-cb');
    } else {
      // We're inside .tree-body → parent is root header
      const treeView = parentChildren.closest('.tree-view');
      if (treeView) parentCb = treeView.querySelector('.tree-root-header > .paiks-cb');
    }

    if (!parentCb) break;

    _computeFolderState(parentCb);
    currentEl = parentCb;
  }
}

// ── File List (legacy grid view) ───────────────────────────────
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
