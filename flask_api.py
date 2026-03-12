import json
import os
import pathlib
import secrets
import urllib.parse
import urllib.request

from flask import Flask, jsonify, request, redirect, session, url_for
from flask_cors import CORS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)
app.secret_key = "paiks-dev-secret-key-change-in-prod"
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = pathlib.Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
SYNC_CACHE_PATH = BASE_DIR / "drive_cache.json"
FOLDER_CONFIG_PATH = BASE_DIR / "folder_config.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

OAUTH_REDIRECT_URI = "http://localhost/PAIKS/oauth2callback"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_client_config():
    """Load client_id and client_secret from credentials.json."""
    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    # Handle both 'web' and 'installed' credential types
    cfg = data.get("web") or data.get("installed") or {}
    return cfg.get("client_id"), cfg.get("client_secret")


def _get_creds():
    """Return valid Credentials or None."""
    if not TOKEN_PATH.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds
    return None


def _drive_service(creds):
    return build("drive", "v3", credentials=creds)


def _load_cache():
    if SYNC_CACHE_PATH.exists():
        return json.loads(SYNC_CACHE_PATH.read_text(encoding="utf-8"))
    return {"files": [], "synced_at": None}


def _save_cache(data):
    SYNC_CACHE_PATH.write_text(json.dumps(data, default=str), encoding="utf-8")


def _load_folder_config():
    """Return {"folder_id": ..., "folder_name": ...} or None if not set."""
    if FOLDER_CONFIG_PATH.exists():
        try:
            return json.loads(FOLDER_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_folder_config(folder_id, folder_name):
    FOLDER_CONFIG_PATH.write_text(
        json.dumps({"folder_id": folder_id, "folder_name": folder_name}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "flask-api"})


# ---------------------------------------------------------------------------
# Auth (manual OAuth 2.0 — no PKCE)
# ---------------------------------------------------------------------------

@app.get("/auth/status")
def auth_status():
    creds = _get_creds()
    return jsonify({"authenticated": creds is not None})


@app.get("/auth/url")
def auth_url():
    if not CREDENTIALS_PATH.exists():
        return jsonify({"error": "credentials.json not found. Download it from Google Cloud Console."}), 400
    client_id, _ = _load_client_config()
    if not client_id:
        return jsonify({"error": "Invalid credentials.json format."}), 400

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_uri = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return jsonify({"url": auth_uri})


@app.get("/auth/callback")
def auth_callback():
    """Receives the auth code forwarded from the Apache bridge."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    client_id, client_secret = _load_client_config()

    # Exchange auth code for tokens via direct POST (no PKCE needed)
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        app.logger.error("Token exchange failed: %s", error_body)
        return jsonify({"error": "Token exchange failed", "details": json.loads(error_body)}), 400

    # Save token in the format google.oauth2.credentials expects
    token_info = {
        "token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token_info), encoding="utf-8")

    # Redirect back to Django home
    return redirect("http://127.0.0.1:8000/?connected=1")


@app.post("/auth/disconnect")
def auth_disconnect():
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    if SYNC_CACHE_PATH.exists():
        SYNC_CACHE_PATH.unlink()
    return jsonify({"status": "disconnected"})


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

@app.get("/drive/folders")
def drive_list_folders():
    """Return all folders the user owns/can see so they can pick one."""
    creds = _get_creds()
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        service = _drive_service(creds)
        folders = []
        page_token = None
        while True:
            params = {
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, modifiedTime)",
                "q": "mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                "orderBy": "name",
            }
            if page_token:
                params["pageToken"] = page_token
            results = service.files().list(**params).execute()
            folders.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        current = _load_folder_config()
        return jsonify({
            "folders": folders,
            "current_folder": current,
        })
    except Exception as e:
        app.logger.error("drive_list_folders error: %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.post("/drive/set-folder")
def drive_set_folder():
    """Save the user's chosen folder. Pass {} to clear (sync all Drive)."""
    payload = request.get_json(silent=True) or {}
    folder_id = payload.get("folder_id", "").strip()
    folder_name = payload.get("folder_name", "").strip()

    if folder_id:
        _save_folder_config(folder_id, folder_name)
        # Wipe stale cache so next sync reflects the new scope
        if SYNC_CACHE_PATH.exists():
            SYNC_CACHE_PATH.unlink()
        return jsonify({"status": "saved", "folder_id": folder_id, "folder_name": folder_name})
    else:
        # Clear folder config → sync entire Drive
        if FOLDER_CONFIG_PATH.exists():
            FOLDER_CONFIG_PATH.unlink()
        if SYNC_CACHE_PATH.exists():
            SYNC_CACHE_PATH.unlink()
        return jsonify({"status": "cleared"})


@app.get("/drive/folder-config")
def drive_folder_config():
    return jsonify(_load_folder_config() or {})


@app.get("/drive/files")
def drive_files():
    creds = _get_creds()
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        page_token = request.args.get("pageToken")
        page_size = int(request.args.get("pageSize", 20))
        name_query = request.args.get("q", "")

        folder_cfg = _load_folder_config()
        service = _drive_service(creds)

        # Build query — always scope to the chosen folder if one is set
        conditions = ["trashed = false"]
        if folder_cfg and folder_cfg.get("folder_id"):
            conditions.append(f"'{folder_cfg['folder_id']}' in parents")
        if name_query:
            escaped = name_query.replace("'", "\\'")
            conditions.append(f"name contains '{escaped}'")

        params = {
            "pageSize": page_size,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink, thumbnailLink)",
            "orderBy": "modifiedTime desc",
            "q": " and ".join(conditions),
        }
        if page_token:
            params["pageToken"] = page_token

        results = service.files().list(**params).execute()
        return jsonify({
            "files": results.get("files", []),
            "nextPageToken": results.get("nextPageToken"),
            "folder": folder_cfg,
        })
    except Exception as e:
        app.logger.error("drive_files error: %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.post("/drive/sync")
def drive_sync():
    creds = _get_creds()
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    folder_cfg = _load_folder_config()
    service = _drive_service(creds)
    all_files = []
    page_token = None

    # Scope the sync to the chosen folder (if any)
    base_q = "trashed = false"
    if folder_cfg and folder_cfg.get("folder_id"):
        base_q = f"'{folder_cfg['folder_id']}' in parents and trashed = false"

    while True:
        params = {
            "pageSize": 100,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink)",
            "q": base_q,
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        results = service.files().list(**params).execute()
        all_files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    from datetime import datetime, timezone
    cache_data = {
        "files": all_files,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_files),
        "folder": folder_cfg,
    }
    _save_cache(cache_data)
    return jsonify({
        "status": "synced",
        "total": len(all_files),
        "synced_at": cache_data["synced_at"],
        "folder": folder_cfg,
    })


@app.get("/drive/stats")
def drive_stats():
    creds = _get_creds()
    cache = _load_cache()
    folder_cfg = _load_folder_config()
    file_types = {}
    for f in cache.get("files", []):
        mime = f.get("mimeType", "unknown")
        short = mime.split("/")[-1].split(".")[-1]
        file_types[short] = file_types.get(short, 0) + 1

    return jsonify({
        "authenticated": creds is not None,
        "documents_total": len(cache.get("files", [])),
        "synced_at": cache.get("synced_at", "Not synced yet"),
        "file_types": file_types,
        "folder": folder_cfg,
    })


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.post("/search")
def search_documents():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    creds = _get_creds()
    if not creds:
        # Fallback: search cached files
        cache = _load_cache()
        results = [
            {
                "id": f["id"],
                "name": f["name"],
                "mimeType": f.get("mimeType", ""),
                "webViewLink": f.get("webViewLink", ""),
                "modifiedTime": f.get("modifiedTime", ""),
            }
            for f in cache.get("files", [])
            if query.lower() in f.get("name", "").lower()
        ]
        return jsonify({"query": query, "results": results[:20], "source": "cache"})

    # Live search from Drive API — scoped to chosen folder if set
    folder_cfg = _load_folder_config()
    service = _drive_service(creds)
    escaped = query.replace("'", "\\'")
    conditions = [f"name contains '{escaped}'", "trashed = false"]
    if folder_cfg and folder_cfg.get("folder_id"):
        conditions.append(f"'{folder_cfg['folder_id']}' in parents")
    results = (
        service.files()
        .list(
            q=" and ".join(conditions),
            pageSize=20,
            fields="files(id, name, mimeType, modifiedTime, webViewLink, iconLink, size)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    return jsonify({"query": query, "results": results.get("files", []), "source": "live"})


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local dev
    app.run(host="127.0.0.1", port=5001, debug=True)
