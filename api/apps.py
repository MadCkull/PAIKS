from django.apps import AppConfig
import os
import sys

class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return
            
        if 'makemigrations' in sys.argv or 'migrate' in sys.argv or 'test' in sys.argv or 'pytest' in sys.modules:
            return
            
        from api.services.sync_manager import start_sync_engine
        from api.services.rag.retrieval.reranker import warmup_reranker
        from api.services.status_broadcaster import start_status_broadcaster
        import threading
        
        # Pre-load the reranker model so the first search is instant
        threading.Thread(target=warmup_reranker, daemon=True).start()
        
        # Start the real-time status broadcaster (replaces all frontend polling)
        start_status_broadcaster()
        
        # Start the sync engine (watchdog + background indexer)
        threading.Thread(target=start_sync_engine, daemon=True).start()

