"""Validate CodeMigrate batch drafts without changing the original C# files.

Run this file from Spyder after run_batch_migration.py has completed.
Compilation and behavior execution are gated by explicit approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration: adjust these values for a different project or batch.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = PROJECT_ROOT / "legacy"
BATCH_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "batch_migration"
BATCH_RUN_DIR = None  # None selects the newest successful non-dry-run batch.

DOTNET = "dotnet"
TARGET_FRAMEWORK = "net10.0"
USE_ASPNET_CORE_FRAMEWORK = True  # Needed for IConfiguration and ASP.NET Core MVC.
RUN_COMPILATION = True
RUN_BEHAVIOR = True
BEHAVIOR_CASES_PATH = (
    PROJECT_ROOT / "evaluation" / "batch_validation" / "behavior_cases.json"
)
COMMAND_TIMEOUT_SECONDS = 180


METHOD_RE = re.compile(
    r"\bpublic\s+(?:(?:async|static|virtual|override|sealed|new)\s+)*"
    r"([\w.<>?,\[\]]+)\s+([A-Za-z_]\w*)\s*"
    r"(?:<[^>\r\n]+>)?\s*\("
)
LEGACY_API_RE = re.compile(
    r"\b(?:ConfigurationManager|System\.Web|HttpNotFound|"
    r"IsSecureConnection|UserHostAddress|System\.Data\.Entity)\b"
)


BEHAVIOR_RUNNER = r'''using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;

public static class BehaviorRunner
{
    static Type ResolveType(string name) =>
        Type.GetType(name, throwOnError: true)!;

    static object? RunCase(JsonElement item)
    {
        var type = Assembly.GetExecutingAssembly().GetType(
            item.GetProperty("type").GetString()!, throwOnError: true)!;

        if (item.TryGetProperty("type_generic_arguments", out var classTypes))
        {
            type = type.MakeGenericType(
                classTypes.EnumerateArray()
                    .Select(e => ResolveType(e.GetString()!)).ToArray());
        }

        var args = item.GetProperty("args").EnumerateArray().ToArray();
        var name = item.GetProperty("method").GetString();
        var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.Name == name && m.GetParameters().Length == args.Length)
            .ToArray();

        if (methods.Length != 1)
            throw new InvalidOperationException("Method missing or ambiguous: " + name);

        var method = methods[0];
        if (item.TryGetProperty("method_generic_arguments", out var methodTypes))
        {
            method = method.MakeGenericMethod(
                methodTypes.EnumerateArray()
                    .Select(e => ResolveType(e.GetString()!)).ToArray());
        }

        var parameters = method.GetParameters();
        var values = args.Select((arg, i) => {
            var parameterType = parameters[i].ParameterType;
            // When a generic method accepts object, preserve the boxed value's
            // runtime type so a direct (T)value cast can be tested meaningfully.
            if (parameterType == typeof(object) && method.IsGenericMethod &&
                method.GetGenericArguments().Length == 1)
                parameterType = method.GetGenericArguments()[0];
            return JsonSerializer.Deserialize(arg.GetRawText(), parameterType);
        }).ToArray();

        var instance = Activator.CreateInstance(type)
            ?? throw new InvalidOperationException("Cannot construct: " + type.FullName);
        object? result = method.Invoke(instance, values);
        if (result is Task task)
        {
            task.GetAwaiter().GetResult();
            result = task.GetType().GetProperty("Result")?.GetValue(task);
        }
        return result;
    }

    public static int Main(string[] args)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(args[0]));
        foreach (var item in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            var id = item.GetProperty("id").GetString();
            try
            {
                Console.WriteLine(JsonSerializer.Serialize(new {
                    id, success = true, value = RunCase(item), error_type = (string?)null
                }));
            }
            catch (Exception ex)
            {
                var actual = ex is TargetInvocationException && ex.InnerException != null
                    ? ex.InnerException : ex;
                Console.WriteLine(JsonSerializer.Serialize(new {
                    id, success = false, value = (object?)null,
                    error_type = actual.GetType().FullName
                }));
            }
        }
        return 0;
    }
}
'''


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def is_within(path: Path, directory: Path) -> bool:
    return path.resolve().is_relative_to(directory.resolve())


def select_run_dir() -> Path:
    if BATCH_RUN_DIR is not None:
        return Path(BATCH_RUN_DIR).resolve()
    if not BATCH_OUTPUT_ROOT.is_dir():
        raise FileNotFoundError(f"Batch directory not found: {BATCH_OUTPUT_ROOT}")
    candidates = []
    for report_path in BATCH_OUTPUT_ROOT.glob("*/migration_report.json"):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (not data.get("metadata", {}).get("dry_run", True)
                and any(x.get("status") == "draft_generated"
                        for x in data.get("entries", []))):
            candidates.append(report_path.parent)
    if not candidates:
        raise RuntimeError("No completed live batch found. Set BATCH_RUN_DIR explicitly.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def public_methods(code: str) -> dict[str, str]:
    return {name: result_type for result_type, name in METHOD_RE.findall(code)}


def audit_entry(entry: dict, batch_root: Path) -> dict:
    relative = Path(str(entry["relative_path"]).replace("\\", "/"))
    outcome = {"relative_path": str(relative), "integrity": "FAILED", "warnings": []}
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        outcome["warnings"].append("Unsafe relative path in migration report")
        return outcome

    source = LEGACY_ROOT / relative
    draft = batch_root / "drafts" / relative
    if not (is_within(source, LEGACY_ROOT) and is_within(draft, batch_root / "drafts")):
        outcome["warnings"].append("A file resolves outside an approved directory")
        return outcome
    if not source.is_file() or not draft.is_file():
        outcome["warnings"].append("Original or draft file is missing")
        return outcome

    actual_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_sha != entry.get("sha256"):
        outcome["warnings"].append("Original file changed after the batch scan")
        return outcome

    original = source.read_text(encoding="utf-8-sig")
    migrated = draft.read_text(encoding="utf-8-sig")
    warnings = outcome["warnings"]
    outcome["integrity"] = "PASS"
    outcome["changed"] = original.replace("\r\n", "\n").strip() != migrated.replace("\r\n", "\n").strip()

    if re.search(r"\bConfiguration\s*\.\s*(AppSettings|ConnectionStrings)\b", migrated):
        warnings.append("Invalid migration pattern: Configuration.AppSettings/ConnectionStrings")
    if "using System.Configuration;" in migrated:
        warnings.append("Obsolete System.Configuration import is still present")
    if "ConfigurationManager" in migrated:
        warnings.append("Legacy ConfigurationManager API is still present")

    before = public_methods(original)
    after = public_methods(migrated)
    missing = sorted(set(before) - set(after))
    if missing:
        warnings.append("Public method names missing: " + ", ".join(missing))
    for name in sorted(set(before) & set(after)):
        if before[name] != after[name]:
            warnings.append(
                f"Review return type of {name}: {before[name]} -> {after[name]}"
            )
    if outcome["changed"] and not LEGACY_API_RE.search(original):
        warnings.append("Changes made even though no recognized legacy API was found")
    if not outcome["changed"]:
        outcome["note"] = "No functional change detected by text comparison"
    return outcome


def create_project(workspace: Path, files: dict[Path, Path], behavior: bool) -> Path:
    source_dir = workspace / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    for relative, source in files.items():
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if behavior:
        (source_dir / "BehaviorRunner.cs").write_text(BEHAVIOR_RUNNER, encoding="utf-8")
    output_type = "Exe" if behavior else "Library"
    project = workspace / "BatchValidation.csproj"
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <PropertyGroup>\n'
        f'    <TargetFramework>{TARGET_FRAMEWORK}</TargetFramework>\n'
        f'    <OutputType>{output_type}</OutputType>\n'
        '    <Nullable>enable</Nullable>\n'
        '    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>\n'
        '    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>\n'
        '  </PropertyGroup>\n'
        + ('  <ItemGroup><FrameworkReference Include="Microsoft.AspNetCore.App" />'
           '</ItemGroup>\n' if USE_ASPNET_CORE_FRAMEWORK else '')
        + '  <ItemGroup><Compile Include="sources/**/*.cs" /></ItemGroup>\n'
        '</Project>\n',
        encoding="utf-8",
    )
    return project


def command(args: list[str], cwd: Path) -> dict:
    env = os.environ.copy()
    env.update({
        "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
    })
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, text=True,
            capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS, check=False,
        )
        return {"ok": result.returncode == 0, "returncode": result.returncode,
                "output": (result.stdout + "\n" + result.stderr)[-16000:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "returncode": None, "output": str(error)}


def build(project: Path) -> dict:
    return command(
        [DOTNET, "build", str(project), "--configuration", "Release",
         "--nologo", "--verbosity", "quiet", "--disable-build-servers",
         "-p:RestoreIgnoreFailedSources=true"], project.parent
    )


def compile_batch(run_dir: Path, entries: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="codemigrate_compile_") as temporary:
        files = {
            Path(e["relative_path"]): run_dir / "drafts" / e["relative_path"]
            for e in entries
        }
        project = create_project(Path(temporary), files, behavior=False)
        return build(project)


def run_behavior(run_dir: Path, entries: list[dict]) -> dict:
    if not BEHAVIOR_CASES_PATH.is_file():
        return {"status": "NOT_RUN", "reason": "Missing behavior_cases.json"}
    specification = json.loads(BEHAVIOR_CASES_PATH.read_text(encoding="utf-8"))
    selection = specification.get("source_files", [])
    cases = specification.get("cases", [])
    if not selection or not cases:
        return {"status": "NOT_RUN", "reason": "Empty behavior specification"}
    available = {e["relative_path"] for e in entries}
    if any(item not in available for item in selection):
        return {"status": "NOT_RUN", "reason": "Behavior source not in eligible entries"}
    if len(set(selection)) != len(selection) or len(set(x["id"] for x in cases)) != len(cases):
        return {"status": "NOT_RUN", "reason": "Duplicate source or behavior case ID"}

    try:
        source_files = {Path(name): LEGACY_ROOT / name for name in selection}
        draft_files = {Path(name): run_dir / "drafts" / name for name in selection}
        with tempfile.TemporaryDirectory(prefix="codemigrate_behavior_") as temporary:
            root = Path(temporary)
            legacy_project = create_project(root / "legacy", source_files, behavior=True)
            modern_project = create_project(root / "modern", draft_files, behavior=True)
            before_build = build(legacy_project)
            after_build = build(modern_project)
            if not before_build["ok"] or not after_build["ok"]:
                return {"status": "FAIL", "legacy_compile": before_build,
                        "modern_compile": after_build}

            outputs = {}
            for name, project in (("legacy", legacy_project), ("modern", modern_project)):
                dll = project.parent / "bin" / "Release" / TARGET_FRAMEWORK / "BatchValidation.dll"
                result = command([DOTNET, str(dll), str(BEHAVIOR_CASES_PATH)], project.parent)
                if not result["ok"]:
                    return {"status": "FAIL", "execution": name, "details": result}
                rows = [json.loads(line) for line in result["output"].splitlines() if line.strip()]
                outputs[name] = {row["id"]: row for row in rows}

            details = []
            for item in cases:
                key = item["id"]
                old, new = outputs["legacy"].get(key), outputs["modern"].get(key)
                passed = (old is not None and new is not None and
                          old.get("success") == new.get("success") and
                          old.get("value") == new.get("value") and
                          old.get("error_type") == new.get("error_type"))
                details.append({"id": key, "passed": passed, "legacy": old, "modern": new})
            return {"status": "PASS" if all(x["passed"] for x in details) else "FAIL",
                    "passed": sum(x["passed"] for x in details),
                    "total": len(details), "cases": details,
                    "note": "Only the explicitly listed test cases were exercised."}
    except (ValueError, TypeError, OSError, KeyError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "reason": str(error)}


def main() -> None:
    run_dir = select_run_dir()
    if not is_within(run_dir, BATCH_OUTPUT_ROOT):
        raise ValueError("Selected batch directory is outside BATCH_OUTPUT_ROOT")
    report = json.loads((run_dir / "migration_report.json").read_text(encoding="utf-8"))
    entries = [e for e in report["entries"] if e.get("status") == "draft_generated"]
    audited = [audit_entry(e, run_dir) for e in entries]
    valid_entries = [e for e, review in zip(entries, audited)
                     if review["integrity"] == "PASS"]

    print("CODEMIGRATE AI - BATCH VALIDATION")
    print("Batch:", run_dir)
    for row in audited:
        print(f"{row['relative_path']}: integrity={row['integrity']}, "
              f"review_warnings={len(row['warnings'])}")
        for warning in row["warnings"]:
            print("  -", warning)

    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_run_dir": str(run_dir),
        "source_integrity": audited,
        "compilation": {"status": "NOT_RUN"},
        "behavior": {"status": "NOT_RUN"},
        "original_files_modified": False,
        "approval_status": "human_review_required",
    }
    output_path = run_dir / "validation" / "batch_validation_report.json"

    if len(valid_entries) != len(entries):
        print("Integrity check failed. Compilation and behavior evaluation are blocked.")
    elif RUN_COMPILATION or RUN_BEHAVIOR:
        if not shutil.which(DOTNET) and not Path(DOTNET).is_file():
            print("dotnet SDK executable not found. Check DOTNET setting and PATH.")
        else:
            print("\nWARNING: Compiling and running generated C# is NOT sandboxed.")
            print("Inspect all drafts and test cases before authorizing execution.")
            if input("Type RUN to approve compilation and behavior tests: ").strip() == "RUN":
                if RUN_COMPILATION:
                    compilation = compile_batch(run_dir, valid_entries)
                    result["compilation"] = {
                        "status": "PASS" if compilation["ok"] else "FAIL",
                        **compilation,
                    }
                    print("Compilation:", result["compilation"]["status"])
                    if not compilation["ok"]:
                        print(compilation["output"][-4000:])
                if RUN_BEHAVIOR:
                    result["behavior"] = run_behavior(run_dir, valid_entries)
                    print("Behavior:", result["behavior"]["status"])
                    if "passed" in result["behavior"]:
                        print("Cases:", result["behavior"]["passed"], "/",
                              result["behavior"]["total"])
            else:
                print("Execution cancelled. Static review only.")

    save_json(output_path, result)
    print("Report:", output_path)
    print("All original C# files were left unchanged.")


if __name__ == "__main__":
    main()
