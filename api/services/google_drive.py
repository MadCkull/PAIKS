from googleapiclient.discovery import build

# Only these MIME types will be synced, browsed, and searched.
ALLOWED_MIME_TYPES = [
    "text/plain",                                                                 # .txt
    "text/csv",                                                                   # .csv
    "application/vnd.google-apps.document",                                      # Google Docs
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",   # .docx
    "application/msword",                                                         # .doc (legacy)
]

# Pre-built Drive API mimeType OR clause
MIME_FILTER = "(" + " or ".join(f"mimeType = '{m}'" for m in ALLOWED_MIME_TYPES) + ")"

def drive_service(creds):
    return build("drive", "v3", credentials=creds)

def fetch_drive_user(creds):
    """Return Google account display name, email, and photo from Drive about API."""
    try:
        service = drive_service(creds)
        about = service.about().get(fields="user").execute()
        u = about.get("user") or {}
        return {
            "display_name": (u.get("displayName") or "").strip(),
            "email": (u.get("emailAddress") or "").strip(),
            "photo_url": (u.get("photoLink") or "").strip(),
        }
    except Exception:
        return {"display_name": "", "email": "", "photo_url": ""}
