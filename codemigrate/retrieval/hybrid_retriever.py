"""Hybrid retrieval using Qdrant, BM25 and Reciprocal Rank Fusion."""

from pathlib import Path

from codemigrate.retrieval.dense_retriever import DenseRetriever
from codemigrate.retrieval.bm25_retriever import BM25Retriever


class HybridRetriever:

    def __init__(
        self,
        dense_retriever=None,
        bm25_retriever=None,
        rrf_k=60,
        candidate_count=20
    ):

        if rrf_k < 0:
            raise ValueError("rrf_k must be nonnegative")

        if candidate_count < 1:
            raise ValueError("candidate_count must be positive")

        self.dense = dense_retriever or DenseRetriever()
        self.bm25 = bm25_retriever or BM25Retriever()

        self.rrf_k = rrf_k
        self.candidate_count = candidate_count

    @staticmethod
    def _chunk_key(result):
        """
        Identify the same source chunk across retrieval systems.

        Dense and BM25 IDs may differ, so use source metadata
        and the original code instead.
        """

        file_path = str(
            Path(result.get("file_path") or "").resolve()
        ).casefold()

        content = (
            str(result.get("content") or "")
            .replace("\r\n", "\n")
            .strip()
        )

        return (
            file_path,
            result.get("class_name"),
            result.get("method_name"),
            content
        )

    def index_directory(self, directory):

        dense_count = self.dense.index_directory(directory)

        bm25_count = self.bm25.index_directory(
            str(directory)
        )

        if dense_count != bm25_count:
            raise RuntimeError(
                f"Index mismatch: "
                f"dense={dense_count}, "
                f"BM25={bm25_count}"
            )

        return dense_count

    def search(self, query, top_k=5):

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query cannot be empty")

        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be positive")

        search_depth = max(
            top_k,
            self.candidate_count
        )

        dense_results = self.dense.search(
            query,
            top_k=search_depth
        )

        bm25_results = self.bm25.search(
            query,
            top_k=search_depth
        )

        merged = {}

        for source, results in [
            ("dense", dense_results),
            ("bm25", bm25_results)
        ]:

            seen_in_source = set()

            for rank, result in enumerate(results, start=1):

                chunk_key = self._chunk_key(result)

                # Prevent duplicates within one retrieval backend.
                if chunk_key in seen_in_source:
                    continue

                seen_in_source.add(chunk_key)

                if chunk_key not in merged:

                    merged[chunk_key] = {
                        **result,
                        "score": 0.0,
                        "dense_rank": None,
                        "bm25_rank": None,
                        "dense_score": None,
                        "bm25_score": None
                    }

                entry = merged[chunk_key]

                entry["score"] += (
                    1.0 / (self.rrf_k + rank)
                )

                entry[f"{source}_rank"] = rank

                entry[f"{source}_score"] = float(
                    result["score"]
                )

        ranked = sorted(
            merged.values(),
            key=lambda item: -item["score"]
        )

        return ranked[:top_k]