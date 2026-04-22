from googleapiclient.discovery import build

# Only these MIME types will be synced, browsed, and searched.
ALLOWED_MIME_TYPES = [
    "text/plain",                                                                 # .txt
    "text/csv",                                                                   # .csv
    "application/pdf",                                                            # .pdf
    "application/vnd.google-apps.document",                                      # Google Docs
    "application/vnd.google-apps.spreadsheet",                                   # Google Sheets
    "application/vnd.google-apps.presentation",                                  # Google Slides
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",   # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",          # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    "application/vnd.ms-excel",                                                   # .xls
]

# Pre-built Drive API mimeType OR clause
MIME_FILTER = "(" + " or ".join(f"mimeType = '{m}'" for m in ALLOWED_MIME_TYPES) + ")"

def drive_service(creds):
    """
    Returns a Google Drive v3 service instance.
    Includes explicit timeouts to prevent SSL handshake hangs.
    """
    import httplib2
    try:
        # Create a custom HTTP object with a generous timeout
        http = httplib2.Http(timeout=15)
        # We use static_discovery=False to avoid the file_cache warning and potential IO hangs
        return build("drive", "v3", credentials=creds, http=http, static_discovery=False)
    except Exception as e:
        # Fallback to default if something goes wrong with parameters
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
