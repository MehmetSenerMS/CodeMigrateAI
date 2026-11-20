"""Test the fine-tuned CodeMigrate AI QLoRA migration endpoint from Spyder."""

from datetime import datetime, timezone
from pathlib import Path
from tkinter import Tk, simpledialog

from codemigrate.agents.code_migration_agent import CodeMigrationAgent
from codemigrate.settings import get_api_url


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

API_URL = get_api_url()

# Choose "sample" for a known migration or "file" for a project source.
SOURCE_MODE = "sample"
SOURCE_FILE = PROJECT_ROOT / "legacy" / "CustomerService.cs"

MIGRATION_INSTRUCTION = (
    "Migrate .NET Framework ConfigurationManager.AppSettings usage "
    "to modern .NET IConfiguration using constructor injection. "
    "Preserve class name, method name, return type and fallback value. "
    "Return only compilable C# code."
)

SAMPLE_LEGACY_CODE = """\
using System.Configuration;

public class NotificationSettings
{
    public string GetSenderName()
    {
        return ConfigurationManager.AppSettings["SenderName"]
            ?? "CodeMigrate";
    }
}
"""


# ============================================================
# Select Input
# ============================================================

if SOURCE_MODE == "sample":
    legacy_code = SAMPLE_LEGACY_CODE
    source_label = "sample_notification_settings"
    migration_instruction = MIGRATION_INSTRUCTION
elif SOURCE_MODE == "file":
    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(SOURCE_FILE)
    legacy_code = SOURCE_FILE.read_text(encoding="utf-8-sig")
    source_label = SOURCE_FILE.stem.lower()
    migration_instruction = (
        "Migrate this legacy C# file to modern .NET where necessary. "
        "Preserve public class and method names, return types, and observable "
        "behavior. Keep already-compatible code unchanged. "
        "Return only compilable C# code."
    )
else:
    raise ValueError("SOURCE_MODE must be 'sample' or 'file'")


# ============================================================
# API Authentication
# ============================================================

window = Tk()
window.withdraw()
try:
    api_key = simpledialog.askstring(
        "CodeMigrate AI",
        "Enter your Colab API key:",
        show="*",
        parent=window,
    )
finally:
    window.destroy()

if not api_key:
    raise ValueError("API key is required")


# ============================================================
# Run Fine-Tuned QLoRA Inference
# ============================================================

migration_agent = CodeMigrationAgent(
    base_url=API_URL,
    api_key=api_key,
    timeout=120,
)

print("=" * 60)
print("CODEMIGRATE AI - QLORA MIGRATION")
print("=" * 60)
print("Source mode:", SOURCE_MODE)
print("Endpoint:", migration_agent.endpoint)

result = migration_agent.migrate(
    instruction=migration_instruction,
    legacy_code=legacy_code,
)

print("\n--- Generated C# ---\n")
print(result.generated_code)
print("\nGeneration time:", result.generation_time)
print("Generated tokens:", result.generated_tokens)

if result.warnings:
    print("\n--- Automated Review Warnings ---")
    for warning in result.warnings:
        print("-", warning)
else:
    print("\nAutomated review warnings: 0")


# ============================================================
# Save a Draft for Compilation and Behavioral Review
# ============================================================

output_directory = PROJECT_ROOT / "outputs" / "migrations"
output_directory.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
draft_path = output_directory / f"{source_label}_migration_draft_{timestamp}.cs"
draft_path.write_text(result.generated_code + "\n", encoding="utf-8")

print("\nDraft saved:", draft_path)
print("No project source files were modified.")
print("Review and compile the draft before applying it.")
print("\nQLoRA migration inference: PASS")
