
import json
import time
import urllib.request
import numpy as np

from qdrant_client import QdrantClient, models


client = QdrantClient(
    url="http://127.0.0.1:6333",
    prefer_grpc=False
)
collection = "codemigrate_hnsw_lab"

rng = np.random.default_rng(42)
query = rng.normal(size=384).astype(np.float32)
query /= np.linalg.norm(query)

vector = query.tolist()

# Test 1: Python Qdrant Client
print("--- Python Client ---")

for i in range(3):
    start = time.perf_counter()

    client.query_points(
        collection_name=collection,
        query=vector,
        search_params=models.SearchParams(exact=True),
        limit=10,
        with_payload=False,
        with_vectors=False
    )

    elapsed = (time.perf_counter() - start) * 1000
    print(f"Request {i+1}: {elapsed:.2f} ms")


# Test 2: Direct REST API
print("\n--- Direct REST API ---")

url = (
    f"http://127.0.0.1:6333/"
    f"collections/{collection}/points/query"
)

body = json.dumps({
    "query": vector,
    "params": {"exact": True},
    "limit": 10,
    "with_payload": False,
    "with_vector": False
}).encode("utf-8")

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

for i in range(3):

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start = time.perf_counter()

    with opener.open(request, timeout=30) as response:
        result = json.load(response)

    elapsed = (time.perf_counter() - start) * 1000
    server_time = result["time"] * 1000

    print(
        f"Request {i+1}: "
        f"Client={elapsed:.2f} ms | "
        f"Server={server_time:.2f} ms"
    )
