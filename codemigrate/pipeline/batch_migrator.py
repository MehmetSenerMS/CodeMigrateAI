"""Safe, file-based batch migration helpers with no remote dependencies.

The scanner never changes source files. Generated drafts are written only to
the configured run output directory, preserving the original relative paths.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import re


SKIP_DIR_NAMES = frozenset({
    ".git", ".vs", ".vscode", "bin", "obj", "packages", "node_modules",
    "TestResults", ".idea", ".venv", "venv", "outputs", "evaluation",
})
SKIP_FILE_ENDINGS = (".Designer.cs", ".g.cs", ".g.i.cs", ".AssemblyAttributes.cs")
SKIP_DIR_NAMES_FOLDED = frozenset(name.casefold() for name in SKIP_DIR_NAMES)


@dataclass(frozen=True)
class SourceRecord:
    relative_path: str
    absolute_path: str
    size_bytes: int
    sha256: str | None
    scan_status: str
    reason: str | None = None


def make_run_directory(root: Path) -> Path:
    """Create a new output directory; never reuse or overwrite an old run."""
    root.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = root / f"{stamp}_{uuid4().hex[:8]}"
        try:
            target.mkdir()
        except FileExistsError:
            continue
        return target


def scan_csharp_sources(
    source_root: Path,
    *,
    max_files: int = 20,
    max_source_chars: int = 3000,
    max_file_bytes: int = 15000,
):
    """Return (records, source_texts) without following directory symlinks."""
    if max_files < 1 or max_source_chars < 1 or max_file_bytes < 1:
        raise ValueError("All scan limits must be positive")
    root = Path(source_root).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)

    records = []
    eligible = {}
    source_paths = sorted(root.rglob("*.cs"), key=lambda p: str(p).casefold())
    for path in source_paths:
        relative = path.relative_to(root)
        display = relative.as_posix()
        size = path.lstat().st_size
        base = dict(
            relative_path=display,
            absolute_path=str(path),
            size_bytes=size,
            sha256=None,
        )

        has_symlink_parent = any(
            (root.joinpath(*relative.parts[:index])).is_symlink()
            for index in range(1, len(relative.parts))
        )
        if (
            path.is_symlink() or has_symlink_parent or not path.is_file()
            or not path.resolve().is_relative_to(root)
        ):
            records.append(SourceRecord(**base, scan_status="skipped", reason="symlink_or_nonfile"))
            continue
        if any(part.casefold() in SKIP_DIR_NAMES_FOLDED for part in relative.parts[:-1]):
            records.append(SourceRecord(**base, scan_status="skipped", reason="excluded_directory"))
            continue
        if relative.name.endswith(SKIP_FILE_ENDINGS):
            records.append(SourceRecord(**base, scan_status="skipped", reason="generated_file"))
            continue
        if size > max_file_bytes:
            records.append(SourceRecord(**base, scan_status="skipped", reason="file_too_large"))
            continue
        try:
            # Strict decoding is deliberate: silently replacing code tokens
            # can change migration semantics.
            payload = path.read_bytes()
            source = payload.decode("utf-8-sig")
        except (UnicodeError, OSError):
            records.append(SourceRecord(**base, scan_status="skipped", reason="read_or_encoding_error"))
            continue
        if len(payload) > max_file_bytes:
            records.append(SourceRecord(**base, scan_status="skipped", reason="file_too_large"))
            continue
        if not source.strip():
            records.append(SourceRecord(**base, scan_status="skipped", reason="empty_source"))
            continue
        if len(source) > max_source_chars:
            records.append(SourceRecord(**base, scan_status="skipped", reason="source_context_too_long"))
            continue
        if len(eligible) >= max_files:
            records.append(SourceRecord(**base, scan_status="skipped", reason="file_limit"))
            continue

        fingerprint = sha256(payload).hexdigest()
        eligible[display] = source
        records.append(SourceRecord(
            **{**base, "sha256": fingerprint},
            scan_status="planned",
        ))

    return records, eligible


def conservative_configuration_cleanup(generated: str, original: str):
    """Remove one clearly obsolete import if no old config types remain."""
    if not re.search(r"\bConfigurationManager\s*\.\s*AppSettings\b", original):
        return generated, False
    if "IConfiguration" not in generated:
        return generated, False
    if not re.search(r"(?m)^\s*using\s+Microsoft\.Extensions\.Configuration\s*;", generated):
        return generated, False
    obsolete = re.compile(r"(?m)^[ \t]*using[ \t]+System\.Configuration[ \t]*;[ \t]*\r?\n")
    possible = obsolete.sub("", generated, count=1)
    if possible == generated:
        return generated, False
    types = (
        "ConfigurationManager", "ConfigurationSection", "ConfigurationElement",
        "ConfigurationProperty", "ConfigurationErrorsException", "AppSettingsReader",
        "ConnectionStringSettings", "ApplicationSettingsBase", "SettingsBase",
        "SettingsProvider", "SettingsProperty", "ConfigurationSettings",
        "IConfigurationSectionHandler",
    )
    if "System.Configuration" in possible or any(
        re.search(rf"\b{re.escape(name)}\b", possible) for name in types
    ):
        return generated, False
    return possible, True


def review_contracts(source: str, draft: str):
    """Conservative warnings; NOT a C# compiler or equivalence checker."""
    warnings = []
    if not draft.strip():
        return ["Empty migration draft"]
    if "```" in draft:
        warnings.append("Markdown code fences in output")

    source_namespace = re.findall(r"\bnamespace\s+([\w.]+)", source)
    for namespace in set(source_namespace):
        if not re.search(rf"\bnamespace\s+{re.escape(namespace)}\b", draft):
            warnings.append(f"Original namespace missing: {namespace}")

    old_types = set(re.findall(r"\b(?:class|struct|record|interface)\s+(\w+)", source))
    for name in sorted(old_types):
        if not re.search(rf"\b(?:class|struct|record|interface)\s+{re.escape(name)}\b", draft):
            warnings.append(f"Original type declaration missing: {name}")
    return warnings


def write_draft(run_dir: Path, record: SourceRecord, original: str, raw_code: str):
    """Write raw, cleaned and unified diff under this unique run directory."""
    relative = Path(record.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe relative source path")
    cleaned, was_cleaned = conservative_configuration_cleanup(raw_code, original)

    raw_path = run_dir / "raw" / relative
    draft_path = run_dir / "drafts" / relative
    diff_path = run_dir / "diffs" / relative.with_suffix(".cs.patch")
    for path in (raw_path, draft_path, diff_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    raw_path.write_text(raw_code.rstrip() + "\n", encoding="utf-8")
    draft_path.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
    diff_text = "".join(unified_diff(
        original.splitlines(keepends=True),
        (cleaned.rstrip() + "\n").splitlines(keepends=True),
        fromfile=f"legacy/{record.relative_path}",
        tofile=f"draft/{record.relative_path}",
    ))
    diff_path.write_text(diff_text, encoding="utf-8")
    return {
        "raw_path": str(raw_path),
        "draft_path": str(draft_path),
        "diff_path": str(diff_path),
        "obsolete_using_removed": was_cleaned,
        "static_review_warnings": review_contracts(original, cleaned),
    }


def write_report(path: Path, entries, *, metadata):
    """Write an interim report atomically, keeping earlier output intact."""
    report = {
        "metadata": metadata,
        "entries": entries,
        "source_files_modified": False,
        "validation_status": "not_run",
        "approval_status": "human_review_required",
    }
    stage = path.with_suffix(path.suffix + ".tmp")
    stage.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage.replace(path)


def source_records_to_dicts(records):
    return [asdict(record) for record in records]
