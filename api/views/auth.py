import json
import secrets
import urllib.parse
import urllib.request
import urllib.error
import logging
from django.http import JsonResponse
from django.shortcuts import redirect
import os

from api.services.google_auth import get_creds, has_token, load_client_config, SCOPES
from api.services.google_drive import fetch_drive_user
from api.services.config import CREDENTIALS_PATH, TOKEN_PATH, SYNC_CACHE_PATH, STORAGE_DIR

logger = logging.getLogger(__name__)

OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/callback")

# Cached user info path  -  avoids hitting Google API on every status check
USER_CACHE_PATH = STORAGE_DIR / "user_cache.json"

def _load_cached_user():
    """Load cached Google user profile from disk."""
    try:
        if USER_CACHE_PATH.exists():
            return json.loads(USER_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

def _save_cached_user(user_info):
    """Cache Google user profile to disk."""
    try:
        USER_CACHE_PATH.write_text(json.dumps(user_info), encoding="utf-8")
    except Exception:
        pass

def status(request):
    """Auth status  -  fully local, no network calls."""
    creds = get_creds()
    if not creds:
        # Even if creds refresh failed, check if we HAVE a token (offline scenario)
        if has_token():
            cached_user = _load_cached_user()
            return JsonResponse({
                "authenticated": True,
                "offline": True,
                "user": cached_user or {"display_name": "Offline User", "email": ""}
            })
        return JsonResponse({"authenticated": False, "user": None})

    # We have valid creds  -  use cached user info (no network call)
    cached_user = _load_cached_user()
    if cached_user:
        return JsonResponse({"authenticated": True, "user": cached_user})

    # First time or cache missing  -  try to fetch (best effort, non-blocking)
    try:
        user = fetch_drive_user(creds)
        _save_cached_user(user)
        return JsonResponse({"authenticated": True, "user": user})
    except Exception:
        return JsonResponse({
            "authenticated": True,
            "user": {"display_name": "Connected", "email": ""}
        })

def get_url(request):
    if not CREDENTIALS_PATH.exists():
        return JsonResponse({"error": "credentials.json not found."}, status=400)

    client_id, _ = load_client_config()
    if not client_id:
        return JsonResponse({"error": "Invalid credentials.json format."}, status=400)

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state

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
    return JsonResponse({"url": auth_uri})

def callback(request):
    code = request.GET.get("code")
    if not code:
        return JsonResponse({"error": "Missing authorization code"}, status=400)

    client_id, client_secret = load_client_config()

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
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logger.error("Token exchange failed (network): %s", str(e))
        return JsonResponse({"error": f"Network error: {e}"}, status=502)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error("Token exchange failed: %s", error_body)
        return JsonResponse({"error": "Token exchange failed", "details": json.loads(error_body)}, status=400)

    token_info = {
        "token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token_info), encoding="utf-8")

    # Cache user profile immediately so we never need to call Google again for status
    try:
        from api.services.google_auth import get_creds as _get_creds
        creds = _get_creds()
        if creds:
            user = fetch_drive_user(creds)
            _save_cached_user(user)
    except Exception:
        pass

    return redirect("/?connected=1")

def disconnect(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    if SYNC_CACHE_PATH.exists():
        SYNC_CACHE_PATH.unlink()
    if USER_CACHE_PATH.exists():
        USER_CACHE_PATH.unlink()
    return JsonResponse({"status": "disconnected"})
