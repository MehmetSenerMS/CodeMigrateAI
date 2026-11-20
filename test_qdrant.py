
from qdrant_client import QdrantClient, models


# 1. Connect to Qdrant server
client = QdrantClient(
    url="http://localhost:6333",
    timeout=10
)

collection_name = "codemigrate_code"


# 2. Create collection if it does not exist
if not client.collection_exists(collection_name):

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE
        )
    )

    print("Collection created")

else:
    print("Collection already exists")


# 3. Inspect collection configuration
info = client.get_collection(collection_name)

print("\n--- Qdrant Collection ---")
print("Name:", collection_name)
print("Status:", info.status)
print("Points:", info.points_count)
print("Vector configuration:", info.config.params.vectors)
