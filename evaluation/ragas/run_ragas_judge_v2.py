"""Evaluate documentation v2 without overwriting baseline RAGAS results."""

import sys
from pathlib import Path


def run():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run_ragas_judge as judge

    base_dir = Path(r"C:\CodeMigrateAI") / "outputs" / "evaluation" / "ragas"
    judge.INPUT_FILE = base_dir / "agent_answers_v2.jsonl"
    judge.OUTPUT_FILE = base_dir / "llm_ragas_results_v2.jsonl"
    judge.REUSE_SUCCESSFUL_SCORES = True

    print("RAGAS evaluation version: documentation v2")
    print("Baseline RAGAS files remain unchanged.")
    judge.run()


if __name__ == "__main__":
    run()
