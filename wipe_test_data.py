import os
import sys
import django

# Setup Django context
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import DocumentTrack, SyncJob
from api.services.rag.indexer import get_qdrant_client, LOCAL_COLLECTION, CLOUD_COLLECTION

print("Wiping DocumentTrack and SyncJob tables...")
DocumentTrack.objects.all().delete()
SyncJob.objects.all().delete()

print("Dropping Qdrant collections...")
client = get_qdrant_client()
if client.collection_exists(LOCAL_COLLECTION):
    client.delete_collection(LOCAL_COLLECTION)
    print(f"Dropped {LOCAL_COLLECTION}")
if client.collection_exists(CLOUD_COLLECTION):
    client.delete_collection(CLOUD_COLLECTION)
    print(f"Dropped {CLOUD_COLLECTION}")

print("Wipe complete!")
