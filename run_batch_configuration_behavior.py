"""Behavioral regression test for the CodeMigrate NotificationSettings draft.

Runs four cases against the legacy source and the batch-generated draft.
The legacy ConfigurationManager.AppSettings interface is simulated locally
with NameValueCollection; no original file is modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


# Adjust only if your project layout differs.
PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = PROJECT_ROOT / "legacy"
BATCH_ROOT = PROJECT_ROOT / "outputs" / "batch_migration"
BATCH_RUN_DIR = None  # None: newest completed non-dry-run batch.
TARGET_FILE = "NotificationSettings.cs"
TARGET_FRAMEWORK = "net10.0"
DOTNET = "dotnet"
TIMEOUT_SECONDS = 180

SCENARIOS = [
    {"id": "configured", "present": True, "value": "Operations Team", "expected": "Operations Team"},
    {"id": "missing", "present": False, "value": None, "expected": "CodeMigrate"},
    {"id": "empty", "present": True, "value": "", "expected": ""},
    {"id": "whitespace", "present": True, "value": " ", "expected": " "},
]


SHIM_CS = r'''using System.Collections.Specialized;

namespace System.Configuration
{
    public static class ConfigurationManager
    {
        public static NameValueCollection AppSettings { get; } = new();
    }
}
'''


HARNESS_CS = r'''using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using LegacyApp;
#if LEGACY
using System.Configuration;
#else
using Microsoft.Extensions.Configuration;
#endif

public static class Program
{
    public static int Main(string[] args)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(args[0]));
        foreach (var item in document.RootElement.EnumerateArray())
        {
            string id = item.GetProperty("id").GetString()!;
            bool present = item.GetProperty("present").GetBoolean();
            string? value = item.GetProperty("value").GetString();
            try
            {
#if LEGACY
                ConfigurationManager.AppSettings.Clear();
                if (present)
                    ConfigurationManager.AppSettings["SenderName"] = value;
                string? result = new NotificationSettings().GetSenderName();
#else
                var values = new Dictionary<string, string?>();
                if (present)
                    values["SenderName"] = value;
                IConfiguration configuration = new ConfigurationBuilder()
                    .AddInMemoryCollection(values).Build();
                string? result = new NotificationSettings(configuration).GetSenderName();
#endif
                Console.WriteLine(JsonSerializer.Serialize(new {
                    id, success = true, result, error_type = (string?)null
                }));
            }
            catch (Exception exception)
            {
                Console.WriteLine(JsonSerializer.Serialize(new {
                    id, success = false, result = (string?)null,
                    error_type = exception.GetType().FullName
                }));
            }
        }
        return 0;
    }
}
'''


def select_batch() -> Path:
    if BATCH_RUN_DIR is not None:
        run_dir = Path(BATCH_RUN_DIR).resolve()
    else:
        candidates = []
        for report_path in BATCH_ROOT.glob("*/migration_report.json"):
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if report.get("metadata", {}).get("dry_run") is False and any(
                entry.get("relative_path") == TARGET_FILE
                and entry.get("status") == "draft_generated"
                for entry in report.get("entries", [])
            ):
                candidates.append(report_path.parent)
        if not candidates:
            raise FileNotFoundError("No completed batch containing NotificationSettings.cs")
        run_dir = max(candidates, key=lambda directory: directory.stat().st_mtime)
    if not run_dir.is_relative_to(BATCH_ROOT.resolve()):
        raise ValueError("Batch directory is outside the configured output root")
    return run_dir


def checked_paths(run_dir: Path) -> tuple[Path, Path]:
    source = (LEGACY_ROOT / TARGET_FILE).resolve()
    draft = (run_dir / "drafts" / TARGET_FILE).resolve()
    if not source.is_relative_to(LEGACY_ROOT.resolve()):
        raise ValueError("Legacy source escaped the expected directory")
    if not draft.is_relative_to((run_dir / "drafts").resolve()):
        raise ValueError("Draft escaped the expected directory")

    report = json.loads((run_dir / "migration_report.json").read_text(encoding="utf-8"))
    entries = [entry for entry in report["entries"]
               if entry.get("relative_path") == TARGET_FILE]
    if len(entries) != 1 or entries[0].get("status") != "draft_generated":
        raise ValueError("Unexpected manifest entry for NotificationSettings.cs")
    if not source.is_file() or not draft.is_file():
        raise FileNotFoundError("Legacy or draft NotificationSettings.cs is missing")
    expected_sha = entries[0].get("sha256")
    actual_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected_sha != actual_sha:
        raise ValueError("Original source differs from the saved batch manifest")
    return source, draft


def create_project(directory: Path, cs_source: Path, legacy: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cs_source, directory / TARGET_FILE)
    (directory / "Program.cs").write_text(HARNESS_CS, encoding="utf-8")
    if legacy:
        (directory / "LegacyConfigurationShim.cs").write_text(SHIM_CS, encoding="utf-8")
    project = directory / "ConfigurationBehavior.csproj"
    define = "LEGACY" if legacy else "MODERN"
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <PropertyGroup>\n'
        f'    <TargetFramework>{TARGET_FRAMEWORK}</TargetFramework>\n'
        '    <OutputType>Exe</OutputType>\n'
        '    <Nullable>enable</Nullable>\n'
        f'    <DefineConstants>{define}</DefineConstants>\n'
        '  </PropertyGroup>\n'
        '  <ItemGroup>\n'
        '    <FrameworkReference Include="Microsoft.AspNetCore.App" />\n'
        '  </ItemGroup>\n'
        '</Project>\n',
        encoding="utf-8",
    )
    return project


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
    })
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True,
        check=False, timeout=TIMEOUT_SECONDS,
    )


def execute_project(project: Path, cases_path: Path) -> dict:
    build = run_command(
        [DOTNET, "build", str(project), "--configuration", "Release",
         "--verbosity", "quiet", "--nologo", "--disable-build-servers",
         "-p:RestoreIgnoreFailedSources=true"],
        project.parent,
    )
    if build.returncode != 0:
        return {
            "status": "COMPILE_FAILED",
            "diagnostics": (build.stdout + "\n" + build.stderr)[-12000:],
        }

    dll = project.parent / "bin" / "Release" / TARGET_FRAMEWORK / "ConfigurationBehavior.dll"
    execution = run_command([DOTNET, str(dll), str(cases_path)], project.parent)
    if execution.returncode != 0:
        return {
            "status": "EXECUTION_FAILED",
            "diagnostics": (execution.stdout + "\n" + execution.stderr)[-12000:],
        }
    try:
        cases = [json.loads(line) for line in execution.stdout.splitlines()
                 if line.strip()]
    except json.JSONDecodeError as error:
        return {"status": "OUTPUT_INVALID", "error": str(error)}
    return {"status": "PASS", "cases": cases}


def compare_cases(legacy_output: dict, modern_output: dict) -> dict:
    if legacy_output.get("status") != "PASS" or modern_output.get("status") != "PASS":
        return {"status": "FAIL", "legacy": legacy_output, "modern": modern_output}
    old = {item["id"]: item for item in legacy_output["cases"]}
    new = {item["id"]: item for item in modern_output["cases"]}
    rows = []
    for scenario in SCENARIOS:
        key = scenario["id"]
        left, right = old.get(key), new.get(key)
        passed = (
            left is not None and right is not None
            and left.get("success") is True and right.get("success") is True
            and left.get("result") == right.get("result") == scenario["expected"]
        )
        rows.append({"scenario": key, "passed": passed, "expected": scenario["expected"],
                     "legacy": left, "modern": right})
    return {"status": "PASS" if all(row["passed"] for row in rows) else "FAIL",
            "passed": sum(row["passed"] for row in rows),
            "total": len(rows), "cases": rows,
            "scope": "NotificationSettings.GetSenderName; four specified inputs only"}


def main() -> None:
    run_dir = select_batch()
    legacy, draft = checked_paths(run_dir)
    print("CODEMIGRATE AI - CONFIGURATION BEHAVIORAL VALIDATION")
    print("Batch:", run_dir)
    print("Original:", legacy)
    print("Draft:", draft)
    print("Scenarios:", ", ".join(case["id"] for case in SCENARIOS))
    print("\nWARNING: Generated C# compilation and execution are NOT sandboxed.")
    print("Review the draft before authorizing code execution.")
    if input("Type RUN to approve compilation and execution: ").strip() != "RUN":
        print("Cancelled. Nothing was executed or modified.")
        return
    if shutil.which(DOTNET) is None and not Path(DOTNET).is_file():
        raise FileNotFoundError(f"dotnet SDK executable not found: {DOTNET}")

    with tempfile.TemporaryDirectory(prefix="codemigrate_config_behavior_") as tmp:
        workspace = Path(tmp)
        case_file = workspace / "cases.json"
        case_file.write_text(json.dumps(SCENARIOS), encoding="utf-8")
        old_project = create_project(workspace / "legacy", legacy, legacy=True)
        new_project = create_project(workspace / "modern", draft, legacy=False)
        old_result = execute_project(old_project, case_file)
        new_result = execute_project(new_project, case_file)
        result = compare_cases(old_result, new_result)

    result.update({
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(legacy), "draft_file": str(draft),
        "original_source_modified": False,
    })
    output_dir = run_dir / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"configuration_behavior_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}.json"
    output_path = output_dir / filename
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nCONFIGURATION BEHAVIOR RESULTS")
    for row in result.get("cases", []):
        print(f"{row['scenario']:<14} {'PASS' if row['passed'] else 'FAIL'}")
    print("Status:", result["status"])
    print("Passed:", result.get("passed", 0), "/", result.get("total", 4))
    print("Report:", output_path)
    print("Original and draft files were not modified.")


if __name__ == "__main__":
    main()
