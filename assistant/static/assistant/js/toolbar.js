let _searchTimeout;

window.initSearch = function() {
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
    clearTimeout(_searchTimeout);
    _searchTimeout = setTimeout(performSearch, 400);
  });

  if (btn) btn.addEventListener("click", performSearch);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(_searchTimeout);
      performSearch();
    }
  });
}

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

window.openModal = function(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
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
  });
  toolbar.addEventListener("mouseleave", () => {
    tabBtns.forEach(b => b.classList.remove("active"));
  });

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "settings")  { openModal("settings-overlay");  if(typeof updateSettingsModal === 'function') updateSettingsModal(); }
      if (action === "drive")     { openModal("drive-overlay");     if(typeof updateDriveModal === 'function') updateDriveModal(); }
      if (action === "dashboard") { openModal("dashboard-overlay"); if(typeof updateDashboardStats === 'function') updateDashboardStats(); }
      if (action === "theme")     { toggleTheme(); }
    });
  });

  document.querySelectorAll(".overlay").forEach(ov => {
    ov.addEventListener("click", e => {
      if (e.target === ov) ov.classList.add("hidden");
    });
  });

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
          document.getElementById("tree-local").style.display = "flex";
        }
      });
    });
  }

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

  document.querySelectorAll(".workspace-item").forEach(ws => {
    ws.addEventListener("click", () => {
      document.querySelectorAll(".workspace-item").forEach(w => w.classList.remove("active"));
      ws.classList.add("active");

      const wsType = ws.dataset.ws;
      openModal("drive-overlay");
      if(typeof updateDriveModal === 'function') updateDriveModal();

      const cloudPanel = document.getElementById("tree-cloud");
      const localPanel = document.getElementById("tree-local");
      const driveTabs  = document.getElementById("drive-tabs");

      if (!cloudPanel || !localPanel) return;

      if (driveTabs) {
        driveTabs.querySelectorAll(".pill-btn").forEach(b =>
          b.classList.remove("active", "cloud-active", "local-active"));
      }

      if (wsType === "drive") {
        cloudPanel.style.display = "";
        localPanel.style.display = "none";
        const btn = driveTabs && driveTabs.querySelector('[data-tab="cloud"]');
        if (btn) btn.classList.add("active", "cloud-active");
      } else if (wsType === "local") {
        cloudPanel.style.display = "none";
        localPanel.style.display = "flex";
        const btn = driveTabs && driveTabs.querySelector('[data-tab="local"]');
        if (btn) btn.classList.add("active", "local-active");
      } else {
        cloudPanel.style.display = "";
        localPanel.style.display = "flex";
      }
    });
  });
}

let _isDark = (localStorage.getItem("paiks-theme") || "dark") === "dark";

window.toggleTheme = function() {
  _isDark = !_isDark;
  const theme = _isDark ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("paiks-theme", theme);

  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.innerHTML = _isDark
      ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
      : '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  }

  document.querySelectorAll(".theme-toggle-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-theme") === theme);
  });
}
