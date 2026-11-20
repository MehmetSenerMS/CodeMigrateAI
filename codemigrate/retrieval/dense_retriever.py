"""Dense code retrieval for CodeMigrate AI.

Pipeline: C# files -> SourceChunk -> SentenceTransformer -> Qdrant -> search.
Only the dense-retrieval component is implemented here; BM25 and reranking
will be separate components in the agreed architecture.
"""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from codemigrate.chunking.code_chunker import CodeChunker


class DenseRetriever:
    """Index C# methods and retrieve similar methods through Qdrant."""

    def __init__(
        self,
        collection_name: str = "codemigrate_code",
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        qdrant_url: str = "http://127.0.0.1:6333",
        device: str = "cpu",
    ) -> None:
        self.collection_name = collection_name
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.client = QdrantClient(url=qdrant_url, prefer_grpc=False)

        dimension = self.model.get_embedding_dimension()
        if dimension is None:
            raise ValueError("Embedding model did not report its vector size")
        self.vector_size = int(dimension)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the collection once; never overwrite existing data."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            return

        config = self.client.get_collection(self.collection_name)
        vectors = config.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise ValueError("Expected a collection with one unnamed vector")
        if vectors.size != self.vector_size or vectors.distance != models.Distance.COSINE:
            raise ValueError(
                "Existing Qdrant collection is incompatible with the "
                "embedding model (vector size or distance differs)"
            )

    def index_directory(self, directory: str | Path, batch_size: int = 32) -> int:
        """Parse and upsert the C# methods under a directory; return count."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(f"Source directory not found: {root}")

        source_files = sorted(
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".cs"
        )
        chunks = []
        for file_path in source_files:
            chunks.extend(CodeChunker(file_path).extract_methods())

        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset:offset + batch_size]
            embeddings = self.model.encode(
                [chunk.content for chunk in batch],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            points = []
            for chunk, embedding in zip(batch, embeddings):
                # Reuse the ID formula from our earlier Qdrant ingestion test.
                key = f"{Path(chunk.file_path).as_posix()}::{chunk.chunk_id}"
                point_id = str(uuid5(NAMESPACE_URL, key))

                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=embedding.tolist(),
                        payload={
                            "chunk_id": chunk.chunk_id,
                            "source_type": chunk.source_type,
                            "file_path": chunk.file_path,
                            "content": chunk.content,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                            "class_name": chunk.class_name,
                            "method_name": chunk.method_name,
                            "embedding_model": self.model_name,
                        },
                    )
                )

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

        return len(chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return ranked results with score, source code and metadata."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query cannot be empty")
        if top_k < 1:
            raise ValueError("top_k must be positive")

        query_vector = self.model.encode(
            query.strip(),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        results = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append({
                "id": str(hit.id),
                "score": float(hit.score),
                "chunk_id": payload.get("chunk_id"),
                "class_name": payload.get("class_name"),
                "method_name": payload.get("method_name"),
                "file_path": payload.get("file_path"),
                "start_line": payload.get("start_line"),
                "end_line": payload.get("end_line"),
                "content": payload.get("content"),
            })
        return results
