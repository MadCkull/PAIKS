import json
import logging
from google.oauth2.credentials import Credentials
from .config import CREDENTIALS_PATH, TOKEN_PATH

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

def load_client_config():
    """Load client_id and client_secret from credentials.json."""
    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    cfg = data.get("web") or data.get("installed") or {}
    return cfg.get("client_id"), cfg.get("client_secret")

def get_creds():
    """Return valid Credentials or None. Never blocks on network."""
    if not TOKEN_PATH.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except Exception as e:
        logger.warning("Failed to load token.json: %s", e)
        return None

    if creds and creds.valid:
        return creds

    # Token expired  -  try refresh
    if creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            # We skip the global socket timeout as it causes race conditions on Windows/Django
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return creds
        except Exception as e:
            logger.warning("Token refresh failed (offline?): %s", e)
            return None

    return None

def has_token():
    """Check if a token file exists at all (user was previously authenticated)."""
    return TOKEN_PATH.exists()
