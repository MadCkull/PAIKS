from django.urls import path
from .views import health, auth, drive, search, rag, llm, local_files, system, events

urlpatterns = [
    # ── Health & System ──
    path('health', health.check),
    path('events/status', events.event_stream),
    # Auth
    path("auth/status",         auth.status),
    path("auth/url",            auth.get_url),
    path("auth/callback",       auth.callback),
    path("auth/disconnect",     auth.disconnect),
    # Drive
    path("drive/files",         drive.files),
    path("drive/folders",       drive.folders),
    path("drive/sync",          drive.sync),
    path("drive/stats",         drive.stats),
    path("drive/selection",     drive.selection),
    path("drive/selections",    drive.selections),
    path("drive/set-folder",    drive.set_folder),
    path("drive/folder-config", drive.folder_config),
    # System
    path("system/settings",      system.settings_view),
    path("system/browse",        system.browse_local),
    path("system/logs",          system.logs),
    # Search
    path("search",              search.search),
    # RAG
    path("rag/status",          rag.status),
    path("rag/ingest",          rag.ingest),
    path("rag/search",          rag.search),
    path("rag/llm/status",      llm.status),
    path("rag/llm/config",      llm.config),
    # Local files
    path("local/files",         local_files.list_files),
    path("local/tree",          local_files.get_tree),
    path("local/upload",        local_files.upload),
    path("local/delete",        local_files.delete),
]
