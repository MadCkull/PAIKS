import json
import os
import pathlib

from flask import Flask, jsonify, request, redirect, session, url_for
from flask_cors import CORS
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)
app.secret_key = "paiks-dev-secret-key-change-in-prod"
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = pathlib.Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
SYNC_CACHE_PATH = BASE_DIR / "drive_cache.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "flask-api"})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.get("/auth/status")
def auth_status():
    creds = _get_creds()
    return jsonify({"authenticated": creds is not None})


@app.get("/auth/url")
def auth_url():
    if not CREDENTIALS_PATH.exists():
        return jsonify({"error": "credentials.json not found. Download it from Google Cloud Console."}), 400
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri="http://127.0.0.1:5001/auth/callback",
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return jsonify({"url": authorization_url})


@app.get("/auth/callback")
def auth_callback():
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri="http://127.0.0.1:5001/auth/callback",
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    TOKEN_PATH.write_text(creds.to_json())
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

@app.get("/drive/files")
def drive_files():
    creds = _get_creds()
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    page_token = request.args.get("pageToken")
    page_size = int(request.args.get("pageSize", 20))
    query = request.args.get("q", "")

    service = _drive_service(creds)
    params = {
        "pageSize": page_size,
        "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink, thumbnailLink)",
        "orderBy": "modifiedTime desc",
    }
    if page_token:
        params["pageToken"] = page_token
    if query:
        params["q"] = f"name contains '{query}' and trashed = false"
    else:
        params["q"] = "trashed = false"

    results = service.files().list(**params).execute()
    return jsonify({
        "files": results.get("files", []),
        "nextPageToken": results.get("nextPageToken"),
    })


@app.post("/drive/sync")
def drive_sync():
    creds = _get_creds()
    if not creds:
        return jsonify({"error": "Not authenticated"}), 401

    service = _drive_service(creds)
    all_files = []
    page_token = None

    while True:
        params = {
            "pageSize": 100,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink)",
            "q": "trashed = false",
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
    }
    _save_cache(cache_data)
    return jsonify({"status": "synced", "total": len(all_files), "synced_at": cache_data["synced_at"]})


@app.get("/drive/stats")
def drive_stats():
    creds = _get_creds()
    cache = _load_cache()
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

    # Live search from Drive API
    service = _drive_service(creds)
    escaped = query.replace("'", "\\'")
    results = (
        service.files()
        .list(
            q=f"name contains '{escaped}' and trashed = false",
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
