let _pickerCurrentPath = "This PC";
let _pickerSelectedPath = null;

// ── Helper: is local-only mode active? ──────────────────────
function isLocalMode() {
  return localStorage.getItem("paiks-mode") === "local";
}

window.updateSettingsModal = async function() {
  const cloudConnectedState = { connected: false, user: null };
  const statsState = {};
  const settingsState = {};
  const llmState = {};

  // ── Fetch each resource independently  -  one failure doesn't kill the rest
  try {
    const res = await fetchWithTimeout(`${API_BASE}/auth/status`, {}, 5000);
    const data = await res.json();
    cloudConnectedState.connected = !!data.authenticated;
    cloudConnectedState.user = data.user;
  } catch(_) { /* offline or unavailable  -  that's fine */ }

  try {
    const res = await fetchWithTimeout(`${API_BASE}/drive/stats`, {}, 5000);
    Object.assign(statsState, await res.json());
  } catch(_) {}

  try {
    const res = await fetchWithTimeout(`${API_BASE}/system/settings`, {}, 5000);
    Object.assign(settingsState, await res.json());
  } catch(_) {}

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 5000);
    Object.assign(llmState, await res.json());
  } catch(_) {}

  const cloudConnected = cloudConnectedState.connected;
  const localMode = isLocalMode();

  // ── DATA SOURCES: CLOUD ──────────────────────────────────
  const cardCloud   = document.getElementById("card-cloud");
  const toggleCloud = document.getElementById("toggle-cloud");
  const pathCloud   = document.getElementById("settings-drive-folder");
  const statusCloud = document.getElementById("settings-drive-status");
  const btnCloudAction = document.getElementById("btn-cloud-action");

  if (toggleCloud) {
    // In local mode without Drive connected: disable the toggle entirely
    if (localMode && !cloudConnected) {
      toggleCloud.checked = false;
      toggleCloud.disabled = true;
    } else {
      toggleCloud.checked = !!settingsState.cloud_enabled;
      toggleCloud.disabled = false;
    }
  }
  if (cardCloud) {
    cardCloud.classList.toggle("disabled", !settingsState.cloud_enabled || (localMode && !cloudConnected));
  }
  if (pathCloud) {
    if (cloudConnected) {
      const folder = statsState.folder?.name || statsState.folder?.folder_name || null;
      pathCloud.textContent = folder ? `📁 ${folder}` : "Root (All Files)";
    } else {
      pathCloud.textContent = "Not connected";
    }
  }
  if (statusCloud) {
    statusCloud.innerHTML = cloudConnected
      ? `<span class="dot online"></span> <span>Connected · ${statsState.cloud_total || 0} files</span>`
      : `<span class="dot offline"></span> <span>Disconnected</span>`;
  }
  if (btnCloudAction) {
    if (cloudConnected) {
      btnCloudAction.textContent = "Change Folder";
      btnCloudAction.onclick = () => openModal("drive-overlay");
    } else {
      btnCloudAction.textContent = "Connect Google Drive";
      btnCloudAction.onclick = () => connectDrive();
    }
  }

  // ── DATA SOURCES: LOCAL ──────────────────────────────────
  const cardLocal   = document.getElementById("card-local");
  const toggleLocal = document.getElementById("toggle-local");
  const pathLocal   = document.getElementById("settings-local-folder");
  const statusLocal = document.getElementById("settings-local-status");

  if (toggleLocal) toggleLocal.checked = !!settingsState.local_enabled;
  if (cardLocal)   cardLocal.classList.toggle("disabled", !settingsState.local_enabled);
  if (pathLocal)   pathLocal.textContent = settingsState.local_root_path || "No folder selected";
  if (statusLocal) {
    statusLocal.innerHTML = settingsState.local_root_path
      ? `<span class="dot online"></span> <span>Ready · ${statsState.local_total || 0} files</span>`
      : `<span class="dot offline"></span> <span>Not configured</span>`;
  }

  // ── ACCOUNT INFO ──────────────────────────────────────────
  const accountSection = document.getElementById("settings-account-section");
  if (accountSection) {
    if (cloudConnected && cloudConnectedState.user) {
      const u = cloudConnectedState.user;
      const name = u.display_name || u.email || "Connected";
      accountSection.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:var(--radius-md);">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--accent-bg);display:flex;align-items:center;justify-content:center;font-size:1.1rem;font-weight:600;color:var(--accent);">${name[0].toUpperCase()}</div>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:600;font-size:0.9rem;">${escapeHtml(name)}</div>
            <div style="font-size:0.75rem;color:var(--text-dim);">${escapeHtml(u.email || "Google Drive")}</div>
          </div>
          <button class="btn btn-outline btn-sm" onclick="disconnectAndSwitchToLocal()" style="font-size:0.75rem;">Disconnect</button>
        </div>`;
    } else {
      const modeLabel = localMode ? "Local Mode" : "Not Connected";
      accountSection.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:var(--radius-md);">
          <div style="width:40px;height:40px;border-radius:50%;background:rgba(100,100,100,0.2);display:flex;align-items:center;justify-content:center;font-size:1.2rem;">💻</div>
          <div style="flex:1;">
            <div style="font-weight:600;font-size:0.9rem;">${modeLabel}</div>
            <div style="font-size:0.75rem;color:var(--text-dim);">Using local files only</div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="connectDrive()" style="font-size:0.75rem;">Connect Drive</button>
        </div>`;
    }
  }

  // ── LLM CONFIG ───────────────────────────────────────────
  const urlInput       = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  const modelSelect    = document.getElementById("llm-model-select");

  if (urlInput && llmState.base_url) urlInput.value = llmState.base_url;
  if (providerSelect && llmState.provider) providerSelect.value = llmState.provider;

  if (llmState.reachable && llmState.available_models?.length) {
    if (modelSelect) {
      modelSelect.innerHTML = llmState.available_models
        .map(m => `<option value="${m}"${m === llmState.current_model ? " selected" : ""}>${m}</option>`)
        .join("");
      modelSelect.style.display = "";
    }
  }

  if (typeof onProviderChange === "function") onProviderChange();
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

  try {
    const body = {};
    body[`${type}_enabled`] = enabled;

    const res = await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.error) showToast(data.error, "error");
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
    await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ cloud_enabled: false })
    });
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

// ── LOCAL FOLDER PICKER LOGIC ────────────────────────────────

window.openLocalFolderPicker = function() {
  const overlay = document.getElementById("local-picker-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  _pickerSelectedPath = null;
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = true;
  browseLocalPath("This PC");
};

window.browseLocalPath = async function(path) {
  const listEl = document.getElementById("picker-list");
  const breadcrumbEl = document.getElementById("picker-breadcrumb");
  if (!listEl) return;

  listEl.innerHTML = '<div class="flex-center" style="height:100%"><div class="spinner"></div></div>';
  if (breadcrumbEl) breadcrumbEl.textContent = path;
  _pickerCurrentPath = path;

  try {
    const res = await fetch(`${API_BASE}/system/browse?path=${encodeURIComponent(path)}`);
    const data = await res.json();

    if (data.error) {
      listEl.innerHTML = `<div class="text-center mt-lg" style="color:var(--red);">${data.error}</div>`;
      return;
    }

    let html = "";
    data.items.forEach(item => {
      const icon = item.type === "drive" ? "💽" : (item.is_dir ? "📁" : "📄");
      const isSelectable = item.is_dir && item.name !== "..";
      const onclick = item.is_dir
        ? `onclick="event.stopPropagation(); browseLocalPath('${item.path.replace(/\\/g, "\\\\")}')"`
        : "";

      html += `
        <div class="picker-item ${item.is_dir ? 'is-dir' : 'is-file'}"
             data-path="${item.path}"
             ${onclick}
             style="display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:8px; cursor:pointer; transition:all 0.2s;">
          <span style="font-size:1.2rem;">${icon}</span>
          <div style="flex:1; min-width:0;">
            <div style="font-size:0.9rem; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name}</div>
            ${item.size ? `<span style="font-size:0.7rem; color:var(--text-dim);">${formatSize(item.size)}</span>` : ""}
          </div>
          ${isSelectable ? `<button class="btn-icon" style="font-size:0.7rem; opacity:0.6;" onclick="event.stopPropagation(); selectPickerItem(this, '${item.path.replace(/\\/g, "\\\\")}')">Select</button>` : ""}
        </div>
      `;
    });
    listEl.innerHTML = html || '<div class="text-center mt-lg color-dim">Empty folder</div>';
  } catch (err) {
    listEl.innerHTML = `<div class="text-center mt-lg" style="color:var(--red);">Failed to browse filesystem.</div>`;
  }
};

window.selectPickerItem = function(btn, path) {
  _pickerSelectedPath = path;
  document.querySelectorAll(".picker-item").forEach(el => el.style.background = "");
  const row = btn.closest(".picker-item");
  if (row) row.style.background = "var(--accent-bg)";
  const confirmBtn = document.getElementById("btn-confirm-picker");
  if (confirmBtn) confirmBtn.disabled = false;
};

window.confirmLocalPicker = async function() {
  if (!_pickerSelectedPath) return;

  try {
    const res = await fetch(`${API_BASE}/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ local_root_path: _pickerSelectedPath, local_enabled: true })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    showToast("Local root folder updated", "success");
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

  try {
    const res = await fetchWithTimeout(`${API_BASE}/rag/llm/status`, {}, 5000);
    const data = await res.json();
    window.current_llm_model = data.current_model || "";
    if (!btn) return;

    if (data.reachable) {
      if (indicator) indicator.className = "chat-model-indicator status-online";
      if (nameLabel) nameLabel.textContent = data.current_model || "Connected";
      btn.disabled = false;
      if (dropdownList && data.available_models?.length) {
        dropdownList.innerHTML = data.available_models
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
  } catch {
    if (btn) btn.disabled = true;
    if (indicator) indicator.className = "chat-model-indicator status-offline";
    if (nameLabel) nameLabel.textContent = "Unavailable";
  }
};

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

  try {
    await fetch(`${API_BASE}/rag/llm/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ base_url, model: modelName, provider }),
    });
    showToast(`Model set to ${modelName}`, "success");
    const menu = document.getElementById("model-dropdown-menu");
    if (menu) menu.classList.add("hidden");
    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to change model", "error");
  }
};
