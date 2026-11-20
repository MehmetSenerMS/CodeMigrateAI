"""Compile and behavior-test the latest CodeMigrate AI C# migration draft.

This first scenario validates LegacyApp.CustomerService. For another C# class,
update SOURCE_FILE, DRAFT_PATTERN, and TEST_HARNESS together.

Compiling and running generated source code is not sandboxed on Windows.
Read the generated draft and approve execution before continuing.
"""

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_FILE = PROJECT_ROOT / "legacy" / "CustomerService.cs"

# Use the newest draft from run_multi_agent_pipeline.py.
DRAFT_DIRECTORY = PROJECT_ROOT / "outputs" / "multi_agent"
DRAFT_PATTERN = "customerservice_migration_draft_*.cs"

TARGET_FRAMEWORK = "net10.0"
TEST_IDS = [-1001, -1, 0, 1, 7, 1001, 2147483647]
COMMAND_TIMEOUT_SECONDS = 180

# The same C# harness is compiled with both the legacy and migrated source.
# Adjust it when migrating a different class or method.
TEST_HARNESS = """\
using System;
using System.Text.Json;
using LegacyApp;

int[] ids = { -1001, -1, 0, 1, 7, 1001, int.MaxValue };

foreach (int id in ids)
{
    var service = new CustomerService();

    try
    {
        string name = service.GetCustomerName(id);
        bool active = service.IsCustomerActive(id);

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            id,
            name,
            active,
            exception = (string?)null
        }));
    }
    catch (Exception ex)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            id,
            name = (string?)null,
            active = (bool?)null,
            exception = ex.GetType().FullName
        }));
    }
}
"""


# ============================================================
# Find Sources and Verify SDK
# ============================================================

dotnet = shutil.which("dotnet")
if dotnet is None:
    raise RuntimeError(".NET SDK not found. Run 'dotnet --list-sdks' in PowerShell.")

if not SOURCE_FILE.is_file():
    raise FileNotFoundError(f"Missing legacy code: {SOURCE_FILE}")

drafts = list(DRAFT_DIRECTORY.glob(DRAFT_PATTERN))
if not drafts:
    raise FileNotFoundError(
        f"No migration draft matching '{DRAFT_PATTERN}' in {DRAFT_DIRECTORY}"
    )

draft_file = max(drafts, key=lambda item: item.stat().st_mtime)
legacy_code = SOURCE_FILE.read_text(encoding="utf-8-sig")
migrated_code = draft_file.read_text(encoding="utf-8-sig")

sdk_check = subprocess.run(
    [dotnet, "--list-sdks"],
    capture_output=True,
    text=True,
    timeout=20,
    check=True,
)
if not any(line.strip().startswith("10.") for line in sdk_check.stdout.splitlines()):
    raise RuntimeError("This validation script requires the .NET 10 SDK")


# ============================================================
# Confirm Execution of Generated C# Code
# ============================================================

print("=" * 65)
print("CODEMIGRATE AI - COMPILATION AND BEHAVIORAL VALIDATION")
print("=" * 65)
print("Legacy source:", SOURCE_FILE)
print("Migration draft:", draft_file)
print("Target framework:", TARGET_FRAMEWORK)
print("Test inputs:", TEST_IDS)

print("\n--- Migrated Source for Review ---\n")
print(migrated_code)

print(
    "\nIMPORTANT: dotnet build/run will compile and execute the generated "
    "C# code on this computer. Do this only if you have inspected the draft."
)

approval = input("Type RUN to approve compilation and execution: ").strip()
if approval != "RUN":
    print("Validation cancelled. No C# code was executed.")
    raise SystemExit(0)


# ============================================================
# Build and Run Each Version in an Isolated Project Folder
# ============================================================

timestamp = (
    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    + "_" + uuid4().hex[:6]
)
RUN_DIRECTORY = PROJECT_ROOT / "outputs" / "validation" / timestamp

PROJECT_FILE = f"""\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{TARGET_FRAMEWORK}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <RestoreIgnoreFailedSources>true</RestoreIgnoreFailedSources>
  </PropertyGroup>
</Project>
"""


def build_and_execute(label: str, source: str) -> dict:
    directory = RUN_DIRECTORY / label
    directory.mkdir(parents=True, exist_ok=False)

    project = directory / "Validation.csproj"
    project.write_text(PROJECT_FILE, encoding="utf-8")
    (directory / "Migration.cs").write_text(source, encoding="utf-8")
    (directory / "Program.cs").write_text(TEST_HARNESS, encoding="utf-8")

    env = os.environ.copy()
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
    env["DOTNET_NOLOGO"] = "1"

    start_time = time.perf_counter()
    build = subprocess.run(
        [dotnet, "build", str(project), "-c", "Release", "--nologo", "-v", "quiet"],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        env=env,
        cwd=directory,
    )

    result = {
        "compiled": build.returncode == 0,
        "build_log": (build.stdout + "\n" + build.stderr).strip(),
        "ran": False,
        "exit_code": None,
        "runtime_output": "",
        "elapsed_seconds": None,
        "project_path": str(project),
    }

    if build.returncode != 0:
        result["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
        return result

    execution = subprocess.run(
        [dotnet, "run", "--project", str(project), "-c", "Release", "--no-build", "--no-launch-profile"],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        env=env,
        cwd=directory,
    )

    result["ran"] = execution.returncode == 0
    result["exit_code"] = execution.returncode
    result["runtime_output"] = execution.stdout.strip()
    result["runtime_error"] = execution.stderr.strip()
    result["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
    return result


legacy = build_and_execute("legacy", legacy_code)
migrated = build_and_execute("migrated", migrated_code)


# ============================================================
# Compare Actual Output for Identical Test Cases
# ============================================================

comparison = []
behavior_pass = False

if legacy["ran"] and migrated["ran"]:
    try:
        legacy_rows = [
            json.loads(line)
            for line in legacy["runtime_output"].splitlines()
            if line.strip()
        ]
        migrated_rows = [
            json.loads(line)
            for line in migrated["runtime_output"].splitlines()
            if line.strip()
        ]

        if len(legacy_rows) != len(TEST_IDS) or len(migrated_rows) != len(TEST_IDS):
            raise ValueError("Unexpected number of behavioral test results")

        for expected_id, old, new in zip(TEST_IDS, legacy_rows, migrated_rows):
            passed = old == new and old.get("id") == expected_id
            comparison.append({
                "customer_id": expected_id,
                "legacy": old,
                "migrated": new,
                "passed": passed,
            })

        behavior_pass = all(row["passed"] for row in comparison)
    except (ValueError, TypeError, KeyError) as error:
        print("Unable to compare behavioral test output:", error)

report = {
    "legacy_source": str(SOURCE_FILE),
    "migration_draft": str(draft_file),
    "target_framework": TARGET_FRAMEWORK,
    "legacy": legacy,
    "migrated": migrated,
    "behavioral_test_cases": comparison,
    "behavioral_pass": behavior_pass,
}

RUN_DIRECTORY.mkdir(parents=True, exist_ok=True)
report_path = RUN_DIRECTORY / "validation_report.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


# ============================================================
# Results
# ============================================================

print("\n--- Compilation Results ---")
for label, record in (("legacy", legacy), ("migrated", migrated)):
    print(f"{label}: {'PASS' if record['compiled'] else 'FAIL'}")
    if not record["compiled"]:
        print(record["build_log"][-1500:])

print("\n--- Behavioral Results ---")
for row in comparison:
    print(
        f"ID={row['customer_id']:>11} | "
        f"{'PASS' if row['passed'] else 'FAIL'} | "
        f"old={row['legacy']} | new={row['migrated']}"
    )

print("\nLegacy execution:", "PASS" if legacy["ran"] else "FAIL")
print("Migrated execution:", "PASS" if migrated["ran"] else "FAIL")
print("Behavioral equivalence:", "PASS" if behavior_pass else "FAIL")
print("Report saved:", report_path)

if legacy["compiled"] and migrated["compiled"] and behavior_pass:
    print("\nC# compilation and behavioral validation: PASS")
else:
    print("\nC# compilation and behavioral validation: FAIL")



