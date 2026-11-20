from pathlib import Path

from crewai import Memory


# ------------------------------------------------------------
# Local embedding configuration
# ------------------------------------------------------------

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ------------------------------------------------------------
# Create persistent agent memory
# ------------------------------------------------------------

def create_agent_memory(project_root: str | Path, llm) -> Memory:

    storage_path = (
        Path(project_root)
        / "data"
        / "agent_memory"
    )

    storage_path.mkdir(
        parents=True,
        exist_ok=True
    )

    memory = Memory(
        storage=str(storage_path),

        llm=llm,

        embedder={
            "provider": "sentence-transformer",
            "config": {
                "model_name": EMBEDDING_MODEL
            }
        },

        semantic_weight=0.5,
        recency_weight=0.3,
        importance_weight=0.2,

        consolidation_threshold=1.0
    )

    return memory