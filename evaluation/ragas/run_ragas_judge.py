"""RAGAS LLM metrics for saved CodeMigrate Documentation Agent answers.

This stage sends the question, response and retrieved C# source snippets to
the configured judge/embeddings API. Review the data and provider policies.
The Colab /chat and /migrate endpoints are NOT OpenAI-compatible judges.
"""

import asyncio
import csv
import json
import os
import random
import shutil
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import Tk, simpledialog


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")
EVAL_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "ragas"
INPUT_FILE = EVAL_DIR / "agent_answers.jsonl"
OUTPUT_FILE = EVAL_DIR / "llm_ragas_results.jsonl"

# An OpenAI API is one supported option. Other providers must expose both
# OpenAI-compatible chat (including the necessary structured output) and
# embeddings APIs. Use environment variables for credentials, never code.
JUDGE_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
JUDGE_API_KEY_ENV = "RAGAS_JUDGE_API_KEY"
JUDGE_BASE_URL_ENV = "RAGAS_JUDGE_BASE_URL"  # optional
EMBEDDING_BASE_URL_ENV = "RAGAS_EMBEDDING_BASE_URL"  # optional
JUDGE_MAX_OUTPUT_TOKENS = 4096
REUSE_SUCCESSFUL_SCORES = True  # Change to False only for a new benchmark.


def get_judge_api_key():
    """Prefer environment configuration; otherwise show a masked dialog."""
    existing = os.environ.get(JUDGE_API_KEY_ENV) or os.environ.get("OPENAI_API_KEY")
    if existing:
        return existing

    root = Tk()
    root.withdraw()
    try:
        key = simpledialog.askstring(
            "RAGAS OpenAI Judge",
            "Enter your OpenAI API key (not stored):",
            parent=root,
            show="*",
        )
    finally:
        root.destroy()
    if not key or not key.strip():
        raise ValueError("OpenAI API key is required")
    return key.strip()


async def score_all(cases, key, judge_url, embedding_url, previous_results):
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings.base import embedding_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    judge_client = AsyncOpenAI(api_key=key, base_url=judge_url)
    embedding_client = AsyncOpenAI(
        api_key=key, base_url=embedding_url or judge_url
    )
    # Faithfulness extracts many claims, then verifies them. The RAGAS LLM
    # default output limit was too short for six of the eight saved answers.
    llm = llm_factory(
        JUDGE_MODEL,
        client=judge_client,
        max_tokens=JUDGE_MAX_OUTPUT_TOKENS,
    )
    embeddings = embedding_factory(
        "openai", model=EMBEDDING_MODEL, client=embedding_client
    )
    scorers = {
        "faithfulness": (
            Faithfulness(llm=llm),
            ("user_input", "response", "retrieved_contexts"),
        ),
        "answer_relevancy": (
            AnswerRelevancy(llm=llm, embeddings=embeddings),
            ("user_input", "response"),
        ),
        "context_precision": (
            ContextPrecision(llm=llm),
            ("user_input", "reference", "retrieved_contexts"),
        ),
        "context_recall": (
            ContextRecall(llm=llm),
            ("user_input", "reference", "retrieved_contexts"),
        ),
    }

    results = []
    for index, case in enumerate(cases, 1):
        if not case.get("response", "").strip():
            raise ValueError(f"Missing actual agent response for {case['id']}")
        if not case.get("retrieved_contexts"):
            raise ValueError(f"No evidence snippets for {case['id']}")

        args = {
            "user_input": case["user_input"],
            "response": case["response"],
            "retrieved_contexts": case["retrieved_contexts"],
            "reference": case["reference"],
        }
        row = dict(previous_results.get(case["id"], {"id": case["id"]}))
        for name, (scorer, required_args) in scorers.items():
            if REUSE_SUCCESSFUL_SCORES and isinstance(
                row.get(name), (int, float)
            ) and not isinstance(row[name], bool):
                continue
            try:
                result = await scorer.ascore(
                    **{key: args[key] for key in required_args}
                )
                row[name] = float(result.value)
                row[f"{name}_error"] = None
            except Exception as error:
                row[name] = None
                row[f"{name}_error"] = f"{type(error).__name__}: {error}"
        results.append(row)
        print(
            f"[{index}/{len(cases)}] {row['id']}: "
            + " ".join(
                f"{name}={row[name]:.3f}" if row[name] is not None else f"{name}=ERROR"
                for name in scorers
            )
        )
        # Persist completed cases after each example. Atomic replacement and
        # a one-time backup protect the previous successful judge results.
        interim = OUTPUT_FILE.with_suffix(OUTPUT_FILE.suffix + ".tmp")
        with interim.open("w", encoding="utf-8") as handle:
            for saved in results:
                handle.write(json.dumps(saved, ensure_ascii=False) + "\n")
            for future in cases[index:]:
                saved = previous_results.get(future["id"])
                if saved is not None:
                    handle.write(json.dumps(saved, ensure_ascii=False) + "\n")
        interim.replace(OUTPUT_FILE)

    await judge_client.close()
    await embedding_client.close()
    return results


def run():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"Generate agent answers first: {INPUT_FILE}"
        )
    key = get_judge_api_key()
    cases = [
        json.loads(line)
        for line in INPUT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("Answer dataset is empty")

    previous_results = {}
    if REUSE_SUCCESSFUL_SCORES and OUTPUT_FILE.exists():
        for line in OUTPUT_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item["id"] in previous_results:
                    raise ValueError(f"Duplicate saved result: {item['id']}")
                previous_results[item["id"]] = item

        backup = OUTPUT_FILE.with_suffix(OUTPUT_FILE.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(OUTPUT_FILE, backup)
            print("Previous results backed up:", backup)

    print("RAGAS judge model:", JUDGE_MODEL)
    print("Embedding model:", EMBEDDING_MODEL)
    print("Judge max output tokens:", JUDGE_MAX_OUTPUT_TOKENS)
    print("Successful existing scores reused:", REUSE_SUCCESSFUL_SCORES)
    print("Examples:", len(cases))
    print("The judge API receives questions, answers and retrieved source code.")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        results = pool.submit(
            lambda: asyncio.run(score_all(
                cases,
                key,
                os.environ.get(JUDGE_BASE_URL_ENV) or None,
                os.environ.get(EMBEDDING_BASE_URL_ENV) or None,
                previous_results,
            ))
        ).result()

    metrics = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    summary = []
    for metric in metrics:
        scores = [row[metric] for row in results if row[metric] is not None]
        if scores:
            rng = random.Random(42)
            bootstraps = sorted(
                statistics.fmean(rng.choices(scores, k=len(scores)))
                for _ in range(2000)
            )
            low, high = bootstraps[49], bootstraps[1949]
        else:
            low = high = None
        summary.append({
            "metric": metric,
            "mean": statistics.fmean(scores) if scores else None,
            "bootstrap_95pct_low": low,
            "bootstrap_95pct_high": high,
            "successful": len(scores),
            "total": len(cases),
        })
    with (EVAL_DIR / "llm_ragas_summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    print("\nRAGAS LLM EVALUATION")
    for row in summary:
        value = f"{row['mean']:.3f}" if row["mean"] is not None else "N/A"
        print(f"{row['metric']:18} {value} ({row['successful']}/{row['total']})")
    print("Results:", EVAL_DIR)
    print("A metric is complete only if its successful count equals total.")


if __name__ == "__main__":
    run()



