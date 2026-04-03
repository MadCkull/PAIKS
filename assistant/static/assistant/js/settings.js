window.updateSettingsModal = async function() {
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
      if (modelSelect) {
        modelSelect.innerHTML = data.available_models
          .map(m => `<option value="${m}"${m === data.current_model ? " selected" : ""}>${m}</option>`)
          .join("");
        modelSelect.style.display = "";
      }
      if (modelInput) modelInput.style.display = "none";
    } else {
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

window.loadLLMStatus = async function() {
  const btn = document.getElementById("chat-model-btn");
  const indicator = document.getElementById("chat-model-indicator");
  const nameLabel = document.getElementById("chat-model-name");
  const dropdownList = document.getElementById("model-dropdown-list");
  
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");

  try {
    const res = await fetch(`${API_BASE}/rag/llm/status`);
    const data = await res.json();

    if (urlInput && data.base_url) urlInput.value = data.base_url;
    if (providerSelect && data.provider) providerSelect.value = data.provider;
    if (typeof onProviderChange === 'function') onProviderChange();

    window.current_llm_model = data.current_model || "";

    if (!btn) return;

    if (data.reachable) {
      indicator.className = "chat-model-indicator status-online";
      nameLabel.textContent = data.current_model || "Connected";
      btn.disabled = false;

      if (dropdownList && data.available_models?.length) {
        dropdownList.innerHTML = data.available_models
          .map(m => `
            <button class="model-dropdown-item ${m === data.current_model ? 'active' : ''}" onclick="selectChatModel('${m}')">
              ${m}
              ${m === data.current_model ? ' <span style="font-size: 1.1em;">✓</span>' : ''}
            </button>
          `)
          .join("");
      } else if (dropdownList) {
         dropdownList.innerHTML = '<div class="model-dropdown-empty">No models found</div>';
      }
    } else {
      indicator.className = "chat-model-indicator status-offline";
      nameLabel.textContent = "Offline";
      btn.disabled = true;
      if (dropdownList) {
        dropdownList.innerHTML = '<div class="model-dropdown-empty">LLM not reachable</div>';
      }
    }
  } catch {
    if (indicator) indicator.className = "chat-model-indicator status-offline";
    if (nameLabel) nameLabel.textContent = "Unavailable";
    if (btn) btn.disabled = true;
  }
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
}

window.saveLLMConfig = async function() {
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");

  const base_url = urlInput?.value.trim();
  const provider = providerSelect?.value || "ollama";
  const model = window.current_llm_model || "llama3.2";

  if (!base_url) {
    showToast("Set a URL first.", "error");
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
    showToast(`LLM configuration saved`, "success");
    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to save LLM config: " + err.message, "error");
  }
}

window.selectChatModel = async function(modelName) {
  const urlInput = document.getElementById("llm-url-input");
  const providerSelect = document.getElementById("llm-provider-select");
  
  const base_url = urlInput?.value.trim() || "http://localhost:11434";
  const provider = providerSelect?.value || "ollama";
  const model = modelName;

  try {
    const res = await fetch(`${API_BASE}/rag/llm/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, model, provider }),
    });
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    showToast(`Model set to ${model}`, "success");
    
    const menu = document.getElementById("model-dropdown-menu");
    const btn = document.getElementById("chat-model-btn");
    if (menu) menu.classList.add("hidden");
    if (btn) btn.setAttribute("aria-expanded", "false");

    await loadLLMStatus();
  } catch (err) {
    showToast("Failed to change model: " + err.message, "error");
  }
}

function initModelDropdown() {
  const chatModelBtn = document.getElementById("chat-model-btn");
  const chatModelMenu = document.getElementById("model-dropdown-menu");
  
  if (chatModelBtn && chatModelMenu) {
    chatModelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (chatModelBtn.disabled) return;
      const isExpanded = chatModelBtn.getAttribute("aria-expanded") === "true";
      if (isExpanded) {
        chatModelMenu.classList.add("hidden");
        chatModelBtn.setAttribute("aria-expanded", "false");
      } else {
        chatModelMenu.classList.remove("hidden");
        chatModelBtn.setAttribute("aria-expanded", "true");
      }
    });

    document.addEventListener("click", (e) => {
      if (!chatModelBtn.contains(e.target) && !chatModelMenu.contains(e.target)) {
        chatModelMenu.classList.add("hidden");
        chatModelBtn.setAttribute("aria-expanded", "false");
      }
    });
  }
}
