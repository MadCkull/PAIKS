function getCsrfToken() {
  const name = "csrftoken";
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  
  if (options.method && options.method.toUpperCase() === "POST") {
    options.headers = options.headers || {};
    const token = getCsrfToken();
    if (token) options.headers["X-CSRFToken"] = token;
  }
  
  return fetch(url, { ...options, signal: controller.signal })
    .finally(() => clearTimeout(id));
}

function showToast(message, type = "info") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(40px)";
    toast.style.transition = "all .3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

function formatSize(bytes) {
  if (!bytes || isNaN(bytes)) return "0 B";
  const b = parseInt(bytes, 10);
  if (b === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let size = b;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return size.toFixed(i === 0 ? 0 : 1) + " " + units[i];
}

function formatBytes(bytes) {
  return formatSize(bytes);
}

function formatMimeType(mime) {
  if (!mime) return "File";
  const map = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.folder": "Folder",
    "application/vnd.google-apps.form": "Google Form",
    "application/pdf": "PDF",
    "image/jpeg": "JPEG Image",
    "image/png": "PNG Image",
    "video/mp4": "MP4 Video",
    "text/plain": "Text File",
  };
  return map[mime] || mime.split("/").pop().split(".").pop();
}

function getFileEmoji(mime) {
  if (!mime) return "📄";
  if (mime.includes("folder")) return "📁";
  if (mime.includes("document") || mime.includes("doc")) return "📝";
  if (mime.includes("spreadsheet") || mime.includes("sheet") || mime.includes("excel") || mime.includes("csv")) return "📊";
  if (mime.includes("presentation") || mime.includes("slide") || mime.includes("powerpoint")) return "📽️";
  if (mime.includes("pdf")) return "📕";
  if (mime.includes("image")) return "🖼️";
  if (mime.includes("video")) return "🎬";
  if (mime.includes("audio")) return "🎵";
  if (mime.includes("zip") || mime.includes("archive") || mime.includes("compressed")) return "📦";
  if (mime.includes("python") || mime.endsWith(".py")) return "🐍";
  if (mime.includes("form")) return "📋";
  if (mime.includes("text") || mime.includes("plain")) return "📃";
  return "📄";
}

function getFileClass(mime) {
  if (!mime) return "other";
  if (mime.includes("folder")) return "folder";
  if (mime.includes("document") || mime.includes("doc")) return "doc";
  if (mime.includes("spreadsheet") || mime.includes("sheet")) return "sheet";
  if (mime.includes("presentation") || mime.includes("slide")) return "slide";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("image")) return "img";
  return "other";
}

function timeAgo(isoString) {
  if (!isoString || isoString === "Not synced yet") return "Never";
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (diff < 60)   return diff + "s ago";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
}

function removeAuthGuard() {
  const guard = document.getElementById("auth-guard");
  if (guard) {
    guard.style.opacity = "0";
    guard.style.transition = "opacity 0.4s ease";
    setTimeout(() => guard.remove(), 400);
  }
}
