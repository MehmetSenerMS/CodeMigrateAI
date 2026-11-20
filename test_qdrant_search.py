
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models

#%%
# --------------------------------------------------
# STEP 1 - Connect to Qdrant
# --------------------------------------------------

client = QdrantClient(
    url="http://localhost:6333"
)

collection_name = "codemigrate_code"

assert client.collection_exists(collection_name)

#%%
# --------------------------------------------------
# STEP 2 - Load embedding model
# --------------------------------------------------

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2",
    device="cpu"
)

#%%
# --------------------------------------------------
# STEP 3 - Encode user query
# --------------------------------------------------

query = (
    "Find the method that checks "
    "whether a customer is active"
)

query_vector = model.encode(
    query,
    convert_to_numpy=True,
    normalize_embeddings=True
)

assert query_vector.shape == (384,)

print("Query embedding shape:", query_vector.shape)

#%%
# --------------------------------------------------
# STEP 4 - Search Qdrant
# --------------------------------------------------

search_result = client.query_points(
    collection_name=collection_name,
    query=query_vector.tolist(),
    search_params=models.SearchParams(
        exact=True # Exact nearest-neighbor search
    ),
    limit=5,
    with_payload=True,
    with_vectors=False
)

#%%
# --------------------------------------------------
# STEP 5 - Display search results
# --------------------------------------------------

print("\n--- Qdrant Search Results ---")

for rank, hit in enumerate(search_result.points, start=1):

    payload = hit.payload

    print(f"\nRank: {rank}")
    print("Class:", payload["class_name"])
    print("Method:", payload["method_name"])
    print(f"Similarity: {hit.score:.4f}")
    print("File:", payload["file_path"])

#%%
# --------------------------------------------------
# STEP 6 - Verify expected method
# --------------------------------------------------

method_names = [
    hit.payload["method_name"]
    for hit in search_result.points
]

assert "IsCustomerActive" in method_names

expected_rank = method_names.index(
    "IsCustomerActive"
) + 1

print("\nExpected method rank:", expected_rank)
print("Qdrant semantic search: PASS")
