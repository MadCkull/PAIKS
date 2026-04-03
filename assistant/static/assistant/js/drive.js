let _driveFiles = [];
let _ragFiles   = [];

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

function localFileIcon(ext) {
  const map = { ".pdf": "📄", ".docx": "📝", ".doc": "📝", ".txt": "📃", ".md": "📃", ".csv": "📊" };
  return map[ext] || "📎";
}

function renderLocalFileList(files) {
  const el = document.getElementById("local-file-list");
  if (!el) return;
  if (!files || !files.length) {
    el.innerHTML = `<p style="font-size:.82rem;color:var(--text-dim);text-align:center;padding:12px 0;">No local files uploaded yet.</p>`;
    return;
  }
  el.innerHTML = files.map(f => `
    <div class="local-file-item">
      <span class="lf-icon">${localFileIcon(f.ext || "")}</span>
      <div class="lf-info">
        <div class="lf-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
        <div class="lf-meta">${formatSize(f.size || 0)} · ${f.chunks || 0} chunks · ${timeAgo(f.uploaded_at)}</div>
      </div>
      <button class="lf-del" title="Delete" onclick="deleteLocalFile('${f.id}')">🗑</button>
    </div>
  `).join("");
}

async function loadLocalFiles() {
  try {
    const res = await fetch(`${API_BASE}/local/files`);
    const data = await res.json();
    renderLocalFileList(data.files || []);
    return data.files || [];
  } catch (_) {
    renderLocalFileList([]);
    return [];
  }
}

window.deleteLocalFile = async function(fileId) {
  if (!confirm("Remove this file and its indexed chunks?")) return;
  try {
    const res = await fetch(`${API_BASE}/local/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: fileId }),
    });
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    showToast("File removed", "info");
    consoleLog(`[OK] Deleted: ${fileId.replace("local__", "")}`, "ok");
    loadLocalFiles();
  } catch (err) {
    showToast("Delete failed: " + err.message, "error");
  }
};

async function uploadLocalFiles(fileList) {
  if (!fileList || !fileList.length) return;

  const progressBar   = document.getElementById("local-upload-bar");
  const progressWrap  = document.getElementById("local-upload-progress");
  const progressLabel = document.getElementById("local-upload-label");

  if (progressWrap) progressWrap.style.display = "";
  if (progressBar)  progressBar.style.width = "10%";
  if (progressLabel) progressLabel.textContent = `Uploading ${fileList.length} file(s)…`;

  const formData = new FormData();
  Array.from(fileList).forEach(f => formData.append("files", f));

  consoleLog(`[INFO] Uploading ${fileList.length} file(s)…`, "info");

  try {
    if (progressBar) progressBar.style.width = "40%";
    const res = await fetch(`${API_BASE}/local/upload`, { method: "POST", body: formData });
    if (progressBar) progressBar.style.width = "80%";
    const data = await res.json();

    if (data.error) {
      consoleLog(`[ERROR] ${data.error}`, "warn");
      showToast(data.error, "error");
      return;
    }

    (data.results || []).forEach(r => {
      if (r.status === "indexed")  consoleLog(`[OK] ${r.name} — ${r.chunks} chunks`, "ok");
      else if (r.status === "error")  consoleLog(`[WARN] ${r.name}: ${r.reason}`, "warn");
      else consoleLog(`[INFO] ${r.name}: ${r.reason || r.status}`, "info");
    });

    const indexed = (data.results || []).filter(r => r.status === "indexed").length;
    if (indexed) showToast(`${indexed} file(s) indexed successfully`, "success");

    if (progressBar) progressBar.style.width = "100%";
    if (progressLabel) progressLabel.textContent = `Done — ${indexed} file(s) indexed`;
    await loadLocalFiles();
  } catch (err) {
    consoleLog(`[ERROR] Upload failed: ${err.message}`, "warn");
    showToast("Upload failed: " + err.message, "error");
  } finally {
    setTimeout(() => {
      if (progressWrap) progressWrap.style.display = "none";
      if (progressBar)  progressBar.style.width = "0%";
    }, 2000);
  }
}

function initLocalDropZone() {
  const zone  = document.getElementById("local-drop-zone");
  const input = document.getElementById("local-file-input");
  if (!zone || !input) return;

  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files.length) uploadLocalFiles(input.files);
    input.value = "";
  });

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length) uploadLocalFiles(e.dataTransfer.files);
  });
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

window.updateDriveModal = async function() {
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

  loadLocalFiles();
  initLocalDropZone();
  try {
    const ragRes = await fetch(`${API_BASE}/rag/status`);
    const ragData = await ragRes.json();
    if (ragData.indexed) {
      consoleLog(`[OK] ChromaDB: ${ragData.total_chunks} total embeddings`, "ok");
    }
  } catch (_) {}

  const searchInput = document.getElementById("drive-search-input");
  if (searchInput) {
    searchInput.value = "";
    searchInput.oninput = () => {
      const q = searchInput.value.trim();
      fetch(`${API_BASE}/drive/stats`)
        .then(r => r.json())
        .then(s => renderCloudTree(_driveFiles, s.folder?.name || "Google Drive", q))
        .catch(() => {});
    };
  }
}

window.triggerSync = async function() {
  const btn = document.getElementById("btn-sync-now") || document.getElementById("btn-sync");
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
      _driveFiles = [];
      await updateDriveModal();

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
    if(typeof updateToolbarContext === 'function') updateToolbarContext();
    if(typeof updateDashboardStats === 'function') updateDashboardStats();
  }
}

window.loadFiles = async function(query = "") {
  const container = document.getElementById("files-container");
  if (!container) return;

  container.innerHTML = Array(6)
    .fill('<div class="skeleton skeleton-block" style="height:80px"></div>')
    .join("");

  try {
    const url = new URL(window.location.origin + `${API_BASE}/drive/files`);
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

window.openFolderPicker = function() {
  const existing = document.getElementById("folder-picker-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "folder-picker-modal";
  modal.className = "folder-picker-modal-container";
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
      <div class="modal-search-row" style="padding:16px;">
        <input id="folder-filter-input" class="search-input input" placeholder="Filter folders…" autocomplete="off" style="width:100%" />
      </div>
      <div id="folder-list" class="folder-list" style="max-height: 400px; overflow-y: auto; padding: 0 16px;">
        <div class="flex-center mt-md"><div class="spinner"></div></div>
      </div>
      <div class="modal-footer" style="padding:16px;">
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
      <button class="folder-item btn btn-outline" style="width:100%; text-align:left; justify-content:flex-start; margin-bottom:8px;" data-id="${escapeHtml(f.id)}" data-name="${escapeHtml(f.name)}">
        <span class="folder-item-icon" style="margin-right:8px;">📁</span>
        <span class="folder-item-name">${escapeHtml(f.name)}</span>
      </button>`).join("");

    list.querySelectorAll(".folder-item").forEach(btn => {
      btn.addEventListener("click", () => {
        selectFolder(btn.dataset.id, btn.dataset.name);
        closeModal();
      });
    });
  };

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

      if (data.current_folder?.folder_id) {
        setTimeout(() => {
          const active = document.querySelector(`.folder-item[data-id="${data.current_folder.folder_id}"]`);
          if (active) {
            active.style.border = "2px solid var(--accent)";
            active.scrollIntoView({ block: "nearest" });
          }
        }, 50);
      }
    })
    .catch(err => {
      document.getElementById("folder-list").innerHTML =
        `<p class="text-muted" style="padding:12px 0;">Failed to load folders: ${err.message}</p>`;
    });

  document.getElementById("folder-filter-input").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    renderFolders(q ? allFolders.filter(f => f.name.toLowerCase().includes(q)) : allFolders);
  });

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
    if(typeof updateDriveModal === 'function') updateDriveModal();
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
    if(typeof updateDriveModal === 'function') updateDriveModal();
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
  
  if(typeof updateSettingsModal === 'function') updateSettingsModal();
}

window.loadFolderBadge = async function() {
  try {
    const res = await fetch(`${API_BASE}/drive/folder-config`);
    const data = await res.json();
    updateFolderBadge(data?.folder_id ? data : null);
  } catch {
    updateFolderBadge(null);
  }
}
