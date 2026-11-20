from pathlib import Path
import tkinter as tk
from tkinter import simpledialog

from codemigrate.llm.remote_client import RemoteMigrationClient
from codemigrate.pipeline.migration_pipeline import MigrationPipeline


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

PROJECT_ROOT = Path(r"C:\CodeMigrateAI")

API_URL = (
    "https://gods-sensitive-marathon-overhead.trycloudflare.com/"
)


# ------------------------------------------------------------
# API Authentication
# ------------------------------------------------------------

root = tk.Tk()
root.withdraw()

try:

    API_KEY = simpledialog.askstring(
        "CodeMigrate AI",
        "Enter your API key:",
        show="*",
        parent=root
    )

finally:
    root.destroy()


if not API_KEY:
    raise ValueError("API key is required")


# ------------------------------------------------------------
# Initialize Components
# ------------------------------------------------------------

model_client = RemoteMigrationClient(
    base_url=API_URL,
    api_key=API_KEY
)

pipeline = MigrationPipeline(
    model_client=model_client
)


try:

    # --------------------------------------------------------
    # Index Legacy Codebase
    # --------------------------------------------------------

    print("=" * 60)
    print("CODEMIGRATE AI - MIGRATION PIPELINE")
    print("=" * 60)

    indexed_count = pipeline.index_codebase(
        PROJECT_ROOT / "legacy"
    )

    print("Indexed C# methods:", indexed_count)

    # --------------------------------------------------------
    # Retrieve Relevant Code
    # --------------------------------------------------------

    query = (
        "Find the method that checks whether "
        "a customer is active"
    )

    print("\nRetrieval query:", query)

    results = pipeline.retrieve(
        query=query,
        top_k=5
    )

    if not results:
        raise RuntimeError("No matching code found")

    print("\n--- Retrieved Methods ---")

    for rank, item in enumerate(results, start=1):

        print(
            f"{rank}. "
            f"{item['class_name']}."
            f"{item['method_name']} "
            f"| CE Score: "
            f"{item['cross_encoder_score']:.4f}"
        )

    # --------------------------------------------------------
    # Select Migration Target
    # --------------------------------------------------------

    selection = int(
        input("\nSelect method number: ")
    )

    if not 1 <= selection <= len(results):
        raise ValueError("Invalid method selection")

    selected_chunk = results[selection - 1]

    print("\nSelected method:")
    print(
        selected_chunk["class_name"],
        selected_chunk["method_name"]
    )

    # --------------------------------------------------------
    # Migration Instruction
    # --------------------------------------------------------

    instruction = (
        "Migrate this legacy C# method to modern .NET. "
        "Preserve the original business logic, method name, "
        "return type, parameters and null behavior. "
        "Do not introduce unnecessary changes. "
        "Return only valid C# code."
    )

    # --------------------------------------------------------
    # Generate Modern Code
    # --------------------------------------------------------

    migration_result = pipeline.migrate(
        selected_chunk=selected_chunk,
        instruction=instruction
    )

    print("\n" + "=" * 60)
    print("LEGACY C# CODE")
    print("=" * 60)

    print(migration_result["legacy_code"])

    print("\n" + "=" * 60)
    print("MIGRATED C# CODE")
    print("=" * 60)

    print(migration_result["modern_code"])

    print("\n--- Migration Statistics ---")

    print(
        "Generation time:",
        migration_result["generation_time"]
    )

    print(
        "Generated tokens:",
        migration_result["generated_tokens"]
    )

    print("\nMigration pipeline: PASS")

finally:

    model_client.close()