
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models

from codemigrate.chunking.code_chunker import CodeChunker

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
# STEP 2 - Extract C# methods
# --------------------------------------------------

source_files = [
    "legacy/CustomerService.cs",
    "legacy/MultipleServices.cs",
    "legacy/GenericRepository.cs",
    "legacy/GenericMethodService.cs",
    "legacy/PremiumCustomerService.cs"
]

chunks = []

for file_path in source_files:

    chunker = CodeChunker(file_path)

    chunks.extend(
        chunker.extract_methods()
    )

print("Extracted chunks:", len(chunks))

assert len(chunks) > 0

#%%
# --------------------------------------------------
# STEP 3 - Generate embeddings
# --------------------------------------------------

model_name = "sentence-transformers/all-MiniLM-L6-v2"

model = SentenceTransformer(
    model_name,
    device="cpu"
)

code_texts = [chunk.content for chunk in chunks]

embeddings = model.encode(
    code_texts,
    convert_to_numpy=True,
    normalize_embeddings=True
)

print("Embedding shape:", embeddings.shape)

assert embeddings.shape == (len(chunks), 384)

#%%
# --------------------------------------------------
# STEP 4 - Construct Qdrant points
# --------------------------------------------------

points = []

for chunk, vector in zip(chunks, embeddings):

    # Create stable UUID from source identity
    source_key = (
        f"{Path(chunk.file_path).as_posix()}"
        f"::{chunk.chunk_id}"
    )

    point_id = str(
        uuid5(NAMESPACE_URL, source_key)
    )

    payload = {
        "chunk_id": chunk.chunk_id,
        "source_type": chunk.source_type,
        "file_path": chunk.file_path,
        "class_name": chunk.class_name,
        "method_name": chunk.method_name,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content": chunk.content,
        "embedding_model": model_name
    }

    point = models.PointStruct(
        id=point_id,
        vector=vector.tolist(),
        payload=payload
    )

    points.append(point)

#%%
# --------------------------------------------------
# STEP 5 - Upload points to Qdrant
# --------------------------------------------------

result = client.upsert(
    collection_name=collection_name,
    points=points,
    wait=True
)

print("\n--- Upsert Result ---")
print("Status:", result.status)

#%%
# --------------------------------------------------
# STEP 6 - Verify stored data
# --------------------------------------------------

count_result = client.count(
    collection_name=collection_name,
    exact=True
)

print("Stored points:", count_result.count)

assert count_result.count >= len(points)

#%%
# --------------------------------------------------
# STEP 7 - Retrieve a sample point
# --------------------------------------------------

stored_points = client.retrieve(
    collection_name=collection_name,
    ids=[points[0].id],
    with_payload=True,
    with_vectors=False
)

assert len(stored_points) == 1

sample = stored_points[0]

print("\n--- Sample Stored Point ---")
print("ID:", sample.id)
print("Class:", sample.payload["class_name"])
print("Method:", sample.payload["method_name"])
print("File:", sample.payload["file_path"])

print("\nQdrant ingestion: PASS")
