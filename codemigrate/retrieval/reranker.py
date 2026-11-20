"""Cross-Encoder reranking for CodeMigrate AI.

Receives candidates from HybridRetriever, scores query/code pairs jointly,
and returns the same candidate records in Cross-Encoder relevance order.
"""

from sentence_transformers import CrossEncoder


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2",
        device: str = "cpu",
        batch_size: int = 8,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = CrossEncoder(model_name, device=device, max_length=512)

    @staticmethod
    def _format_candidate(candidate: dict) -> str:
        """Attach code context to the text that the Cross-Encoder will score."""
        content = candidate.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Each candidate must include non-empty C# content")

        return (
            f"Class: {candidate.get('class_name') or 'Unknown'}\n"
            f"Method: {candidate.get('method_name') or 'Unknown'}\n"
            f"C# code:\n{content}"
        )

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Score all hybrid candidates, then return their top-k ordered by relevance."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query cannot be empty")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if not candidates:
            return []

        pairs = [
            (query, self._format_candidate(candidate))
            for candidate in candidates
        ]
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        if len(scores) != len(candidates):
            raise RuntimeError("Cross-Encoder returned an unexpected number of scores")

        ranked = []
        for hybrid_rank, (candidate, score) in enumerate(
            zip(candidates, scores), start=1
        ):
            item = dict(candidate)  # Do not mutate the hybrid retrieval results.
            item["hybrid_rank"] = hybrid_rank
            item["cross_encoder_score"] = float(score)
            ranked.append(item)

        ranked.sort(
            key=lambda item: (-item["cross_encoder_score"], item["hybrid_rank"])
        )
        for rerank_rank, item in enumerate(ranked, start=1):
            item["rerank_rank"] = rerank_rank

        return ranked[:top_k]
