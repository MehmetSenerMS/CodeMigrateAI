"""Compile and behavior-test a ConfigurationManager -> IConfiguration migration.

The legacy ConfigurationManager.AppSettings API is simulated by a small
in-memory stub, so no .NET Framework targeting pack is required. The modern
code uses Microsoft's ASP.NET Core framework reference, included with the SDK.

This is a focused contract test, not a full application integration test.
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
SOURCE_FILE = PROJECT_ROOT / "legacy" / "NotificationSettings.cs"
DRAFT_DIRECTORY = PROJECT_ROOT / "outputs" / "multi_agent"
DRAFT_PATTERN = "notificationsettings_migration_draft_*.cs"

TARGET_FRAMEWORK = "net10.0"
COMMAND_TIMEOUT_SECONDS = 180

EXPECTED_RESULTS = {
    "configured": "Operations Team",
    "missing": "CodeMigrate",
    "empty": "",
    "whitespace": " ",
}


# ============================================================
# C# Test Harness
# ============================================================

PROJECT_FILE = f"""\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{TARGET_FRAMEWORK}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <RestoreIgnoreFailedSources>true</RestoreIgnoreFailedSources>
  </PropertyGroup>
  <ItemGroup>
    <FrameworkReference Include="Microsoft.AspNetCore.App" />
  </ItemGroup>
</Project>
"""

# This stub only emulates the AppSettings indexer used in the legacy source.
LEGACY_CONFIGURATION_STUB = """\
using System.Collections.Specialized;

namespace System.Configuration
{
    public static class ConfigurationManager
    {
        public static NameValueCollection AppSettings { get; } = new();
    }
}
"""

TEST_HARNESS = """\
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using LegacyApp;
using Microsoft.Extensions.Configuration;

var cases = new (string Name, string? Value)[]
{
    ("configured", "Operations Team"),
    ("missing", null),
    ("empty", ""),
    ("whitespace", " "),
};

foreach (var item in cases)
{
    System.Configuration.ConfigurationManager.AppSettings.Clear();
    var configData = new Dictionary<string, string?>();

    if (item.Value is not null)
    {
        System.Configuration.ConfigurationManager.AppSettings["SenderName"] = item.Value;
        configData["SenderName"] = item.Value;
    }

    IConfiguration configuration = new ConfigurationBuilder()
        .AddInMemoryCollection(configData)
        .Build();

    Type settingsType = typeof(NotificationSettings);
    ConstructorInfo? injectionConstructor = settingsType.GetConstructor(
        new[] { typeof(IConfiguration) }
    );

    object instance = injectionConstructor is null
        ? Activator.CreateInstance(settingsType)!
        : injectionConstructor.Invoke(new object[] { configuration });

    MethodInfo method = settingsType.GetMethod("GetSenderName")
        ?? throw new InvalidOperationException("GetSenderName missing");

    try
    {
        string? value = (string?)method.Invoke(instance, null);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            scenario = item.Name,
            value,
            exception = (string?)null
        }));
    }
    catch (TargetInvocationException error)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            scenario = item.Name,
            value = (string?)null,
            exception = error.InnerException?.GetType().FullName
        }));
    }
}
"""


# ============================================================
# Locate Inputs and Check .NET SDK
# ============================================================

dotnet = shutil.which("dotnet")
if not dotnet:
    raise RuntimeError("dotnet executable not found in PATH")

if not SOURCE_FILE.is_file():
    raise FileNotFoundError(SOURCE_FILE)

drafts = list(DRAFT_DIRECTORY.glob(DRAFT_PATTERN))
if not drafts:
    raise FileNotFoundError(f"No migration draft found: {DRAFT_PATTERN}")

draft_file = max(drafts, key=lambda path: path.stat().st_mtime)
legacy_code = SOURCE_FILE.read_text(encoding="utf-8-sig")
modern_code = draft_file.read_text(encoding="utf-8-sig")

sdk_result = subprocess.run(
    [dotnet, "--list-sdks"],
    text=True,
    capture_output=True,
    timeout=20,
    check=True,
)

if not any(line.lstrip().startswith("10.") for line in sdk_result.stdout.splitlines()):
    raise RuntimeError("The .NET 10 SDK is required for this test")


# ============================================================
# Review Code Before Executing Locally
# ============================================================

print("=" * 64)
print("CODEMIGRATE AI - CONFIGURATION BEHAVIOR TEST")
print("=" * 64)
print("Legacy:", SOURCE_FILE)
print("QLoRA draft:", draft_file)
print("Target framework:", TARGET_FRAMEWORK)

print("\n--- QLoRA C# Draft ---\n")
print(modern_code)
print(
    "\nCompilation and execution of generated C# code is not sandboxed. "
    "Inspect the draft before approving."
)

if input("Type RUN to compile and execute both versions: ").strip() != "RUN":
    print("Cancelled. No C# source was compiled or executed.")
    raise SystemExit(0)


# ============================================================
# Compile and Execute Both Variants
# ============================================================

identifier = (
    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    + "_" + uuid4().hex[:6]
)
RUN_DIRECTORY = PROJECT_ROOT / "outputs" / "validation" / "configuration" / identifier


def build_and_run(label: str, source_code: str) -> dict:
    directory = RUN_DIRECTORY / label
    directory.mkdir(parents=True, exist_ok=False)

    project = directory / "Validation.csproj"
    project.write_text(PROJECT_FILE, encoding="utf-8")
    (directory / "Migration.cs").write_text(source_code, encoding="utf-8")
    (directory / "LegacyConfigurationStub.cs").write_text(
        LEGACY_CONFIGURATION_STUB, encoding="utf-8"
    )
    (directory / "Program.cs").write_text(TEST_HARNESS, encoding="utf-8")

    env = os.environ.copy()
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
    env["DOTNET_NOLOGO"] = "1"

    start = time.perf_counter()
    build = subprocess.run(
        [dotnet, "build", str(project), "-c", "Release", "--nologo", "-v", "quiet"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        env=env,
    )

    result = {
        "compiled": build.returncode == 0,
        "build_log": (build.stdout + "\n" + build.stderr).strip(),
        "ran": False,
        "runtime_output": "",
        "runtime_error": "",
        "elapsed_seconds": None,
    }

    if not result["compiled"]:
        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        return result

    execution = subprocess.run(
        [dotnet, "run", "--project", str(project), "-c", "Release", "--no-build", "--no-launch-profile"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        env=env,
    )
    result["ran"] = execution.returncode == 0
    result["runtime_output"] = execution.stdout.strip()
    result["runtime_error"] = execution.stderr.strip()
    result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    return result


legacy = build_and_run("legacy", legacy_code)
modern = build_and_run("modern", modern_code)


# ============================================================
# Validate Every Scenario and Save Report
# ============================================================

rows = []
behavior_pass = False

if legacy["ran"] and modern["ran"]:
    try:
        original = [json.loads(line) for line in legacy["runtime_output"].splitlines()]
        generated = [json.loads(line) for line in modern["runtime_output"].splitlines()]

        if len(original) != len(EXPECTED_RESULTS) or len(generated) != len(EXPECTED_RESULTS):
            raise ValueError("Unexpected number of results")

        for name, old, new in zip(EXPECTED_RESULTS, original, generated):
            passed = (
                old.get("scenario") == name
                and new.get("scenario") == name
                and old.get("value") == EXPECTED_RESULTS[name]
                and new.get("value") == EXPECTED_RESULTS[name]
                and old.get("exception") is None
                and new.get("exception") is None
            )
            rows.append({"scenario": name, "legacy": old, "modern": new, "passed": passed})

        behavior_pass = all(row["passed"] for row in rows)
    except (ValueError, TypeError) as error:
        print("Behavioral comparison error:", error)

report = {
    "legacy_source": str(SOURCE_FILE),
    "generated_draft": str(draft_file),
    "legacy_build": legacy,
    "modern_build": modern,
    "scenarios": rows,
    "behavioral_pass": behavior_pass,
    "legacy_configuration_emulated": True,
}

RUN_DIRECTORY.mkdir(parents=True, exist_ok=True)
report_file = RUN_DIRECTORY / "configuration_validation_report.json"
report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n--- Compilation ---")
for name, item in (("legacy", legacy), ("modern", modern)):
    print(f"{name}: {'PASS' if item['compiled'] else 'FAIL'}")
    if not item["compiled"]:
        print(item["build_log"][-1800:])

print("\n--- Behavioral Tests ---")
for row in rows:
    print(
        f"{row['scenario']:12} | {'PASS' if row['passed'] else 'FAIL'} | "
        f"old={row['legacy']['value']!r} | new={row['modern']['value']!r}"
    )

print("\nBehavioral equivalence:", "PASS" if behavior_pass else "FAIL")
print("Report:", report_file)

if legacy["compiled"] and modern["compiled"] and behavior_pass:
    print("\nConfiguration migration compilation and behavior: PASS")
else:
    print("\nConfiguration migration compilation and behavior: FAIL")



