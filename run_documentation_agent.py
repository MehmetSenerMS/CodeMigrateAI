"""Run the CodeMigrate AI Documentation Agent from Spyder.

Requires the existing Colab /chat endpoint, local retrieval dependencies,
and the documentation_agent.py module under codemigrate/agents/.
"""

from datetime import datetime, timezone
from pathlib import Path
from tkinter import Tk, simpledialog

from codemigrate.llm.crewai_llm import CodeMigrateLLM
from codemigrate.memory.memory_config import create_agent_memory
from codemigrate.retrieval.hybrid_retriever import HybridRetriever
from codemigrate.retrieval.reranker import CrossEncoderReranker
from codemigrate.agents.documentation_agent import generate_documentation
from codemigrate.settings import get_api_url


# ============================================================
# Project Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

API_URL = get_api_url()

# Index C# source files already present in your project.
SOURCE_DIR = PROJECT_ROOT / "legacy"

QUERY = (
    "Document how CustomerService.GetCustomerName and "
    "CustomerService.IsCustomerActive work. Explain their actual "
    "behavior, dependencies and migration considerations."
)

CANDIDATE_COUNT = 12
TOP_K = 3


# ============================================================
# Validate Source Directory
# ============================================================

if not SOURCE_DIR.is_dir():
    raise FileNotFoundError(f"C# source directory not found: {SOURCE_DIR}")

if not any(SOURCE_DIR.rglob("*.cs")):
    raise RuntimeError(f"No C# files found under: {SOURCE_DIR}")


# ============================================================
# Secure API Key Input
# ============================================================

window = Tk()
window.withdraw()

try:
    API_KEY = simpledialog.askstring(
        "CodeMigrate AI",
        "Enter your Colab API key:",
        show="*",
        parent=window,
    )
finally:
    window.destroy()

if not API_KEY:
    raise ValueError("API key is required")


# ============================================================
# Initialize Remote CrewAI LLM and Local Memory
# ============================================================

llm = CodeMigrateLLM(
    base_url=API_URL,
    api_key=API_KEY,
    # Match the request size already accepted by the working Code Analysis Agent.
    max_new_tokens=512,
)

memory = create_agent_memory(
    project_root=PROJECT_ROOT,
    llm=llm,
)

print("Remote LLM:", llm.base_url)


# ============================================================
# Build Hybrid Search Index (Qdrant + BM25)
# ============================================================

retriever = HybridRetriever(candidate_count=CANDIDATE_COUNT)

indexed_methods = retriever.index_directory(SOURCE_DIR)
if indexed_methods < 1:
    raise RuntimeError("Hybrid retrieval did not index any C# methods")

print("Indexed C# methods:", indexed_methods)


# ============================================================
# Initialize Cross-Encoder Reranking
# ============================================================

reranker = CrossEncoderReranker(
    model_name="cross-encoder/ms-marco-MiniLM-L6-v2",
    device="cpu",
    batch_size=8,
)


# ============================================================
# Generate Source-Grounded Technical Documentation
# ============================================================

print("\nStarting Documentation Agent...")
print("Retrieval query:", QUERY)

result = generate_documentation(
    QUERY,
    llm=llm,
    retriever=retriever,
    reranker=reranker,
    memory=memory,
    candidate_count=CANDIDATE_COUNT,
    top_k=TOP_K,
)

documentation = result["documentation"]
sources = result["sources"]

if not sources:
    raise RuntimeError("No source evidence found. Documentation was not saved.")

if not documentation.strip():
    raise RuntimeError("Documentation Agent returned an empty response")

if "next tool to be called" in documentation.lower():
    raise RuntimeError("The agent returned tool instructions instead of documentation")


# ============================================================
# Save Unreviewed Draft (Do Not Save It to Memory Yet)
# ============================================================

output_dir = PROJECT_ROOT / "outputs" / "documentation"
output_dir.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
output_path = output_dir / f"customer_service_draft_{timestamp}.md"

source_list = "\n".join(
    f"- [SOURCE {item['source_id']}] "
    f"{item['file_path']} :: "
    f"{item['class_name']}.{item['method_name']}"
    for item in sources
)

output_path.write_text(
    documentation + "\n\n## Retrieved Sources\n\n" + source_list + "\n",
    encoding="utf-8",
)


# ============================================================
# Results
# ============================================================

print("\n" + "=" * 60)
print("CODEMIGRATE AI - DOCUMENTATION AGENT")
print("=" * 60)
print(documentation)

print("\n--- Retrieved Sources ---")
for item in sources:
    print(
        f"[{item['source_id']}] "
        f"{item['class_name']}.{item['method_name']} | "
        f"CE Score: {item['cross_encoder_score']}"
    )
    print("   ", item["file_path"])

print("\nMemory notes used:", result["memory_notes_used"])
print("Automatic repair attempts:", result.get("repair_attempts", 0))
if result.get("review_warnings"):
    print("\n--- Documentation Review Warnings ---")
    for warning in result["review_warnings"]:
        print("-", warning)
print("Manual review required:", result.get("review_required", True))
print("Draft saved:", output_path)
print("Review the draft before saving any new facts to agent memory.")
print("\nDocumentation Agent execution: PASS")
