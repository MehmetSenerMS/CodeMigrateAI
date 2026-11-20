
import numpy as np
from sentence_transformers import SentenceTransformer

from codemigrate.chunking.code_chunker import CodeChunker


# --------------------------------------------------
# STEP 1 - Extract C# code chunks
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
    chunks.extend(chunker.extract_methods())

print("Total code chunks:", len(chunks))

if not chunks:
    raise ValueError("No code chunks were extracted")

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
# STEP 3 - Generate code embeddings
# --------------------------------------------------

code_texts = [chunk.content for chunk in chunks]

code_embeddings = model.encode(
    code_texts,
    convert_to_numpy=True,
    normalize_embeddings=True
)

print("Embedding matrix:", code_embeddings.shape)

#%%
# --------------------------------------------------
# STEP 4 - Generate query embedding
# --------------------------------------------------

query = "Find the method that checks whether a customer is active"

query_embedding = model.encode(
    query,
    convert_to_numpy=True,
    normalize_embeddings=True
)

print("Query vector shape:", query_embedding.shape)

#%%
# --------------------------------------------------
# STEP 5 - Calculate cosine similarities
# --------------------------------------------------

scores = code_embeddings @ query_embedding

#%%
# --------------------------------------------------
# STEP 6 - Rank code chunks
# --------------------------------------------------

ranked_indices = np.argsort(scores)[::-1]

print("\n--- Semantic Search Results ---")

for rank, index in enumerate(ranked_indices[:5], start=1):

    chunk = chunks[index]
    score = scores[index]

    print(f"\nRank: {rank}")
    print(f"Class: {chunk.class_name}")
    print(f"Method: {chunk.method_name}")
    print(f"Similarity: {score:.4f}")
    print(f"Source: {chunk.file_path}")
#%%
# --------------------------------------------------
# STEP 7 - Evaluate Semantic Retrieval
# --------------------------------------------------

test_queries = [
    {
        "query": "Find a method that returns a customer's name",
        "expected_class": "CustomerService",
        "expected_method": "GetCustomerName"
    },
    {
        "query": "Find the method that checks whether a customer is active",
        "expected_class": "CustomerService",
        "expected_method": "IsCustomerActive"
    },
    {
        "query": "Find a generic method that converts an object to another type",
        "expected_class": "GenericMethodService",
        "expected_method": "ConvertValue"
    }
]

query_embeddings = model.encode(
    [item["query"] for item in test_queries],
    convert_to_numpy=True,
    normalize_embeddings=True
)

similarity_matrix = query_embeddings @ code_embeddings.T

hit_at_1 = 0
hit_at_3 = 0
reciprocal_ranks = []

for i, test_case in enumerate(test_queries):

    ranked_indices = np.argsort(
        similarity_matrix[i]
    )[::-1]

    expected_index = next(
        index
        for index, chunk in enumerate(chunks)
        if chunk.class_name == test_case["expected_class"]
        and chunk.method_name == test_case["expected_method"]
    )

    target_rank = int(
        np.where(ranked_indices == expected_index)[0][0]
    ) + 1

    hit_at_1 += int(target_rank == 1)
    hit_at_3 += int(target_rank <= 3)

    reciprocal_ranks.append(1.0 / target_rank)

    print("\nQuery:", test_case["query"])
    print("Expected:", test_case["expected_method"])
    print("Expected rank:", target_rank)

    print("Top 3 results:")

    for rank, index in enumerate(ranked_indices[:3], start=1):
        chunk = chunks[index]

        print(
            f"  {rank}. {chunk.class_name}.{chunk.method_name}"
            f" | Score: {similarity_matrix[i, index]:.4f}"
        )

n_queries = len(test_queries)

print("\n--- Retrieval Evaluation ---")
print(f"Hit@1: {hit_at_1 / n_queries:.4f}")
print(f"Hit@3: {hit_at_3 / n_queries:.4f}")
print(f"MRR: {np.mean(reciprocal_ranks):.4f}")












































