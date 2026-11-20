"""CodeMigrate AI — retrieve relevant legacy C# code.

Run from C:\\CodeMigrateAI in Spyder (F5), or:
    python codemigrate_main.py
    python codemigrate_main.py --rerank
    python codemigrate_main.py --query "Find a method that checks customer activity"

The hybrid ranker is the default. Cross-Encoder reranking is opt-in.
"""

import argparse

from codemigrate.retrieval.hybrid_retriever import HybridRetriever


DEFAULT_QUERY = "Find the method that checks whether a customer is active"


def retrieve_code(
    query: str,
    retriever: HybridRetriever,
    *,
    top_k: int = 5,
    rerank: bool = False,
) -> list[dict]:
    """Return relevant C# chunks while retaining retrieval metadata."""
    if top_k < 1:
        raise ValueError("top_k must be positive")

    candidates = retriever.search(query, top_k=max(top_k, 20))
    if not rerank:
        return candidates[:top_k]

    # Import and load this extra model only when explicitly enabled.
    from codemigrate.retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker(device="cpu")
    return reranker.rerank(query, candidates, top_k=top_k)


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeMigrate AI retrieval")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--directory", default="legacy")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Apply optional Cross-Encoder reranking after hybrid retrieval",
    )
    args = parser.parse_args()

    retriever = HybridRetriever(rrf_k=60, candidate_count=20)
    indexed_count = retriever.index_directory(args.directory)

    results = retrieve_code(
        args.query,
        retriever,
        top_k=args.top_k,
        rerank=args.rerank,
    )
    print(f"Indexed C# methods: {indexed_count}")
    print(f"Query: {args.query}")
    print(f"Mode: {'Hybrid + Cross-Encoder' if args.rerank else 'Hybrid'}")

    for rank, item in enumerate(results, 1):
        score_label = "CE" if args.rerank else "RRF"
        score_key = "cross_encoder_score" if args.rerank else "score"
        print(
            f"{rank}. {item['class_name']}.{item['method_name']} "
            f"| {score_label}={item[score_key]:.4f} "
            f"| {item['file_path']}:{item['start_line']}"
        )


if __name__ == "__main__":
    main()
