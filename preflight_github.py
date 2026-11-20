"""Check Git *staged* files before public publication. No secret values printed.

This is intentionally a conservative heuristic scanner; manual review remains
necessary. Execute after `git add` and before `git commit`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import PurePosixPath


BLOCKED_ROOTS = {
    "data", "models", "outputs", "chroma", "chromadb", "vector_store",
    "qdrant_storage", ".venv", "venv", "env", "__pycache__",
}
BLOCKED_EXTENSIONS = {
    ".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin",
    ".sqlite", ".sqlite3", ".db", ".pfx", ".pem", ".key",
    ".parquet", ".arrow",
}
SECRET_PATTERNS = [
    ("OpenAI-style token", re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}")),
    ("Hugging Face token", re.compile(rb"\bhf_[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Private key material", re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("Credentials embedded in URL", re.compile(rb"https?://[^\s:/@]+:[^\s@/]+@")),
]
MAX_STAGED_FILE_BYTES = 8 * 1024 * 1024


def git_bytes(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("Git command failed; run from a Git repository")
    return result.stdout


def scan_staged() -> list[tuple[str, str]]:
    files = [entry.decode("utf-8", errors="replace")
             for entry in git_bytes("ls-files", "--cached", "-z").split(b"\x00") if entry]
    if not files:
        return [("repository", "No staged files: run git add first")]

    issues = []
    for filename in files:
        normalized = filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        name = path.name.lower()
        segments = {segment.lower() for segment in path.parts}
        if segments & BLOCKED_ROOTS:
            issues.append((filename, "Excluded runtime/data/model directory"))
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            issues.append((filename, "Binary/model/database file must not be published"))
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            issues.append((filename, "Private environment configuration is staged"))

        # Inspect the staged blob (not the possibly different working-tree file).
        blob = git_bytes("show", f":{filename}")
        if len(blob) > MAX_STAGED_FILE_BYTES:
            issues.append((filename, "Large staged file; inspect or use external artifact storage"))
            continue

        for reason, pattern in SECRET_PATTERNS:
            if pattern.search(blob):
                issues.append((filename, f"Possible secret: {reason}"))

        if path.suffix.lower() == ".ipynb":
            try:
                notebook = json.loads(blob.decode("utf-8"))
                output_cells = sum(bool(cell.get("outputs"))
                                   for cell in notebook.get("cells", [])
                                   if cell.get("cell_type") == "code")
                if output_cells:
                    issues.append((filename, f"Notebook contains outputs in {output_cells} code cells"))
            except (ValueError, UnicodeError):
                issues.append((filename, "Notebook JSON could not be checked"))
    return issues


def main() -> int:
    print("CODEMIGRATE AI - GITHUB PREFLIGHT")
    try:
        issues = scan_staged()
    except (OSError, RuntimeError) as error:
        print("FAIL:", error)
        return 1

    if issues:
        for path, reason in issues:
            print(f"REVIEW: {path} | {reason}")
        print(f"FAIL: {len(issues)} issue(s) to inspect before committing.")
        return 1
    print("PASS: no issues detected by this heuristic staged-file check.")
    print("Manual review and license checks are still required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
