from django.urls import path
from .views import health, auth, drive, search, rag, llm, local_files

urlpatterns = [
    # Health
    path("health",              health.check),
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
    path("drive/set-folder",    drive.set_folder),
    path("drive/folder-config", drive.folder_config),
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
    path("local/upload",        local_files.upload),
    path("local/delete",        local_files.delete),
]
