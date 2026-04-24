// ── PAIKSEventBus — Global SSE Connection Manager ──────────────
// Single persistent SSE connection that replaces ALL polling.
// Components register handlers via PAIKSEventBus.on('event_type', callback).

window.PAIKSEventBus = (function() {
  let _source = null;
  let _handlers = {};
  let _reconnectDelay = 3000;     // Start at 3s
  const MAX_RECONNECT = 30000;    // Cap at 30s
  let _reconnectTimer = null;
  let _connected = false;

  function _connect() {
    if (_source) {
      try { _source.close(); } catch(_) {}
    }

    _source = new EventSource(`${API_BASE}/events/status`);

    _source.onopen = function() {
      _connected = true;
      _reconnectDelay = 3000;  // Reset backoff on successful connect
      console.log("[SSE] Connected to event stream");
    };

    _source.onmessage = function(e) {
      try {
        const payload = JSON.parse(e.data);
        const type = payload.type;
        const data = payload.data;

        // Store latest data in the live stats cache
        if (type === "drive_stats" || type === "rag_status" || type === "llm_status") {
          if (!window._liveStats) window._liveStats = {};
          window._liveStats[type] = data;
          window._liveStats._lastUpdate = Date.now();
        }

        // Dispatch to all registered handlers for this event type
        if (_handlers[type]) {
          _handlers[type].forEach(fn => {
            try { fn(data); } catch(err) {
              console.warn(`[SSE] Handler error for ${type}:`, err.message);
            }
          });
        }
      } catch(err) {
        // Ignore parse errors (e.g. keepalive pings)
      }
    };

    _source.onerror = function() {
      _connected = false;
      _source.close();
      _source = null;

      // Exponential backoff reconnect
      if (_reconnectTimer) clearTimeout(_reconnectTimer);
      console.warn(`[SSE] Connection lost. Reconnecting in ${_reconnectDelay/1000}s...`);
      _reconnectTimer = setTimeout(() => {
        _reconnectDelay = Math.min(_reconnectDelay * 2, MAX_RECONNECT);
        _connect();
      }, _reconnectDelay);
    };
  }

  return {
    /** Register a handler for an event type. Returns an unsubscribe function. */
    on: function(eventType, handler) {
      if (!_handlers[eventType]) _handlers[eventType] = [];
      _handlers[eventType].push(handler);
      return function() {
        _handlers[eventType] = _handlers[eventType].filter(fn => fn !== handler);
      };
    },

    /** Start the SSE connection (called once on page load). */
    connect: function() {
      if (!_source) _connect();
    },

    /** Check if connected. */
    isConnected: function() {
      return _connected;
    },

    /** Get the latest cached data for a given event type. */
    getLatest: function(eventType) {
      return window._liveStats ? window._liveStats[eventType] : null;
    }
  };
})();


// ── Local Mouse Tracking for Glass Effects ───────────────────
// Calculates mouse position relative to each bubble individually,
// completely bypassing CSS 'background-attachment: fixed' offset bugs.
let _glassTicking = false;
document.addEventListener('mousemove', (e) => {
  if (!_glassTicking) {
    requestAnimationFrame(() => {
      // We target .cb__body because that's where the ::before glow pseudo-element lives
      const bubbles = document.querySelectorAll('.cb__body');
      
      // Phase 1: READ (Avoids layout thrashing by reading all bounds first)
      const rects = [];
      for (let i = 0; i < bubbles.length; i++) {
        rects.push(bubbles[i].getBoundingClientRect());
      }
      
      // Phase 2: WRITE
      for (let i = 0; i < bubbles.length; i++) {
        const rect = rects[i];
        
        // Calculate exact coordinates local to THIS specific bubble
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        bubbles[i].style.setProperty('--mouse-x', `${x}px`);
        bubbles[i].style.setProperty('--mouse-y', `${y}px`);
      }
      
      _glassTicking = false;
    });
    _glassTicking = true;
  }
});

// ── Page Initialization ─────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  // ── Core UI Init (always, never fails) ─────────────────────
  console.log("Calling initSidebarAutoReveal...");
  if (typeof initSidebarAutoReveal === "function") initSidebarAutoReveal();
  if (typeof initToolbar === "function") initToolbar();
  if (typeof initNewChatInput === "function") initNewChatInput();
  if (typeof initChatUI === "function") initChatUI();
  if (typeof renderHistoryList === "function") renderHistoryList();

  const newChatBtn = document.getElementById("btn-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", e => {
      e.preventDefault();
      if (typeof startNewChat === "function") startNewChat();
    });
  }

  // ── Mode Detection ─────────────────────────────────────────
  const mode = localStorage.getItem("paiks-mode"); // "local", "drive", or null

  if (!mode) {
    // No mode chosen yet  -  send to login
    if (window.location.pathname !== "/login/") {
      window.location.href = "/login/";
      return;
    }
  }

  if (mode === "drive") {
    // Drive mode  -  check if still authenticated
    try {
      const authed = typeof checkAuthStatus === "function" ? await checkAuthStatus() : false;
      if (!authed) {
        // Token gone/expired  -  still let them in but note they're offline
        console.warn("Drive mode but not authenticated  -  running in degraded mode");
      }
      if (typeof updateConnectionUI === "function") {
        try { await updateConnectionUI(); } catch(_) {}
      }
    } catch(_) {
      console.warn("Auth check failed  -  continuing offline");
    }
  }

  // In local mode, skip all auth checks
  if (mode === "local") {
    // Set sidebar display name to "Local User"
    const nameEl = document.getElementById("sidebar-user-name");
    if (nameEl) nameEl.textContent = "Local User";
  }

  window.appSettings = {};
  
  // ── Global Boot & Theme/Accent Init from Backend ─────────
  try {
    const res = await fetch(`${API_BASE}/system/settings`);
    window.appSettings = await res.json();
    if (window.appSettings.general && window.appSettings.general.accent_color && typeof setAccentColor === 'function') {
      // Pass null as second arg to indicate it's not from a swatch click, and true to prevent autosave
      setAccentColor(window.appSettings.general.accent_color, null, true);
    }
  } catch(e) {
    console.warn("Failed to load global settings from backend", e);
  }

  // ── Start Global SSE Connection ────────────────────────────
  // This single connection replaces all polling for drive stats,
  // RAG status, LLM status, and sync progress.
  PAIKSEventBus.connect();

  // ── Feature Init (independent, non-blocking) ──────────────
  if (typeof initSearch === "function") initSearch();

  const safeCall = async (fn) => { try { await fn(); } catch(e) { console.warn("Init failed:", e.message); } };

  // Track initialization time for minimum loading screen duration
  const initStartTime = Date.now();

  if (document.getElementById("chat-thread")) {
    // These fetch once on load to prime the UI before SSE starts pushing.
    // Once SSE events start arriving, they'll keep the UI current automatically.
    await safeCall(async () => {
      if (typeof loadRagStatus === "function") await loadRagStatus();
    });
    await safeCall(async () => {
      if (typeof loadLLMStatus === "function") await loadLLMStatus();
    });
    await safeCall(async () => {
      if (typeof updateDashboardStats === "function") await updateDashboardStats();
    });
    await safeCall(async () => {
      if (typeof updateToolbarContext === "function") await updateToolbarContext();
    });
    // Settings modal loads on-demand when opened, not on boot
  }

  // Enforce minimum 3 second loading screen
  const elapsed = Date.now() - initStartTime;
  if (elapsed < 3000) {
    await new Promise(r => setTimeout(r, 3000 - elapsed));
  }

  // Transition from loading state to normal state
  if (typeof setLoading === "function") setLoading(false);
  const appElement = document.getElementById("app");
  if (appElement) {
    appElement.style.opacity = "1";
    appElement.style.pointerEvents = "auto";
  }

  // ── Google Drive connected notification ────────────────────
  const params = new URLSearchParams(window.location.search);
  if (params.get("connected") === "1") {
    localStorage.setItem("paiks-mode", "drive");
    if (typeof showToast === "function") showToast("Google Drive connected successfully!", "success");
    window.history.replaceState({}, "", window.location.pathname);
  }
});

