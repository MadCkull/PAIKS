let _searchTimeout;

window.initSearch = function() {
  const input = document.getElementById("search-input");
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

      if (data.error || !data.results?.length) {
        resultsContainer.innerHTML = `<p class="text-muted mt-sm">${data.error || "No results found."}</p>`;
        return;
      }

      resultsContainer.innerHTML = data.results.map((r, i) => `
        <a href="${r.webViewLink || r.localPath || "#"}" target="_blank" rel="noopener" class="result-item" style="animation-delay:${i * 0.05}s">
          <div class="result-icon">${getFileEmoji(r.mimeType || r.name || "")}</div>
          <div class="result-info">
            <div class="result-name">${escapeHtml(r.name || "")}</div>
            <div class="result-meta">${r.relevance_hint || ""}</div>
          </div>
        </a>`).join("");
    } catch (err) {
      resultsContainer.innerHTML = `<p class="text-muted mt-sm">Search failed.</p>`;
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(_searchTimeout);
    _searchTimeout = setTimeout(performSearch, 400);
  });
};

window.openModal = function(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove("hidden");
    // Trigger specific updates
    if (id === "settings-overlay" && window.updateSettingsModal) updateSettingsModal();
    if (id === "drive-overlay" && window.updateDriveModal) updateDriveModal();
    if (id === "dashboard-overlay" && window.updateDashboardStats) updateDashboardStats();
  }
};

window.closeModal = function(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
};

function initToolbar() {
  const toolbar = document.getElementById("toolbarComponent");
  if (!toolbar) return;

  const tabBtns = toolbar.querySelectorAll(".tab-btn");

  tabBtns.forEach(btn => {
    btn.addEventListener("mouseenter", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "settings")  openModal("settings-overlay");
      if (action === "drive")     openModal("drive-overlay");
      if (action === "dashboard") openModal("dashboard-overlay");
      if (action === "theme")     toggleTheme();
    });
  });

  toolbar.addEventListener("mouseleave", () => {
    tabBtns.forEach(b => b.classList.remove("active"));
  });

  // Handle overlay background clicks
  document.querySelectorAll(".overlay").forEach(ov => {
    ov.addEventListener("click", e => {
      if (e.target === ov) ov.classList.add("hidden");
    });
  });

  // Sidebar Workspace Switching logic
  document.querySelectorAll(".workspace-item").forEach(ws => {
    ws.addEventListener("click", () => {
      document.querySelectorAll(".workspace-item").forEach(w => w.classList.remove("active"));
      ws.classList.add("active");
      
      const wsType = ws.dataset.ws; // 'all', 'drive', 'local'
      openModal("drive-overlay");
      
      // We rely on drive.js to handle the actual tab switching now
      const driveTabs = document.querySelector("#drive-tabs");
      if (driveTabs) {
          const tabToClick = wsType === "local" ? "local" : "cloud";
          const btn = driveTabs.querySelector(`[data-tab="${tabToClick}"]`);
          if (btn) btn.click();
      }
    });
  });
}

const SIDEBAR_COLLAPSED_KEY = "paiks-sidebar-collapsed";
function initSidebarCollapse() {
  const btn = document.getElementById("sidebar-collapse-toggle");
  const sidebar = document.getElementById("app-sidebar");
  if (!btn || !sidebar) return;

  if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1") sidebar.classList.add("collapsed");

  btn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebar.classList.contains("collapsed") ? "1" : "0");
  });
}

let _isDark = (localStorage.getItem("paiks-theme") || "dark") === "dark";
window.toggleTheme = function() {
  _isDark = !_isDark;
  const theme = _isDark ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("paiks-theme", theme);
  // Theme SVG update logic
  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.innerHTML = _isDark
      ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
      : '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  }
};
