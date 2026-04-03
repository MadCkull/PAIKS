document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initMobileToggle === "function") initMobileToggle();
  if (typeof initSidebarCollapse === "function") initSidebarCollapse();
  if (typeof initToolbar === "function") initToolbar();
  if (typeof initNewChatInput === "function") initNewChatInput();
  if (typeof initChatUI === "function") initChatUI();
  if (typeof initModelDropdown === "function") initModelDropdown();

  if (typeof renderHistoryList === "function") renderHistoryList();
  
  const newChatBtn = document.querySelector(".btn-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", e => {
      e.preventDefault();
      if (typeof startNewChat === "function") startNewChat();
    });
  }

  if (typeof checkAuthStatus === "function") {
      const authed = await checkAuthStatus();
      if (!authed && window.location.pathname !== "/login/") {
        window.location.href = "/login/";
        return;
      }
      
      if (typeof updateConnectionUI === "function") await updateConnectionUI();
  }

  if (typeof initSearch === "function") initSearch();

  if (document.getElementById("stat-total")) {
    if(typeof loadDashboardStats === "function") loadDashboardStats();
    if(typeof loadFolderBadge === "function") loadFolderBadge();
  }
  
  if (document.getElementById("chat-thread")) {
    if(typeof loadRagStatus === "function") loadRagStatus();
    if(typeof loadLLMStatus === "function") loadLLMStatus();
    if(typeof updateDashboardStats === "function") updateDashboardStats();
    if(typeof updateToolbarContext === "function") updateToolbarContext();
    if(typeof updateSettingsModal === "function") updateSettingsModal();
  }

  if (document.getElementById("files-container")) {
    if(typeof loadFiles === "function") loadFiles();
    if(typeof loadRagStatus === "function") loadRagStatus();
    if(typeof loadLLMStatus === "function") loadLLMStatus();
    
    if (window.location.hash === "#ai-assistant-chat") {
      requestAnimationFrame(() => {
        const chat = document.getElementById("ai-assistant-chat");
        if (chat) chat.scrollIntoView({ behavior: "smooth", block: "start" });
        const rag = document.getElementById("rag-input");
        if (rag) setTimeout(() => rag.focus(), 400);
      });
    }
  }

  const fileSearchInput = document.getElementById("file-search-input");
  if (fileSearchInput) {
    let timeout;
    fileSearchInput.addEventListener("input", () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
          if(typeof loadFiles === "function") loadFiles(fileSearchInput.value.trim());
      }, 500);
    });
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get("connected") === "1") {
    if(typeof showToast === "function") showToast("Google Drive connected successfully!", "success");
    window.history.replaceState({}, "", window.location.pathname);
  }
});
