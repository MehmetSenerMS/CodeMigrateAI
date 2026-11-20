from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer


client = QdrantClient(
    url="http://localhost:6333"
)

collection_name = "codemigrate_code"

info = client.get_collection(collection_name)

print("--- Qdrant Index Information ---")

print("Collection status:", info.status)
print("Points:", info.points_count)
print("Indexed vectors:", info.indexed_vectors_count)
print("HNSW configuration:", info.config.hnsw_config)
print("Optimizer configuration:", info.config.optimizer_config)



#%%
# Compare exact search with default approximate mode

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2",
    device="cpu"
)

query = "Find the method that checks whether a customer is active"

query_vector = model.encode(
    query,
    normalize_embeddings=True
).tolist()


# Exact search
exact_result = client.query_points(
    collection_name=collection_name,
    query=query_vector,
    search_params=models.SearchParams(
        exact=True
    ),
    limit=5,
    with_payload=True
)


# Allow approximate search
approx_result = client.query_points(
    collection_name=collection_name,
    query=query_vector,
    search_params=models.SearchParams(
        exact=False,
        hnsw_ef=32
    ),
    limit=5,
    with_payload=True
)


print("\n--- Exact Search ---")

for rank, hit in enumerate(exact_result.points, 1):
    print(
        rank,
        hit.payload["method_name"],
        round(hit.score, 4)
    )


print("\n--- Approximate Search Mode ---")

for rank, hit in enumerate(approx_result.points, 1):
    print(
        rank,
        hit.payload["method_name"],
        round(hit.score, 4)
    )


exact_ids = [hit.id for hit in exact_result.points]
approx_ids = [hit.id for hit in approx_result.points]

overlap = len(
    set(exact_ids) & set(approx_ids)
) / len(exact_ids)

print("\nTop-5 overlap:", round(overlap, 4))
print("Same ranking:", exact_ids == approx_ids)
