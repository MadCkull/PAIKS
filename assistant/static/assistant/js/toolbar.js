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
      if (action === "knowledge") window.openKnowledgeInspector();
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
}

/* ── Sidebar Auto-Reveal ─────────────────────────────────────── */

function initSidebarAutoReveal() {
  const trigger = document.getElementById("sidebar-trigger");
  const sidebar = document.getElementById("app-sidebar");
  console.log("Init sidebar auto-reveal:", trigger, sidebar);
  if (!trigger || !sidebar) return;

  let closeTimer = null;
  const CLOSE_DELAY = 300; // ms before closing after mouse leaves

  function expandSidebar() {
    console.log("Expanding sidebar...");
    if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
    sidebar.classList.add("expanded");
    trigger.classList.add("expanded");
  }

  function schedulClose() {
    if (closeTimer) clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      sidebar.classList.remove("expanded");
      trigger.classList.remove("expanded");
      closeTimer = null;
    }, CLOSE_DELAY);
  }

  // ── Desktop: mouseenter / mouseleave ──
  trigger.addEventListener("mouseenter", expandSidebar);
  sidebar.addEventListener("mouseenter", expandSidebar);
  trigger.addEventListener("mouseleave", schedulClose);
  sidebar.addEventListener("mouseleave", schedulClose);

  // ── Touch support ──
  trigger.addEventListener("touchstart", (e) => {
    e.preventDefault();
    if (sidebar.classList.contains("expanded")) {
      sidebar.classList.remove("expanded");
    } else {
      expandSidebar();
    }
  }, { passive: false });

  // Close on tap outside (touch devices)
  document.addEventListener("touchstart", (e) => {
    if (!sidebar.contains(e.target) && !trigger.contains(e.target)) {
      sidebar.classList.remove("expanded");
    }
  });

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar.classList.contains("expanded")) {
      sidebar.classList.remove("expanded");
    }
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
