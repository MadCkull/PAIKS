async function fetchAuthState() {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/auth/status`, {}, 5000);
    return await res.json();
  } catch {
    return { authenticated: false, user: null };
  }
}

async function checkAuthStatus() {
  const data = await fetchAuthState();
  return !!data.authenticated;
}

function getInitials(name) {
  if (!name) return "?";
  const clean = name.trim();
  if (clean.includes("@")) return clean[0].toUpperCase();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

function syncSidebarIdentity(connected, user) {
  const nameEl = document.getElementById("sidebar-user-name");
  if (!nameEl) return;
  const mode = localStorage.getItem("paiks-mode");

  if (connected && user) {
    nameEl.textContent = (user.display_name || user.email || "Connected").trim();
  } else if (mode === "local") {
    nameEl.textContent = "Local User";
  } else {
    nameEl.textContent = "Guest";
  }
}

async function updateConnectionUI() {
  const data = await fetchAuthState();
  const connected = !!data.authenticated;
  const user = (data.user && typeof data.user === "object") ? data.user : {};

  const sidebarDot = document.getElementById("sidebar-connection-dot");
  if (sidebarDot) {
    sidebarDot.className = `connection-dot ${connected ? "connected" : "disconnected"}`;
  }

  const subEl = document.getElementById("connection-label");
  const badgeEl = document.getElementById("drive-profile-badge");
  const driveTitle = document.getElementById("drive-link-title");
  if (driveTitle) driveTitle.textContent = "Google Drive";

  if (subEl) {
    if (connected) {
      const email = (user.email || "").trim();
      const gname = (user.display_name || "").trim();
      subEl.textContent = gname && email ? `${gname} · ${email}` : email || gname || "Linked";
    } else {
      subEl.textContent = localStorage.getItem("paiks-mode") === "local" ? "Local mode" : "Not linked";
    }
  }
  if (badgeEl) {
    badgeEl.textContent = connected ? "Linked" : "";
    badgeEl.hidden = !connected;
  }

  syncSidebarIdentity(connected, user);

  const connectBtn = document.getElementById("btn-connect");
  const disconnectBtn = document.getElementById("btn-disconnect");
  if (connectBtn) connectBtn.classList.toggle("hidden", connected);
  if (disconnectBtn) disconnectBtn.classList.toggle("hidden", !connected);

  const statusBadge = document.getElementById("auth-status-badge");
  if (statusBadge) {
    statusBadge.className = `badge ${connected ? "badge-green" : "badge-dim"}`;
    statusBadge.innerHTML = connected
      ? '<span class="connection-dot connected"></span> Connected'
      : '<span class="connection-dot disconnected"></span> Not Connected';
  }

  return connected;
}
