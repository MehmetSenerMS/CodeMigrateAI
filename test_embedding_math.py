import math

def cosine_similarity(vector_a,vector_b):
    
    if len(vector_a) != len(vector_b):
        raise ValueError("Vector dimensions must match")
    
    if not vector_a:
        raise ValueError("Vectors cannot be empty")
    
    dot_product = sum(a*b for a, b in zip(vector_a,vector_b))
    
    norm_a = math.sqrt(sum(a**2 for a in vector_a))
    
    norm_b = math.sqrt(sum(b**2 for b in vector_b))
    
    if norm_a == 0 or norm_b == 0:
        raise ValueError("Zero vectors are not supported")
    
    return dot_product / (norm_a * norm_b)
        
    
    
# Artificial vectors for learning the math
query_vector = [1.0, 1.0, 0.0]

code_vectors = {
    "IsCustomerActive": [1.0, 0.8, 0.0],
    "GetCustomerName": [1.0, 0.0, 0.0],
    "CalculateInvoice": [0.0, 0.0, 1.0]
}

results = []

for method_name, vector in code_vectors.items():

    score = cosine_similarity(
        query_vector,
        vector
    )

    results.append((method_name, score))

results.sort(key=lambda x: x[1], reverse=True)

print("--- Semantic Similarity Ranking (Toy Example) ---")

for method_name, score in results:
    print(f"{method_name}: {score:.4f}")