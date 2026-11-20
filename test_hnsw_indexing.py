
import numpy as np

from qdrant_client import QdrantClient, models

#%%
# --------------------------------------------------
# STEP 1 - Configuration
# --------------------------------------------------

client = QdrantClient(
    url="http://localhost:6333",
    timeout=60
)

collection_name = "codemigrate_hnsw_lab"

n_vectors = 4000
dimension = 384
batch_size = 200

#%%
# --------------------------------------------------
# STEP 2 - Create experimental collection
# --------------------------------------------------

if not client.collection_exists(collection_name):

    client.create_collection(
        collection_name=collection_name,

        vectors_config=models.VectorParams(
            size=dimension,
            distance=models.Distance.COSINE
        ),

        hnsw_config=models.HnswConfigDiff(
            m=16,
            ef_construct=100,
            full_scan_threshold=10
        ),

        # Initially avoid indexing during upload
        optimizers_config=models.OptimizersConfigDiff(
            indexing_threshold=20000
        )
    )

    print("Experimental collection created")

#%%
# --------------------------------------------------
# STEP 3 - Generate synthetic vectors
# --------------------------------------------------

rng = np.random.default_rng(seed=42)

vectors = rng.normal(
    size=(n_vectors, dimension)
).astype(np.float32)

# L2 normalization
vectors /= np.linalg.norm(
    vectors,
    axis=1,
    keepdims=True
)

print("Vector matrix:", vectors.shape)

#%%
# --------------------------------------------------
# STEP 4 - Upload vectors
# --------------------------------------------------

existing_count = client.count(
    collection_name=collection_name,
    exact=True
).count

if existing_count != n_vectors:

    for start in range(0, n_vectors, batch_size):

        end = min(start + batch_size, n_vectors)

        points = [
            models.PointStruct(
                id=i,
                vector=vectors[i].tolist()
            )
            for i in range(start, end)
        ]

        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True
        )

        print(f"Uploaded {end}/{n_vectors}")

else:
    print("All vectors already uploaded")

#%%
# --------------------------------------------------
# STEP 5 - Enable HNSW indexing
# --------------------------------------------------

client.update_collection(
    collection_name=collection_name,
    optimizers_config=models.OptimizersConfigDiff(
        indexing_threshold=256
    )
)

print("\nHNSW indexing requested")

#%%
# --------------------------------------------------
# STEP 6 - Inspect collection
# --------------------------------------------------

info = client.get_collection(collection_name)

exact_count = client.count(
    collection_name=collection_name,
    exact=True
).count

print("\n--- HNSW Index Status ---")
print("Points:", exact_count)
print("Indexed vectors:", info.indexed_vectors_count)
print("Status:", info.status)
print("Optimizer status:", info.optimizer_status)
print("HNSW config:", info.config.hnsw_config)
print("Optimizer config:", info.config.optimizer_config)
