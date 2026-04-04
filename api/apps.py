from django.apps import AppConfig
import os
import sys

class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return
            
        if 'makemigrations' in sys.argv or 'migrate' in sys.argv or 'test' in sys.argv:
            return
            
        from api.services.sync_manager import start_sync_engine
        import threading
        
        # Start in a separate thread so it doesn't block Django startup
        threading.Thread(target=start_sync_engine, daemon=True).start()
