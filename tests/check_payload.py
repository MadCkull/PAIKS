from api.services.rag.indexer import get_qdrant_client, LOCAL_COLLECTION
client = get_qdrant_client()

if client.collection_exists(LOCAL_COLLECTION):
    points, _ = client.scroll(
        collection_name=LOCAL_COLLECTION,
        limit=1,
        with_payload=True
    )
    if points:
        print("RAW PAYLOAD KEYS:", points[0].payload.keys())
        print("RAW PAYLOAD:", points[0].payload)
    else:
        print("No points found in local collection.")
else:
    print("Collection does not exist.")
