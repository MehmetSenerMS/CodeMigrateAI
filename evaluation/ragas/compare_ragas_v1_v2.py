"""Compute paired bootstrap confidence intervals for RAGAS v2 minus v1."""

import json
import random
import statistics
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")
EVAL_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "ragas"
BASE_FILE = EVAL_DIR / "llm_ragas_results.jsonl"
NEW_FILE = EVAL_DIR / "llm_ragas_results_v2.jsonl"
BOOTSTRAP_SAMPLES = 2000
SEED = 42
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


def load_unique(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != len({row["id"] for row in rows}):
        raise ValueError(f"Duplicate evaluation ID in {path}")
    return {row["id"]: row for row in rows}


def bootstrap(values):
    if not values:
        raise ValueError("Empty paired metric vector")
    rng = random.Random(SEED)
    means = sorted(
        statistics.fmean(rng.choices(values, k=len(values)))
        for _ in range(BOOTSTRAP_SAMPLES)
    )
    return {
        "mean_difference": statistics.fmean(values),
        "95pct_ci_low": means[int(0.025 * (BOOTSTRAP_SAMPLES - 1))],
        "95pct_ci_high": means[int(0.975 * (BOOTSTRAP_SAMPLES - 1))],
        "wins": sum(value > 0 for value in values),
        "losses": sum(value < 0 for value in values),
        "ties": sum(value == 0 for value in values),
    }


def run():
    before = load_unique(BASE_FILE)
    after = load_unique(NEW_FILE)
    if not before or set(before) != set(after):
        raise ValueError("Baseline and v2 must cover the exact same test IDs")

    report = {
        "baseline": str(BASE_FILE),
        "candidate": str(NEW_FILE),
        "sample_count": len(before),
        "metrics": {},
    }
    ids = sorted(before)
    for metric in METRICS:
        old = [before[key].get(metric) for key in ids]
        new = [after[key].get(metric) for key in ids]
        if any(value is None for value in old + new):
            raise ValueError(f"Incomplete RAGAS scores for: {metric}")
        diffs = [b - a for a, b in zip(old, new)]
        report["metrics"][metric] = {
            "v1_mean": statistics.fmean(old),
            "v2_mean": statistics.fmean(new),
            **bootstrap(diffs),
        }

    report_path = EVAL_DIR / "ragas_v1_vs_v2_paired_bootstrap.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("RAGAS A/B COMPARISON (v2 - v1)")
    for metric, value in report["metrics"].items():
        print(
            f"{metric:18} {value['v1_mean']:.3f} -> {value['v2_mean']:.3f} "
            f"| difference={value['mean_difference']:+.3f} "
            f"| 95% CI=[{value['95pct_ci_low']:+.3f}, "
            f"{value['95pct_ci_high']:+.3f}]"
        )
    print("Saved:", report_path)


if __name__ == "__main__":
    run()
