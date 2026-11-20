import math
from uuid import uuid5, NAMESPACE_URL
import re
from pathlib import Path
from collections import Counter

from codemigrate.chunking.code_chunker import CodeChunker


class BM25Retriever:

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75
    ):

        self.k1 = k1
        self.b = b

        self.chunks = []
        self.tokenized_docs = []
        self.term_frequencies = []
        self.document_frequencies = Counter()

        self.doc_lengths = []
        self.avg_doc_length = 0.0

    @staticmethod
    def _tokenize(text: str) -> list[str]:

        # Extract identifier-like tokens
        words = re.findall(
            r"[A-Za-z_][A-Za-z0-9_]*",
            text
        )

        tokens = []

        for word in words:

            # Split snake_case
            for part in word.split("_"):

                # Split CamelCase / PascalCase
                parts = re.sub(
                    r"([A-Z]+)([A-Z][a-z])",
                    r"\1 \2",
                    part
                )

                parts = re.sub(
                    r"([a-z0-9])([A-Z])",
                    r"\1 \2",
                    parts
                )

                tokens.extend(
                    token.lower()
                    for token in parts.split()
                )

        return tokens

    def index_directory(
        self,
        directory: str
    ) -> int:

        self.chunks = []
        self.tokenized_docs = []
        self.term_frequencies = []
        self.document_frequencies = Counter()
        self.doc_lengths = []

        source_files = sorted(
            Path(directory).rglob("*.cs")
        )

        for file_path in source_files:

            chunker = CodeChunker(file_path)

            self.chunks.extend(
                chunker.extract_methods()
            )

        for chunk in self.chunks:

            tokens = self._tokenize(chunk.content)

            self.tokenized_docs.append(tokens)

            frequencies = Counter(tokens)

            self.term_frequencies.append(
                frequencies
            )

            self.document_frequencies.update(
                set(tokens)
            )

            self.doc_lengths.append(len(tokens))

        if self.doc_lengths:

            self.avg_doc_length = (
                sum(self.doc_lengths)
                / len(self.doc_lengths)
            )

        else:
            self.avg_doc_length = 0.0

        return len(self.chunks)

    
    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> list[dict]:

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query cannot be empty")

        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be positive")

        if not self.chunks or self.avg_doc_length == 0:
            raise RuntimeError("BM25 index is empty")

        query_tokens = set(self._tokenize(query))

        n_documents = len(self.chunks)

        results = []

        for i, chunk in enumerate(self.chunks):

            score = 0.0
            doc_length = self.doc_lengths[i]

            for term in query_tokens:

                term_frequency = (
                    self.term_frequencies[i].get(term, 0)
                )

                if term_frequency == 0:
                    continue

                document_frequency = (
                    self.document_frequencies[term]
                )

                # Inverse Document Frequency
                idf = math.log(
                    1.0
                    + (
                        n_documents - document_frequency + 0.5
                    ) / (
                        document_frequency + 0.5
                    )
                )

                # Document length normalization
                normalization = self.k1 * (
                    1 - self.b
                    + self.b * doc_length / self.avg_doc_length
                )

                # BM25 contribution of this term
                term_score = idf * (
                    term_frequency * (self.k1 + 1)
                ) / (
                    term_frequency + normalization
                )

                score += term_score

            if score > 0:

                source_key = (
                    f"{Path(chunk.file_path).as_posix()}"
                    f"::{chunk.chunk_id}"
                )

                point_id = str(
                    uuid5(NAMESPACE_URL, source_key)
                )

                results.append({
                    "id": point_id,
                    "score": float(score),
                    "chunk_id": chunk.chunk_id,
                    "class_name": chunk.class_name,
                    "method_name": chunk.method_name,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content
                })

        results.sort(
            key=lambda item: (-item["score"], item["id"])
        )

        return results[:top_k]
