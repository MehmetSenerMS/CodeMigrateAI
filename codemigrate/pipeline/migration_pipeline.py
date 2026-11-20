from pathlib import Path

from codemigrate.retrieval.hybrid_retriever import HybridRetriever
from codemigrate.retrieval.reranker import CrossEncoderReranker
from codemigrate.llm.remote_client import RemoteMigrationClient


class MigrationPipeline:

    def __init__(
        self,
        model_client: RemoteMigrationClient,
        retriever=None,
        reranker=None
    ):

        self.model_client = model_client

        self.retriever = retriever or HybridRetriever(
            rrf_k=60,
            candidate_count=20
        )

        self.reranker = reranker or CrossEncoderReranker(
            device="cpu"
        )

        self.source_root = None

    def index_codebase(self, directory):

        self.source_root = Path(directory).resolve()

        return self.retriever.index_directory(
            directory
        )

    def retrieve(self, query, top_k=5):

        candidates = self.retriever.search(
            query=query,
            top_k=20
        )

        return self.reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=top_k
        )

    def migrate(self, selected_chunk, instruction):

        if self.source_root is None:
            raise RuntimeError(
                "Index the codebase before migration"
            )

        # ----------------------------------------------------
        # Resolve Source File
        # ----------------------------------------------------

        file_path = selected_chunk.get("file_path")

        if not file_path:
            raise ValueError("Source file path is missing")

        source_path = Path(file_path).resolve()

        if self.source_root not in source_path.parents:
            raise ValueError(
                "Source file is outside the indexed directory"
            )

        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        if source_path.suffix.lower() != ".cs":
            raise ValueError("Expected a C# source file")

        # ----------------------------------------------------
        # Read Complete C# Source
        # ----------------------------------------------------

        legacy_code = source_path.read_text(
            encoding="utf-8-sig"
        )

        # Current API request limit.
        if len(legacy_code) > 15000:
            raise ValueError(
                "Source file exceeds the current inference limit"
            )

        class_name = selected_chunk.get("class_name")
        method_name = selected_chunk.get("method_name")

        # ----------------------------------------------------
        # Migration Instruction
        # ----------------------------------------------------

        complete_instruction = (
            f"{instruction}\n\n"
            f"Target class: {class_name}\n"
            f"Target method: {method_name}\n\n"
            "Return a complete C# source file. "
            "Preserve the surrounding class declaration, "
            "required using directives, other methods "
            "and unrelated business logic. "
            "Focus the migration on the selected method. "
            "Do not return a standalone method."
        )

        # ----------------------------------------------------
        # LLM Inference
        # ----------------------------------------------------

        result = self.model_client.migrate(
            instruction=complete_instruction,
            legacy_code=legacy_code
        )

        modern_code = result["generated_code"]

        if not modern_code.strip():
            raise RuntimeError(
                "Model returned empty code"
            )

        return {
            "source_file": str(source_path),
            "class_name": class_name,
            "method_name": method_name,
            "legacy_code": legacy_code,
            "modern_code": modern_code,
            "generation_time": result["generation_time"],
            "generated_tokens": result["generated_tokens"],
            "cross_encoder_score": selected_chunk.get(
                "cross_encoder_score"
            )
        }