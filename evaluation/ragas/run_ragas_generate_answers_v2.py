"""A/B experiment: documentation v2 using only the top 3 frozen sources.

Requires the existing run_ragas_generate_answers.py in the same directory.
Never changes the baseline agent_answers.jsonl or original retrieval results.
"""

import json
import sys
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")
EVAL_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "ragas"
TOP_K = 3


def run():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run_ragas_generate_answers as generator

    baseline_path = EVAL_DIR / "answer_evaluation_inputs.jsonl"
    new_inputs_path = EVAL_DIR / "answer_evaluation_inputs_v2.jsonl"
    new_outputs_path = EVAL_DIR / "agent_answers_v2.jsonl"
    if not baseline_path.is_file():
        raise FileNotFoundError(f"Missing original retrieval evidence: {baseline_path}")

    baseline = [
        json.loads(line)
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not baseline:
        raise ValueError("No evaluation cases available")

    narrowed = []
    for item in baseline:
        trimmed = dict(item)
        for field in ("source_hits", "retrieved_context_ids", "retrieved_contexts"):
            trimmed[field] = item[field][:TOP_K]
        if not trimmed["source_hits"]:
            raise ValueError(f"No source evidence for {item['id']}")
        if not set(item["reference_context_ids"]).issubset(
            set(trimmed["retrieved_context_ids"])
        ):
            print(
                "WARNING: At least one gold method is outside top 3:", item["id"]
            )
        narrowed.append(trimmed)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with new_inputs_path.open("w", encoding="utf-8") as handle:
        for row in narrowed:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    generator.INPUT_FILE = new_inputs_path
    generator.OUTPUT_FILE = new_outputs_path
    generator.MAX_NEW_TOKENS = 512

    print("Documentation version: v2")
    print("Frozen evidence top-k:", TOP_K)
    print("Baseline answers are preserved.")
    generator.run()


if __name__ == "__main__":
    run()
