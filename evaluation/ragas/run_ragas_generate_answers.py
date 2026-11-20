"""Generate real Documentation Agent answers from FROZEN retrieved evidence.

Run after run_ragas_retrieval.py. It does not re-index or change the retrieved
chunks, so answer quality is evaluated against the evidence the agent saw.
It does not save generated text to CrewAI memory.
"""

import json
import sys
from pathlib import Path
from tkinter import Tk, simpledialog


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")
EVAL_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "ragas"
INPUT_FILE = EVAL_DIR / "answer_evaluation_inputs.jsonl"
OUTPUT_FILE = EVAL_DIR / "agent_answers.jsonl"
MAX_NEW_TOKENS = 512


class FixedRetriever:
    """Return the same source chunks captured during retrieval evaluation."""

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=5):
        return self.hits[:top_k]


class IdentityReranker:
    """Preserve the measured CrossEncoder order exactly."""

    def rerank(self, query, candidates, top_k=5):
        return candidates[:top_k]


def run():
    sys.path.insert(0, str(PROJECT_ROOT))
    from codemigrate.settings import get_api_url
    from codemigrate.llm.crewai_llm import CodeMigrateLLM
    from codemigrate.agents.documentation_agent import generate_documentation

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"Run retrieval evaluation first: {INPUT_FILE}")

    # Qt dialog masks the API key; never print or save the key.
    window = Tk()
    window.withdraw()
    try:
        api_key = simpledialog.askstring(
            "CodeMigrate AI", "Enter the Colab API key:",
            show="*", parent=window
        )
    finally:
        window.destroy()
    if not api_key:
        raise ValueError("API key is required")

    llm = CodeMigrateLLM(
        base_url=get_api_url(),
        api_key=api_key,
        max_new_tokens=MAX_NEW_TOKENS,
    )

    cases = [
        json.loads(line)
        for line in INPUT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    existing = {}
    if OUTPUT_FILE.exists():
        for line in OUTPUT_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("response", "").strip():
                    existing[row["id"]] = row

    with OUTPUT_FILE.open("a", encoding="utf-8") as output:
        for index, case in enumerate(cases, 1):
            if case["id"] in existing:
                print(f"[{index}/{len(cases)}] {case['id']} - already saved")
                continue

            hits = case["source_hits"]
            if not hits:
                print(f"[{index}/{len(cases)}] {case['id']} - no evidence, skipped")
                continue

            result = generate_documentation(
                case["user_input"],
                llm=llm,
                retriever=FixedRetriever(hits),
                reranker=IdentityReranker(),
                memory=None,
                candidate_count=len(hits),
                top_k=len(hits),
            )
            answer = result["documentation"].strip()
            if not answer:
                raise RuntimeError(f"Empty Documentation Agent answer: {case['id']}")

            record = {
                key: value
                for key, value in case.items()
                if key != "source_hits"
            }
            record["response"] = answer
            record["review_warnings"] = result.get("review_warnings", [])
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()  # Supports safe resume after a tunnel interruption.
            print(f"[{index}/{len(cases)}] {case['id']} - saved")

    print("\nAnswers:", OUTPUT_FILE)
    print("The generated answers were not written to agent memory.")


if __name__ == "__main__":
    run()
