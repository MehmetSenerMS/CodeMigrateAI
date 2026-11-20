"""RAGAS ID-based retrieval evaluation for CodeMigrate AI (run in Spyder).

Edit only the settings under CONFIGURATION before running. Gold labels are
human-reviewable in gold_queries.jsonl. No remote LLM, memory, or C# code
execution is required in this retrieval-only stage.
"""

import asyncio
import csv
import json
import math
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")
SOURCE_DIR = PROJECT_ROOT / "legacy"
GOLD_FILE = PROJECT_ROOT / "evaluation" / "ragas" / "gold_queries.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "ragas"

TOP_K = 5
CANDIDATE_COUNT = 12
BOOTSTRAP_SAMPLES = 2000
SEED = 42


# ============================================================
# PURE METRIC HELPERS (easy to unit-test independently)
# ============================================================

def method_id(hit):
    """Canonical ID matching gold labels, without path/score dependence."""
    name = str(hit.get("method_name") or "").strip()
    owner = str(hit.get("class_name") or "").strip()
    if not owner or not name:
        raise ValueError(f"Result is missing class/method metadata: {hit!r}")
    return f"{owner}.{name}"


def unique_hits(hits, limit):
    """Prevent multiple copies of one method skewing retrieval metrics."""
    chosen = []
    seen = set()
    for hit in hits:
        canonical = method_id(hit)
        if canonical not in seen:
            seen.add(canonical)
            chosen.append(dict(hit))
        if len(chosen) >= limit:
            break
    return chosen


def retrieval_metrics(retrieved_ids, reference_ids, k):
    relevant = set(reference_ids)
    ranked = list(retrieved_ids[:k])
    flags = [int(identifier in relevant) for identifier in ranked]
    hits = sum(flags)

    # P@k uses a fixed denominator k, even if fewer results are returned.
    precision = hits / k
    recall = hits / len(relevant)
    reciprocal_rank = next(
        (1.0 / rank for rank, hit in enumerate(flags, start=1) if hit),
        0.0,
    )
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(flags, 1))
    ideal = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, min(len(relevant), k) + 1)
    )
    return {
        "hit_at_k": float(bool(hits)),
        "precision_at_k": precision,
        "recall_at_k": recall,
        "mrr_at_k": reciprocal_rank,
        "ndcg_at_k": dcg / ideal if ideal else 0.0,
    }


def mean_ci(values, samples=2000, seed=42):
    """Unstratified percentile bootstrap CI over evaluation questions."""
    rng = random.Random(seed)
    if not values:
        raise ValueError("Cannot bootstrap an empty metric")
    averages = sorted(
        statistics.fmean(rng.choices(values, k=len(values)))
        for _ in range(samples)
    )
    low = averages[int(0.025 * (samples - 1))]
    high = averages[int(0.975 * (samples - 1))]
    return statistics.fmean(values), low, high


def paired_ci(left, right, samples=2000, seed=42):
    if len(left) != len(right) or not left:
        raise ValueError("Paired comparison needs equal non-empty vectors")
    differences = [a - b for a, b in zip(left, right)]
    return mean_ci(differences, samples, seed)


def load_gold(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing evaluation questions: {path}\n"
            "Copy gold_queries.jsonl to C:\\CodeMigrateAI\\evaluation\\ragas."
        )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Gold evaluation file is empty")
    seen = set()
    for item in rows:
        if item["id"] in seen:
            raise ValueError(f"Duplicate question ID: {item['id']}")
        seen.add(item["id"])
        gold = item["reference_context_ids"]
        if not gold or len(gold) != len(set(gold)):
            raise ValueError(f"Missing or duplicate gold methods: {item['id']}")
        if not item["user_input"].strip() or not item["reference"].strip():
            raise ValueError(f"Incomplete question: {item['id']}")
    return rows


async def ragas_id_metrics(rows):
    """Call RAGAS's real ID-based metrics, not homemade substitutes."""
    try:
        from ragas import SingleTurnSample
        from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS is missing/incompatible. Install: "
            "python -m pip install 'ragas>=0.4,<1'"
        ) from exc

    precision = IDBasedContextPrecision()
    recall = IDBasedContextRecall()
    for row in rows:
        # Empty retrievals are represented as 0 (RAGAS may reject an empty list).
        if not row["retrieved_context_ids"]:
            row["ragas_id_context_precision"] = 0.0
            row["ragas_id_context_recall"] = 0.0
            continue
        sample = SingleTurnSample(
            retrieved_context_ids=row["retrieved_context_ids"],
            reference_context_ids=row["reference_context_ids"],
        )
        row["ragas_id_context_precision"] = float(await precision.single_turn_ascore(sample))
        row["ragas_id_context_recall"] = float(await recall.single_turn_ascore(sample))


def run_in_thread(coroutine_factory):
    """Works inside Spyder/IPython, where an event loop may already run."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coroutine_factory())).result()


def save_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run():
    # Make CodeMigrateAI imports work even if Spyder's current folder differs.
    sys.path.insert(0, str(PROJECT_ROOT))
    from codemigrate.retrieval.hybrid_retriever import HybridRetriever
    from codemigrate.retrieval.reranker import CrossEncoderReranker

    if not SOURCE_DIR.is_dir() or not any(SOURCE_DIR.rglob("*.cs")):
        raise FileNotFoundError(f"No C# files under {SOURCE_DIR}")
    if TOP_K < 1 or CANDIDATE_COUNT < TOP_K:
        raise ValueError("Require 1 <= TOP_K <= CANDIDATE_COUNT")

    cases = load_gold(GOLD_FILE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    hybrid = HybridRetriever(candidate_count=CANDIDATE_COUNT)
    count = hybrid.index_directory(SOURCE_DIR)
    print(f"Indexed C# methods: {count}")
    reranker = CrossEncoderReranker(device="cpu")

    rows = []
    answer_inputs = []
    strategies = ("bm25", "dense", "hybrid", "reranked")
    for index, case in enumerate(cases, 1):
        question = case["user_input"]
        depth = max(CANDIDATE_COUNT, TOP_K * 3)

        bm25_hits = unique_hits(hybrid.bm25.search(question, top_k=depth), TOP_K)
        dense_hits = unique_hits(hybrid.dense.search(question, top_k=depth), TOP_K)
        # Search depth must be >= candidate_count for cross-encoder comparison.
        hybrid_candidates = unique_hits(hybrid.search(question, top_k=depth), depth)
        hybrid_hits = hybrid_candidates[:TOP_K]
        reranked_hits = unique_hits(
            reranker.rerank(question, hybrid_candidates, top_k=len(hybrid_candidates)),
            TOP_K,
        ) if hybrid_candidates else []

        result_sets = {
            "bm25": bm25_hits,
            "dense": dense_hits,
            "hybrid": hybrid_hits,
            "reranked": reranked_hits,
        }
        print(f"[{index:02d}/{len(cases)}] {case['id']}")
        for strategy in strategies:
            hits = result_sets[strategy]
            ids = [method_id(hit) for hit in hits]
            row = {
                "id": case["id"],
                "strategy": strategy,
                "user_input": question,
                "reference": case["reference"],
                "reference_context_ids": case["reference_context_ids"],
                "retrieved_context_ids": ids,
                **retrieval_metrics(ids, case["reference_context_ids"], TOP_K),
            }
            rows.append(row)
            print(f"  {strategy:8} MRR={row['mrr_at_k']:.3f} Recall={row['recall_at_k']:.3f} {ids[:2]}")

        # Source context is actual retrieved C#, never a generated reference.
        answer_inputs.append({
            "id": case["id"],
            "user_input": question,
            "reference": case["reference"],
            "reference_context_ids": case["reference_context_ids"],
            "retrieved_context_ids": [method_id(hit) for hit in reranked_hits],
            "retrieved_contexts": [str(hit["content"]) for hit in reranked_hits],
            "source_hits": [
                {
                    "class_name": hit["class_name"],
                    "method_name": hit["method_name"],
                    "file_path": str(hit.get("file_path") or "unknown"),
                    "content": str(hit["content"]),
                    "score": float(hit.get("score") or 0),
                    "cross_encoder_score": float(hit.get("cross_encoder_score") or 0),
                }
                for hit in reranked_hits
            ],
            "response": "",  # Populate with the Documentation Agent's actual answer.
        })

    # All strategies use exactly the same set/order of questions.
    run_in_thread(lambda: ragas_id_metrics(rows))

    save_jsonl(OUTPUT_DIR / "retrieval_results.jsonl", rows)
    save_jsonl(OUTPUT_DIR / "answer_evaluation_inputs.jsonl", answer_inputs)

    metrics = (
        "hit_at_k", "precision_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k",
        "ragas_id_context_precision", "ragas_id_context_recall",
    )
    summary = []
    for strategy in strategies:
        group = [row for row in rows if row["strategy"] == strategy]
        record = {"strategy": strategy, "questions": len(group), "top_k": TOP_K}
        for metric in metrics:
            estimate, low, high = mean_ci(
                [row[metric] for row in group], BOOTSTRAP_SAMPLES, SEED
            )
            record[metric] = round(estimate, 6)
            record[f"{metric}_ci_low"] = round(low, 6)
            record[f"{metric}_ci_high"] = round(high, 6)
        summary.append(record)

    with (OUTPUT_DIR / "retrieval_summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    comparison = {}
    for metric in ("recall_at_k", "mrr_at_k", "ndcg_at_k"):
        reranked = [row[metric] for row in rows if row["strategy"] == "reranked"]
        hybrid_values = [row[metric] for row in rows if row["strategy"] == "hybrid"]
        difference, low, high = paired_ci(
            reranked, hybrid_values, BOOTSTRAP_SAMPLES, SEED
        )
        comparison[metric] = {
            "reranked_minus_hybrid": difference,
            "95pct_ci": [low, high],
        }
    (OUTPUT_DIR / "paired_bootstrap.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )

    print("\nRAGAS RETRIEVAL EVALUATION")
    for item in summary:
        print(
            f"{item['strategy']:9} Hit@{TOP_K}: {item['hit_at_k']:.3f} "
            f"MRR: {item['mrr_at_k']:.3f} "
            f"RAGAS-ID Precision: {item['ragas_id_context_precision']:.3f} "
            f"RAGAS-ID Recall: {item['ragas_id_context_recall']:.3f}"
        )
    print("Results:", OUTPUT_DIR)
    print("Review the gold labels against the actual source methods before drawing conclusions.")


if __name__ == "__main__":
    run()
