let _pickerCurrentPath = "This PC";
let _pickerSelectedPath = null;
let _pickerSource = "local"; // 'local' or 'drive'
let _settingsAutosaveTimer = null;
let _isInitializingSettings = false;

/* ── Tab Switching ───────────────────────────────────────────── */
window.switchSettingsTab = function(btn, tabId) {
  document.querySelectorAll(".sm-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  btn.classList.add("active");
  const panel = document.getElementById("tab-" + tabId);
  if (panel) panel.classList.add("active");
};

/* ── Autosave badge & Persistence ────────────────────────────── */
window.settingsTriggerAutosave = function() {
  if (_isInitializingSettings) return;
  clearTimeout(_settingsAutosaveTimer);
  _settingsAutosaveTimer = setTimeout(async () => {
    // 1. Show Visual Feedback
    const badge = document.getElementById("autosave-badge");
    if (badge) {
       badge.classList.add("show");
       setTimeout(() => badge.classList.remove("show"), 2000);
    }

    // 2. Gather Data for Persistence (Nested Structure)
    const data = {
      general: {
        system_prompt: document.getElementById("system-prompt")?.value || "",
        context_memory_limit: parseInt(document.getElementById("ctx-slider")?.value || 6),
        accent_color: document.querySelector(".accent-swatch.active")?.dataset.accent || "purple"
      },
      sources: {
        cloud_enabled: document.getElementById("toggle-cloud")?.checked || false,
        local_enabled: document.getElementById("toggle-local")?.checked || false
      },
      rag: {
        chunk_size: parseInt(document.getElementById("chunk-size")?.value || 512),
        chunk_overlap: parseInt(document.getElementById("chunk-overlap")?.value || 64),
        top_k: parseInt(document.getElementById("topk")?.value || 30),
        top_n: parseInt(document.getElementById("topn")?.value || 5),
        rerank_enabled: document.getElementById("rerank-toggle")?.checked || false,
        auto_summarise: document.getElementById("auto-summarise-toggle")?.checked || false
      },
      models: {
        cloud_llm_enabled: document.getElementById("toggle-cloud-llm")?.checked || false,
        cloud_provider: document.getElementById("cloud-llm-provider")?.value || "Google Gemini",
        cloud_key: document.getElementById("cloud-llm-key")?.value || "",
        cloud_model: document.getElementById("cloud-llm-model")?.value || "gemini-1.5-pro",
        embed_model: document.getElementById("embed-model-select")?.value || "nomic-embed-text"
      },
      data: {
        sync_interval: document.getElementById("sync-interval-select")?.value || "30"
      }
    };

    // 3. POST to Backend & Update Cache
    try {
      const res = await fetch(`${API_BASE}/system/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        body: JSON.stringify(data)
      });
      const resJson = await res.json();
      
      // Mutate local cache mapped to backend response
      window.appSettings = resJson.settings || window.appSettings;
      
      // Trigger Drive sync
      if (typeof window.revalidateFileTree === "function") window.revalidateFileTree();
      
    } catch (err) {
      console.error("Autosave failed:", err);
    }
  }, 800);
};

/* ── Slider label updater ────────────────────────────────────── */
window.settingsUpdateSlider = function(el, outId, suffix) {
  const out = document.getElementById(outId);
  if (out) out.textContent = el.value + suffix;
  settingsTriggerAutosave();
};

/* ── Chunk preview ───────────────────────────────────────────── */
window.updateChunkPreview = function() {
  const cs = document.getElementById("chunk-size")?.value || 512;
  const co = document.getElementById("chunk-overlap")?.value || 64;
  const ps = document.getElementById("preview-size");
  const po = document.getElementById("preview-overlap");
  if (ps) ps.textContent = cs + " tokens";
  if (po) po.textContent = co + " tokens";
};

/* ── Inline confirm expand ───────────────────────────────────── */
window.settingsToggleConfirm = function(id) {
  const el = document.getElementById("confirm-" + id);
  if (el) el.classList.toggle("open");
};
window.settingsExecClear = async function(id) {
  const labels = { 
    mirror: "App cache wiped & reloading...", 
    chat: "Chat history deleted", 
    db: "Vector database wiped" 
  };
  
  const endpoints = {
    mirror: "/system/clear-cache",
    chat: "/chat/clear-all",
    db: "/rag/wipe-db"
  };

  try {
    const res = await fetch(`${API_BASE}${endpoints[id]}`, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() }
    });
    const data = await res.json();
    
    if (data.error) throw new Error(data.error);

    showToast(labels[id] || "Done", "success");
    
    // UI specific post-cleanup
    if (id === "chat") {
      try {
        localStorage.removeItem("paiks-sessions");
        if (typeof renderHistoryList === "function") renderHistoryList();
      } catch(_) {}
    }

    if (id === "mirror") {
      // Powerful browser reset
      try {
        localStorage.clear();
        sessionStorage.clear();
        // Clear CacheStorage if browser supports it
        if ('caches' in window) {
          const names = await caches.keys();
          await Promise.all(names.map(name => caches.delete(name)));
        }
      } catch(_) {}
      
      // Reload for fresh start
      setTimeout(() => window.location.reload(), 1500);
    }
    
    if (id === "db") {
       // Update dashboard metrics if possible
       if (typeof window.updateSettingsModal === "function") updateSettingsModal();
    }

    settingsToggleConfirm(id); // close prompt
  } catch (err) {
    showToast(`Cleanup failed: ${err.message}`, "error");
  }
};

/* ── Universal Folder Picker ─────────────────────────────────── */
let _pickerNavStack = []; // navigation history for back button
let _driveChildrenCache = {}; // { parentId: [folder objects] } — avoids re-fetching

window.openUniversalPicker = function(source) {
  _pickerSource = source;
  _pickerSelectedPath = null;
  _pickerNavStack = [];
  _driveChildrenCache = {};
  
  // Hide popover if open
  closeFolderPrompt(source === "drive" ? "drive" : "local");

  const overlay = document.getElementById("local-picker-overlay");
  const title   = document.getElementById("picker-modal-title");
  const confirm = document.getElementById("btn-confirm-picker");
  const backBtn = document.getElementById("picker-back-btn");
  if (title) title.textContent = source === "drive" ? "☁ Select Google Drive Folder" : "📁 Select Local Root Folder";
  if (confirm) confirm.disabled = true;
  if (backBtn) backBtn.style.display = "none";
  if (overlay) overlay.classList.remove("hidden");
  if (source === "drive") {
    _loadDriveFolders(null); // show root entry points
  } else {
    _pickerNavStack = [];
    browseLocalPath("This PC");
  }
};

window.pickerGoBack = function() {
  if (_pickerSource === "drive") {
    if (_pickerNavStack.length > 0) {
      _pickerNavStack.pop(); // remove current
      const prev = _pickerNavStack.length > 0 ? _pickerNavStack[_pickerNavStack.length - 1] : null;
      _loadDriveFolders(prev ? prev.id : null, true); // true = skip push
    }
  } else {
    // Local: go up by trimming path
    if (_pickerNavStack.length > 0) {
      _pickerNavStack.pop();
      const prev = _pickerNavStack.length > 0 ? _pickerNavStack[_pickerNavStack.length - 1] : "This PC";
      browseLocalPath(typeof prev === "string" ? prev : prev.path || "This PC", true);
    }
  }
};

window.confirmUniversalPicker = function() {
  if (!_pickerSelectedPath) return;
  const source = _pickerSource;
  if (source === "local") {
    confirmLocalPicker();
  } else {
    const { id, name } = _pickerSelectedPath;
    const pathText  = document.getElementById("path-drive-text");
    const dot       = document.getElementById("dot-drive");
    const label     = document.getElementById("label-drive");
    const card      = document.getElementById("sc-drive");
    if (pathText) { pathText.textContent = name; pathText.classList.remove("empty"); }
    if (dot)    dot.className    = "sc-status-dot connected";
    if (label)  label.textContent = "Connected";
    if (card)   card.classList.add("active-cloud");
    closeModal("local-picker-overlay");
    fetch(`${API_BASE}/drive/set-folder`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ folder_id: id, folder_name: name })
    })
    .then(r => r.json())
    .then((data) => {
       if (data.error) throw new Error(data.error);
       if (window.appSettings && window.appSettings.sources) {
         window.appSettings.sources.drive_folder_id = id;
         window.appSettings.sources.drive_folder_name = name;
       }
       if (typeof window.revalidateFileTree === "function") window.revalidateFileTree();
       showToast(`Drive folder set: ${name}`, "success");
    })
    .catch(() => showToast("Failed to save folder", "error"));
  }
};


async function _loadDriveFolders(parentId, isBack = false) {
  const listEl = document.getElementById("picker-list");
  const crumb  = document.getElementById("picker-breadcrumb");
  const backBtn = document.getElementById("picker-back-btn");

  if (listEl) listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-dim);"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
  
  // Deselect on navigation
  _pickerSelectedPath = null;
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = true;

  // Update nav stack
  if (!isBack && parentId !== null) {
    // Don't push if we're going back
    const crumbName = _pickerNavStack.length > 0 ? parentId : parentId;
    // We'll update the name after fetch
  }

  // Check frontend cache first
  if (parentId && _driveChildrenCache[parentId]) {
    _renderDriveFolders(_driveChildrenCache[parentId], parentId, isBack);
    return;
  }

  try {
    const url = parentId ? `${API_BASE}/drive/folders?parent_id=${encodeURIComponent(parentId)}` : `${API_BASE}/drive/folders`;
    const res = await fetchWithTimeout(url, {}, 8000);
    const data = await res.json();
    const folders = data.folders || [];
    
    // Cache the result
    if (parentId) _driveChildrenCache[parentId] = folders;
    
    _renderDriveFolders(folders, parentId, isBack);
    
  } catch(e) {
    if (listEl) listEl.innerHTML = '<div style="padding:24px;color:var(--color-error);text-align:center;"><i class="fas fa-triangle-exclamation"></i> Could not load Drive folders — check authentication.</div>';
  }
}

function _renderDriveFolders(folders, parentId, isBack) {
  const listEl = document.getElementById("picker-list");
  const crumb  = document.getElementById("picker-breadcrumb");
  const backBtn = document.getElementById("picker-back-btn");
  
  // Build breadcrumb trail
  if (backBtn) backBtn.style.display = _pickerNavStack.length > 0 ? "" : "none";
  
  if (!parentId) {
    // Show root entry points (like drives in local picker)
    if (crumb) crumb.textContent = "Google Drive";
    if (backBtn) backBtn.style.display = "none";
    
    if (!listEl) return;
    listEl.innerHTML = folders.map(f => {
      const isShared = f.type === "shared" || f.id === "shared";
      const iconClass = isShared ? "shared-icon" : "drive-icon";
      const iconChar = isShared ? '<i class="fas fa-share-nodes"></i>' : '<i class="fab fa-google-drive"></i>';
      const sub = isShared ? "Files shared by others" : "Your personal files";
      return `
        <div class="picker-root-card" data-drive-id="${f.id}" data-drive-name="${escapeHtml(f.name)}"
             onclick="_pickerSelectDriveItem('${f.id}','${escapeHtml(f.name)}')"
             ondblclick="_pickerOpenDriveFolder('${f.id}','${escapeHtml(f.name)}')">
          <div class="picker-root-icon ${iconClass}">${iconChar}</div>
          <div style="flex:1;">
            <div class="picker-root-name">${escapeHtml(f.name)}</div>
            <div class="picker-root-sub">${sub}</div>
          </div>
          <span class="picker-item-chevron"><i class="fas fa-chevron-right"></i></span>
        </div>`;
    }).join("");
    return;
  }
  
  // Update breadcrumb
  const crumbParts = _pickerNavStack.map(s => s.name);
  if (crumb) crumb.textContent = crumbParts.join(" / ") || "Google Drive";
  
  if (!listEl) return;
  
  if (!folders.length) {
    listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-dim);font-size:0.85rem;"><i class="fas fa-folder-open" style="font-size:1.5rem;margin-bottom:8px;display:block;opacity:0.4;"></i>No sub-folders found</div>';
    return;
  }
  
  listEl.innerHTML = folders.map(f => `
    <div class="picker-item" data-drive-id="${f.id}" data-drive-name="${escapeHtml(f.name)}"
         onclick="_pickerSelectDriveItem('${f.id}','${escapeHtml(f.name)}')"
         ondblclick="_pickerOpenDriveFolder('${f.id}','${escapeHtml(f.name)}')">
      <span class="picker-item-icon">📁</span>
      <span class="picker-item-name">${escapeHtml(f.name)}</span>
      <span class="picker-item-chevron"><i class="fas fa-chevron-right"></i></span>
    </div>`
  ).join("");
}

// Single click = select folder
window._pickerSelectDriveItem = function(id, name) {
  _pickerSelectedPath = { id, name };
  document.querySelectorAll(".picker-item, .picker-root-card").forEach(el => el.classList.remove("picker-selected"));
  const el = document.querySelector(`[data-drive-id="${id}"]`);
  if (el) el.classList.add("picker-selected");
  const confirm = document.getElementById("btn-confirm-picker");
  if (confirm) confirm.disabled = false;
};

// Double click = navigate into folder
window._pickerOpenDriveFolder = function(id, name) {
  _pickerNavStack.push({ id, name });
  _loadDriveFolders(id);
};

/* ── Cloud LLM toggle (show/hide API fields) ─────────────────── */
window.onCloudLLMToggle = function(enabled) {
  const body = document.getElementById("cloud-llm-body");
  const dot  = document.getElementById("dot-cloud-llm");
  if (body) {
    if (enabled) {
      body.classList.remove("mec-body-disabled");
    } else {
      body.classList.add("mec-body-disabled");
    }
  }
  if (dot) dot.className = "status-dot " + (enabled ? "yellow" : "gray");
  settingsTriggerAutosave();
};

/* ── Accent Color Picker ─────────────────────────────────────── */
window.setAccentColor = function(accent, swatchEl, noSave = false) {
  // Mark active swatch
  document.querySelectorAll(".accent-swatch").forEach(s => s.classList.remove("active"));
  if (swatchEl) {
    swatchEl.classList.add("active");
  } else {
    const target = document.querySelector(`.accent-swatch[data-accent="${accent}"]`);
    if (target) target.classList.add("active");
  }

  // Map accent name to CSS variable overrides
  const palettes = {
    purple: { accent: "#6c5ce7", accentLight: "#a78bfa", accentGlow: "rgba(108,92,231,0.35)", accentBg: "rgba(108,92,231,0.12)" },
    blue:   { accent: "#3b82f6", accentLight: "#60a5fa", accentGlow: "rgba(59,130,246,0.35)",  accentBg: "rgba(59,130,246,0.12)" },
    cyan:   { accent: "#0ea5e9", accentLight: "#38bdf8", accentGlow: "rgba(14,165,233,0.35)",  accentBg: "rgba(14,165,233,0.12)" },
    green:  { accent: "#10b981", accentLight: "#34d399", accentGlow: "rgba(16,185,129,0.35)",  accentBg: "rgba(16,185,129,0.12)" },
    amber:  { accent: "#f59e0b", accentLight: "#fbbf24", accentGlow: "rgba(245,158,11,0.35)",  accentBg: "rgba(245,158,11,0.12)" },
    rose:   { accent: "#f43f5e", accentLight: "#fb7185", accentGlow: "rgba(244,63,94,0.35)",   accentBg: "rgba(244,63,94,0.12)" },
  };
  const p = palettes[accent] || palettes.purple;
  const root = document.documentElement;
  root.style.setProperty("--accent",       p.accent);
  root.style.setProperty("--accent-light", p.accentLight);
  root.style.setProperty("--accent-glow",  p.accentGlow);
  root.style.setProperty("--accent-bg",    p.accentBg);
  
  if (!noSave) settingsTriggerAutosave();
};

// Global helper to update slider labels silently
function _syncSliderLabel(id, value, suffix="") {
  const el = document.getElementById(id);
  const val = document.getElementById(id + "-val");
  if (el) el.value = value;
  if (val) val.textContent = value + suffix;
}

window.updateSettingsModal = async function() {
  _isInitializingSettings = true;
  try {
    const settings = window.appSettings || {};

    const gen = settings.general || {};
    const src = settings.sources || {};
    const rag = settings.rag     || {};
    const mod = settings.models  || {};
    const dat = settings.data    || {};

    // 1. TAB: General
    if (gen.accent_color) setAccentColor(gen.accent_color, null, true);
    if (gen.system_prompt !== undefined) {
      const sp = document.getElementById("system-prompt");
      if (sp) { sp.value = gen.system_prompt; if (window.updateCharCount) updateCharCount(sp); }
    }
    _syncSliderLabel("ctx-slider", gen.context_memory_limit || 6, " msgs");

    // 2. TAB: Sources (Baseline DOM Population)
    const toggleCloud    = document.getElementById("toggle-cloud");
    const pathDriveText  = document.getElementById("path-drive-text");
    const dotDrive       = document.getElementById("dot-drive");
    const labelDrive     = document.getElementById("label-drive");
    const cardDrive      = document.getElementById("sc-drive");
    const btnCloudAction = document.getElementById("btn-cloud-action");
    const driveFileCount = document.getElementById("drive-file-count");
    
    const toggleLocal    = document.getElementById("toggle-local");
    const pathLocalText  = document.getElementById("settings-local-folder");
    const dotLocal       = document.getElementById("dot-local");
    const labelLocal     = document.getElementById("label-local");
    const cardLocal      = document.getElementById("sc-local");
    const localFileCount = document.getElementById("local-file-count");

    if (toggleCloud) toggleCloud.checked = !!src.cloud_enabled;
    if (toggleLocal) toggleLocal.checked = !!src.local_enabled;
    
    const localRoot = src.local_root_path;
    if (pathLocalText) { pathLocalText.textContent = localRoot || "No folder selected"; pathLocalText.classList.toggle("empty", !localRoot); }
    
    if (localRoot) {
      if (dotLocal)   dotLocal.className   = "sc-status-dot connected";
      if (labelLocal) labelLocal.textContent = "Connected";
      if (cardLocal)  cardLocal.classList.add("active-green");
    } else {
      if (dotLocal)   dotLocal.className   = "sc-status-dot disabled";
      if (labelLocal) labelLocal.textContent = "Not configured";
      if (cardLocal)  cardLocal.classList.remove("active-green");
    }

    // Disable picker buttons if source is off
    if (btnCloudAction) btnCloudAction.disabled = !src.cloud_enabled;
    if (document.getElementById("btn-local-browse")) document.getElementById("btn-local-browse").disabled = !src.local_enabled;

    // Async Hydration for Statuses/Stats
    (async () => {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/auth/status`, {}, 3000);
        const data = await res.json();
        
        // Fetch stats for both cloud and local
        const dStats = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 3000).then(r=>r.json()).catch(()=>({}));
        
        if (data.authenticated) {
          const folder = dStats.folder?.name || dStats.folder?.folder_name || src.drive_folder_name || null;
          if (pathDriveText) { pathDriveText.textContent = folder || "Root (All Files)"; pathDriveText.classList.remove("empty"); }
          if (dotDrive)    dotDrive.className    = "sc-status-dot connected";
          if (labelDrive)  labelDrive.textContent = "Connected";
          if (cardDrive)   cardDrive.classList.add("active-cloud");
          if (driveFileCount && dStats.cloud_total !== undefined) driveFileCount.textContent = dStats.cloud_total;
          if (btnCloudAction) { 
            btnCloudAction.innerHTML = '<i class="fas fa-pen-to-square"></i> Change Folder'; 
            btnCloudAction.onclick = () => promptChangeFolder('drive'); 
          }
        } else {
          if (pathDriveText) { pathDriveText.textContent = "Not connected"; pathDriveText.classList.add("empty"); }
          if (dotDrive)    dotDrive.className    = "sc-status-dot disabled";
          if (labelDrive)  labelDrive.textContent = "Not connected";
          if (btnCloudAction) { 
            btnCloudAction.innerHTML = '<i class="fas fa-plug"></i> Connect Drive'; 
            btnCloudAction.onclick = () => connectDrive(); 
          }
        }

        // Update local stats from the same stats response
        if (localFileCount && dStats.local_total !== undefined) {
          localFileCount.textContent = dStats.local_total;
        }

        // Hydrate LLM Status
        const llmRes = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 3000);
        const llmState = await llmRes.json();
        const settingsActiveModel = document.getElementById("settings-active-model");
        if (settingsActiveModel && llmState.current_model) settingsActiveModel.value = llmState.current_model;
        const settingsLlmDot = document.getElementById("settings-llm-dot");
        if (settingsLlmDot) settingsLlmDot.className = "status-dot " + (llmState.reachable ? "green" : "gray");
        if (typeof loadLLMStatus === "function") loadLLMStatus();

      } catch(_) {}
    })();

    // 4. TAB: RAG
    _syncSliderLabel("chunk-size", rag.chunk_size || 512);
    _syncSliderLabel("chunk-overlap", rag.chunk_overlap || 64);
    _syncSliderLabel("topk", rag.top_k || 30);
    _syncSliderLabel("topn", rag.top_n || 5);
    if (window.updateChunkPreview) updateChunkPreview();
    
    const rr = document.getElementById("rerank-toggle");
    if (rr) rr.checked = !!rag.rerank_enabled;
    const as = document.getElementById("auto-summarise-toggle");
    if (as) as.checked = !!rag.auto_summarise;

    // 5. TAB: Models
    const tcl = document.getElementById("toggle-cloud-llm");
    if (tcl) tcl.checked = !!mod.cloud_llm_enabled;
    if (typeof onCloudLLMToggle === "function") onCloudLLMToggle(!!mod.cloud_llm_enabled);

    const cp = document.getElementById("cloud-llm-provider");
    if (cp) cp.value = mod.cloud_provider || "Google Gemini";
    const ck = document.getElementById("cloud-llm-key");
    if (ck) ck.value = mod.cloud_key || "";
    const cm = document.getElementById("cloud-llm-model");
    if (cm) cm.value = mod.cloud_model || "gemini-1.5-pro";
    const em = document.getElementById("embed-model-select");
    if (em) em.value = mod.embed_model || "nomic-embed-text";

    // 6. TAB: Data
    const si = document.getElementById("sync-interval-select");
    if (si) si.value = dat.sync_interval || "30";

    if (typeof onProviderChange === "function") onProviderChange();
  } finally {
    _isInitializingSettings = false;
  }
};

window.toggleSource = async function(type, enabled) {
  // Guard: don't allow enabling cloud if not connected
  if (type === "cloud" && enabled) {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/auth/status`, {}, 3000);
      const data = await res.json();
      if (!data.authenticated) {
        showToast("Connect Google Drive first to enable cloud sync", "error");
        const toggle = document.getElementById("toggle-cloud");
        if (toggle) toggle.checked = false;
        return;
      }
    } catch(_) {
      showToast("Cannot verify Google connection  -  try again later", "error");
      const toggle = document.getElementById("toggle-cloud");
      if (toggle) toggle.checked = false;
      return;
    }
  }

  const card = document.getElementById(`card-${type}`);
  if (card) card.classList.toggle("disabled", !enabled);

  // Sync button disabled state
  const btn = type === 'cloud' ? document.getElementById("btn-cloud-action") : document.getElementById("btn-local-browse");
  if (btn) btn.disabled = !enabled;
  if (!enabled) closeFolderPrompt(type === 'cloud' ? 'drive' : 'local');

  try {
    const res = await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ 
        sources: { [`${type}_enabled`]: enabled } 
      })
    });
    const data = await res.json();
    if (data.error) showToast(data.error, "error");
    else {
      window.appSettings = data.settings || window.appSettings;
      if (typeof window.revalidateFileTree === "function") window.revalidateFileTree();
    }
  } catch (err) {
    showToast("Failed to toggle source", "error");
  }
};

// ── DISCONNECT & SWITCH TO LOCAL ─────────────────────────────
window.disconnectAndSwitchToLocal = async function() {
  try {
    await fetch(`${API_BASE}/auth/disconnect`, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() }
    });
    localStorage.setItem("paiks-mode", "local");
    // Disable cloud in settings
    const res = await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ 
        sources: { cloud_enabled: false } 
      })
    });
    const resJson = await res.json();
    window.appSettings = resJson.settings || window.appSettings;
    if (typeof window.revalidateFileTree === "function") window.revalidateFileTree();
    
    showToast("Disconnected from Google Drive", "info");
    setTimeout(() => location.reload(), 800);
  } catch(e) {
    showToast("Disconnect failed", "error");
  }
};

// ── CONNECT DRIVE (upgrade from local mode) ──────────────────
window.connectDrive = async function() {
  try {
    const res = await fetch(`${API_BASE}/auth/url`);
    const data = await res.json();
    if (data.url) {
      localStorage.setItem("paiks-mode", "drive");
      window.location.href = data.url;
    } else {
      showToast(data.error || "Could not get auth URL", "error");
    }
  } catch (err) {
    showToast("Failed to connect: " + err.message, "error");
  }
};

// ── LOGOUT (return to login screen) ──────────────────────────
window.logoutPaiks = function() {
  localStorage.removeItem("paiks-mode");
  // Also disconnect Drive if connected
  fetch(`${API_BASE}/auth/disconnect`, {
    method: "POST",
    headers: { "X-CSRFToken": getCsrfToken() }
  }).catch(() => {});
  window.location.href = "/login/";
};

// ── Folder Change Prompts ────────────────────────────────────
window.promptChangeFolder = function(type) {
  const popover = document.getElementById(`popover-warning-${type}`);
  if (popover) {
    // Close others first
    document.querySelectorAll(".picker-warning-popover").forEach(p => p.classList.add("hidden"));
    popover.classList.remove("hidden");
  }
};

window.closeFolderPrompt = function(type) {
  const popover = document.getElementById(`popover-warning-${type}`);
  if (popover) popover.classList.add("hidden");
};

window.browseLocalPath = async function(path, isBack = false) {
  const listEl = document.getElementById("picker-list");
  const breadcrumbEl = document.getElementById("picker-breadcrumb");
  const backBtn = document.getElementById("picker-back-btn");
  if (!listEl) return;

  listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-dim);"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
  if (breadcrumbEl) breadcrumbEl.textContent = path;
  _pickerCurrentPath = path;
  
  // Deselect on navigation
  _pickerSelectedPath = null;
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = true;

  // Manage nav stack
  if (!isBack) {
    _pickerNavStack.push(path);
  }
  if (backBtn) backBtn.style.display = _pickerNavStack.length > 1 ? "" : "none";

  try {
    const res = await fetch(`${API_BASE}/system/browse?path=${encodeURIComponent(path)}`);
    const data = await res.json();

    if (data.error) {
      listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--color-error);">${data.error}</div>`;
      return;
    }

    let html = "";
    data.items.forEach(item => {
      const icon = item.type === "drive" ? "💽" : (item.is_dir ? "📁" : "📄");
      const isSelectable = item.is_dir && item.name !== "..";
      const escapedPath = item.path.replace(/\\/g, "\\\\").replace(/'/g, "\\'");

      // Single click = select, Double click = open (for directories)
      const onclickAttr = isSelectable
        ? `onclick="_localPickerSelect(this, '${escapedPath}')"`
        : "";
      const ondblclickAttr = item.is_dir
        ? `ondblclick="browseLocalPath('${escapedPath}')"`
        : "";

      html += `
        <div class="picker-item ${item.is_dir ? 'is-dir' : 'is-file'}"
             data-path="${item.path}"
             ${onclickAttr} ${ondblclickAttr}>
          <span class="picker-item-icon">${icon}</span>
          <span class="picker-item-name">${item.name}</span>
          ${item.size ? `<span class="picker-item-meta">${formatSize(item.size)}</span>` : ""}
          ${item.is_dir && item.name !== ".." ? '<span class="picker-item-chevron"><i class="fas fa-chevron-right"></i></span>' : ""}
        </div>
      `;
    });
    listEl.innerHTML = html || '<div style="padding:24px;text-align:center;color:var(--text-dim);">Empty folder</div>';
  } catch (err) {
    listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--color-error);">Failed to browse filesystem.</div>`;
  }
};

// Single click handler for local picker — select a folder
window._localPickerSelect = function(el, path) {
  _pickerSelectedPath = path;
  document.querySelectorAll("#picker-list .picker-item").forEach(item => item.classList.remove("picker-selected"));
  el.classList.add("picker-selected");
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = false;
};

window.selectPickerItem = function(btn, path) {
  _pickerSelectedPath = path;
  document.querySelectorAll(".picker-item").forEach(el => el.classList.remove("picker-selected"));
  const row = btn.closest(".picker-item");
  if (row) row.classList.add("picker-selected");
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = false;
};

window.confirmLocalPicker = async function() {
  if (!_pickerSelectedPath) return;

  try {
    const res = await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ 
        sources: { local_root_path: _pickerSelectedPath, local_enabled: true } 
      })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    window.appSettings = data.settings || window.appSettings;
    if (typeof window.revalidateFileTree === "function") window.revalidateFileTree();

    const pathText = document.getElementById("settings-local-folder");
    closeModal("local-picker-overlay");
    updateSettingsModal();
  } catch (err) {
    showToast("Failed to set root: " + err.message, "error");
  }
};

// ── LLM CONFIG ───────────────────────────────────────────────

window.loadLLMStatus = async function() {
  const btn = document.getElementById("chat-model-btn");
  const indicator = document.getElementById("chat-model-indicator");
  const nameLabel = document.getElementById("chat-model-name");
  const dropdownList = document.getElementById("model-dropdown-list");

  // Use SSE-cached data if available (avoids redundant HTTP fetch)
  let data = (window._liveStats && window._liveStats.llm_status)
    ? window._liveStats.llm_status
    : null;

  if (!data) {
    // Fallback: HTTP fetch (first load before SSE starts pushing)
    try {
      const res = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 5000);
      data = await res.json();
    } catch {
      if (btn) btn.disabled = true;
      if (indicator) indicator.className = "chat-model-indicator status-offline";
      if (nameLabel) nameLabel.textContent = "Unavailable";
      return;
    }
  }

  window.current_llm_model = data.current_model || "";
  if (!btn) return;

  if (data.reachable) {
    if (indicator) indicator.className = "chat-model-indicator status-online";
    if (nameLabel) nameLabel.textContent = data.current_model || "Connected";
    btn.disabled = false;
    if (dropdownList && data.available_models?.length) {
      dropdownList.innerHTML = data.available_models
        .filter(m => !m.toLowerCase().includes('embed'))
        .map(m => `
          <button class="model-dropdown-item ${m === data.current_model ? 'active' : ''}" onclick="selectChatModel('${m}')">
            ${m} ${m === data.current_model ? ' ✓' : ''}
          </button>
        `).join("");
    }
  } else {
    if (indicator) indicator.className = "chat-model-indicator status-offline";
    if (nameLabel) nameLabel.textContent = "Offline";
    btn.disabled = true;
  }
};

// Auto-update LLM UI when SSE pushes new llm_status
if (typeof PAIKSEventBus !== "undefined") {
  PAIKSEventBus.on("llm_status", function(data) {
    // Update the chat model button in real-time
    if (typeof loadLLMStatus === "function") loadLLMStatus();
  });
}

window.onProviderChange = function() {
  const provider = document.getElementById("llm-provider-select")?.value;
  const urlInput = document.getElementById("llm-url-input");
  if (!urlInput) return;
  const current = urlInput.value.trim();
  if (provider === "ollama" && (!current || current.includes("1234"))) {
    urlInput.value = "http://localhost:11434";
  } else if (provider === "openai_compat" && (!current || current.includes("11434"))) {
    urlInput.value = "http://localhost:1234";
  }
};

window.saveLLMConfig = async function() {
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  const base_url = urlInput?.value.trim();
  const provider = providerSelect?.value || "ollama";
  const model = window.current_llm_model || "llama3.2";

  try {
    await fetch(`${API_BASE}/rag/llm/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ base_url, model, provider }),
    });
    showToast("LLM configuration saved", "success");
    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to save LLM config", "error");
  }
};

window.selectChatModel = async function(modelName) {
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  const base_url = urlInput?.value.trim() || "http://localhost:11434";
  const provider = providerSelect?.value || "ollama";

  // ── Optimistic UI Update (Instant Response) ──
  const nameLabel = document.getElementById("chat-model-name");
  if (nameLabel) nameLabel.textContent = modelName;
  const menu = document.getElementById("model-dropdown-menu");
  if (menu) menu.classList.add("hidden");
  document.querySelectorAll(".model-dropdown-item").forEach(item => {
     item.classList.toggle("active", item.textContent.trim().startsWith(modelName));
  });
  window.current_llm_model = modelName;

  try {
    await fetch(`${API_BASE}/rag/llm/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ base_url, model: modelName, provider }),
    });
    showToast(`Model set to ${modelName}`, "success");
    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to change model", "error");
  }
};
