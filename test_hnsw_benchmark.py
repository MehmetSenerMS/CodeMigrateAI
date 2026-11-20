
import time
import numpy as np
from qdrant_client import QdrantClient, models

#%%
# ----#----------------------------------------------
# STEP 1 - Configuration
# --------------------------------------------------

client = QdrantClient(
    url="http://localhost:6333",
    timeout=60,
    prefer_grpc=False
)

collection_name = "codemigrate_hnsw_lab"

dimension = 384
n_queries = 50
top_k = 10

info = client.get_collection(collection_name)

if info.indexed_vectors_count < 4000:
    raise RuntimeError("HNSW index is not ready")

#%%
# --------------------------------------------------
# STEP 2 - Generate reproducible queries
# --------------------------------------------------

rng = np.random.default_rng(2026)

queries = rng.normal(
    size=(n_queries, dimension)
).astype(np.float32)

queries /= np.linalg.norm(
    queries,
    axis=1,
    keepdims=True
)

#%%
# --------------------------------------------------
# STEP 3 - Define search configurations
# --------------------------------------------------

configurations = {
    "Exact": models.SearchParams(exact=True),
    "HNSW ef=16": models.SearchParams(
        exact=False, hnsw_ef=16
    ),
    "HNSW ef=64": models.SearchParams(
        exact=False, hnsw_ef=64
    ),
    "HNSW ef=128": models.SearchParams(
        exact=False, hnsw_ef=128
    )
}


def run_search(query, params):

    start = time.perf_counter()

    result = client.query_points(
        collection_name=collection_name,
        query=query.tolist(),
        search_params=params,
        limit=top_k,
        with_payload=False,
        with_vectors=False
    )

    elapsed_ms = (
        time.perf_counter() - start
    ) * 1000

    ids = [hit.id for hit in result.points]

    return ids, elapsed_ms

#%%
# --------------------------------------------------
# STEP 4 - Warm up searches
# --------------------------------------------------

for params in configurations.values():

    for query in queries[:5]:
        run_search(query, params)

#%%
# --------------------------------------------------
# STEP 5 - Run benchmark
# --------------------------------------------------

results = {}

for name, params in configurations.items():

    all_ids = []
    latencies = []

    for query in queries:

        ids, elapsed = run_search(query, params)

        all_ids.append(ids)
        latencies.append(elapsed)

    results[name] = {
        "ids": all_ids,
        "latencies": latencies
    }

    print(f"Completed: {name}")

#%%
# --------------------------------------------------
# STEP 6 - Calculate Recall@10
# --------------------------------------------------

exact_ids = results["Exact"]["ids"]

print("\n--- HNSW Benchmark Results ---")

for name, data in results.items():

    recalls = []

    for query_index in range(n_queries):

        expected = set(
            exact_ids[query_index]
        )

        retrieved = set(
            data["ids"][query_index]
        )

        recall = (
            len(expected & retrieved)
            / len(expected)
        )

        recalls.append(recall)

    mean_recall = np.mean(recalls)

    median_latency = np.median(
        data["latencies"]
    )

    p95_latency = np.percentile(
        data["latencies"], 95
    )

    print(f"\n{name}")
    print(f"Recall@10: {mean_recall:.4f}")
    print(f"Median latency: {median_latency:.3f} ms")
    print(f"P95 latency: {p95_latency:.3f} ms")
