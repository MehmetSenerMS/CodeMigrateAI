# CodeMigrate AI — RAGAS Evaluation

This folder evaluates the existing Qdrant dense retrieval, BM25, Hybrid RRF,
and CrossEncoder reranking pipeline. It does not fine-tune models or mutate
source code or agent memory.

## Setup (Windows / Spyder)

Copy these four files to `C:\CodeMigrateAI\evaluation\ragas\`:

- `gold_queries.jsonl`
- `run_ragas_retrieval.py`
- `run_ragas_generate_answers.py`
- `run_ragas_judge.py`

Existing `codemigrate` package and running Qdrant server are required.
Run **once** in PowerShell (not separately in each Spyder execution):

```powershell
& "C:\Users\msmes\anaconda3\envs\codemigrate-ai\python.exe" -m pip install "ragas>=0.4,<1" "openai>=1" 
```

Set `PROJECT_ROOT`, `SOURCE_DIR`, `TOP_K` and the paths at the start of the
Python files if your installation differs. The reference labels in
`gold_queries.jsonl` are *illustrative* and must be checked against your
actual indexed C# methods before interpreting accuracy. Questions are only
eight examples, some sharing the same method, so confidence intervals are
exploratory rather than proof of generalization.

## Stage 1 — Retrieval without a judge LLM

```python
%runfile C:/CodeMigrateAI/evaluation/ragas/run_ragas_retrieval.py --wdir
```

This uses actual retrieved C# source code, evaluates 8 manually labeled
questions across four retrieval methods, and saves:

- `outputs/evaluation/ragas/retrieval_results.jsonl` (per-query results)
- `outputs/evaluation/ragas/retrieval_summary.csv` (mean and bootstrap 95% CI)
- `outputs/evaluation/ragas/paired_bootstrap.json` (reranked vs hybrid)
- `outputs/evaluation/ragas/answer_evaluation_inputs.jsonl` (captured contexts)

Metrics: Hit@k, Precision@k, Recall@k, MRR@k, nDCG@k and **actual RAGAS**
`IDBasedContextPrecision`/`IDBasedContextRecall`. ID-based precision is a
simple relevant-ID fraction; MRR and nDCG also account for ranking.

## Stage 2 — Generate Documentation Agent answers

Ensure the current Colab service exposes `/chat` and the shared project
configuration correctly supplies `CODEMIGRATE_API_URL`. Then:

```python
%runfile C:/CodeMigrateAI/evaluation/ragas/run_ragas_generate_answers.py --wdir
```

Enter the Colab inference key in the masked dialog. The existing Documentation
Agent is given **exactly the recorded source contexts**; no retrieval results
are replaced after measurement. Output:
`outputs/evaluation/ragas/agent_answers.jsonl`.

## Stage 3 — RAGAS LLM-based metrics (optional)

This step requires a **separate judge/embedding API**, e.g. an OpenAI API key.
Your CodeMigrate Colab `/chat` endpoint is a custom interface, not an
OpenAI-compatible chat-and-embeddings service, and cannot be substituted.

Configure `RAGAS_JUDGE_API_KEY` (or `OPENAI_API_KEY`) as an environment variable
*before launching Spyder*. The defaults are `gpt-4o-mini` for judging and
`text-embedding-3-small` for embeddings. Alternative services must offer
OpenAI-compatible chat and embedding endpoints; set
`RAGAS_JUDGE_BASE_URL`/`RAGAS_EMBEDDING_BASE_URL` if appropriate and edit
the model names. This stage sends your prompts, agent answers, and retrieved
source snippets to that provider; review these data before running.

```python
%runfile C:/CodeMigrateAI/evaluation/ragas/run_ragas_judge.py --wdir
```

It computes RAGAS **Faithfulness**, **AnswerRelevancy**, **ContextPrecision**
and **ContextRecall** with the current collections API and saves per-question
scores/errors plus mean and bootstrap CI to `outputs/evaluation/ragas/`.
Report counts are explicit: a metric with a provider error is **incomplete**.

Official RAGAS references:

- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/
