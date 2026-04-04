document.addEventListener("DOMContentLoaded", async () => {
  // ── Core UI Init (always, never fails) ─────────────────────
  if (typeof initSidebarCollapse === "function") initSidebarCollapse();
  if (typeof initToolbar === "function") initToolbar();
  if (typeof initNewChatInput === "function") initNewChatInput();
  if (typeof initChatUI === "function") initChatUI();
  if (typeof renderHistoryList === "function") renderHistoryList();

  const newChatBtn = document.querySelector(".btn-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", e => {
      e.preventDefault();
      if (typeof startNewChat === "function") startNewChat();
    });
  }

  // ── Mode Detection ─────────────────────────────────────────
  const mode = localStorage.getItem("paiks-mode"); // "local", "drive", or null

  if (!mode) {
    // No mode chosen yet — send to login
    if (window.location.pathname !== "/login/") {
      window.location.href = "/login/";
      return;
    }
  }

  if (mode === "drive") {
    // Drive mode — check if still authenticated
    try {
      const authed = typeof checkAuthStatus === "function" ? await checkAuthStatus() : false;
      if (!authed) {
        // Token gone/expired — still let them in but note they're offline
        console.warn("Drive mode but not authenticated — running in degraded mode");
      }
      if (typeof updateConnectionUI === "function") {
        try { await updateConnectionUI(); } catch(_) {}
      }
    } catch(_) {
      console.warn("Auth check failed — continuing offline");
    }
  }

  // In local mode, skip all auth checks
  if (mode === "local") {
    // Set sidebar user name to "Local User"
    const nameEl = document.getElementById("sidebar-user-name");
    if (nameEl) nameEl.textContent = "Local User";
  }

  // Remove auth guard immediately — don't wait for anything
  if (typeof removeAuthGuard === "function") removeAuthGuard();

  // ── Feature Init (independent, non-blocking) ──────────────
  if (typeof initSearch === "function") initSearch();

  // Each of these is wrapped independently so one failure doesn't block others
  const safeCall = async (fn) => { try { await fn(); } catch(e) { console.warn("Init failed:", e.message); } };

  if (document.getElementById("chat-thread")) {
    safeCall(() => typeof loadRagStatus === "function" && loadRagStatus());
    safeCall(() => typeof loadLLMStatus === "function" && loadLLMStatus());
    safeCall(() => typeof updateDashboardStats === "function" && updateDashboardStats());
    safeCall(() => typeof updateToolbarContext === "function" && updateToolbarContext());
    // Settings modal loads on-demand when opened, not on boot
  }

  // ── Google Drive connected notification ────────────────────
  const params = new URLSearchParams(window.location.search);
  if (params.get("connected") === "1") {
    localStorage.setItem("paiks-mode", "drive");
    if (typeof showToast === "function") showToast("Google Drive connected successfully!", "success");
    window.history.replaceState({}, "", window.location.pathname);
  }
});
