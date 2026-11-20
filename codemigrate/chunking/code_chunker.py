"""C# source-code chunking for the CodeMigrate AI ingestion layer.

This lightweight parser supports common class and method declarations. It is
not a complete C# syntax parser (Roslyn-equivalent).
"""

import re
from pathlib import Path

from codemigrate.chunking.models import SourceChunk


class CodeChunker:
    """Read a C# file and create one SourceChunk per supported method."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

        if self.file_path.suffix.lower() != ".cs":
            raise ValueError("Only C# source files are supported")

        if not self.file_path.is_file():
            raise FileNotFoundError(
                f"Source file not found: {self.file_path}"
            )

    def read_source(self) -> str:
        """Read the source file, accepting UTF-8 files with or without a BOM."""
        return self.file_path.read_text(encoding="utf-8-sig")

    @staticmethod
    def _mask_non_code(source_code: str) -> str:
        """Mask comments and string/char literals while preserving offsets.

        Every masked character becomes a space; newline characters are kept.
        This keeps positions and line numbers aligned with the original file.
        """
        masked = list(source_code)
        length = len(source_code)
        index = 0

        def hide(start: int, end: int) -> None:
            for pos in range(start, end):
                if source_code[pos] not in "\r\n":
                    masked[pos] = " "

        while index < length:
            start = index

            if source_code.startswith("//", index):
                newline = source_code.find("\n", index + 2)
                index = length if newline == -1 else newline
                hide(start, index)
                continue

            if source_code.startswith("/*", index):
                end = source_code.find("*/", index + 2)
                index = length if end == -1 else end + 2
                hide(start, index)
                continue

            # C# raw strings: """...""", $"""...""", $$"""...""".
            quote_start = index
            while quote_start < length and source_code[quote_start] == "$":
                quote_start += 1
            if source_code.startswith('"""', quote_start):
                quote_end = quote_start
                while quote_end < length and source_code[quote_end] == '"':
                    quote_end += 1
                marker = '"' * (quote_end - quote_start)
                end = source_code.find(marker, quote_end)
                index = length if end == -1 else end + len(marker)
                hide(start, index)
                continue

            verbatim = False
            if source_code.startswith(('$@"', '@$"'), index):
                verbatim = True
                index += 3
            elif source_code.startswith('@"', index):
                verbatim = True
                index += 2
            elif source_code.startswith('$"', index):
                index += 2
            elif source_code[index] == '"':
                index += 1
            elif source_code[index] == "'":
                index += 1
                while index < length:
                    if source_code[index] == "\\":
                        index += 2
                    elif source_code[index] == "'":
                        index += 1
                        break
                    else:
                        index += 1
                hide(start, min(index, length))
                continue
            else:
                index += 1
                continue

            # Normal and verbatim strings (including their common $ prefixes).
            while index < length:
                if verbatim and source_code.startswith('""', index):
                    index += 2
                elif source_code[index] == '"':
                    index += 1
                    break
                elif not verbatim and source_code[index] == "\\":
                    index += 2
                else:
                    index += 1
            hide(start, min(index, length))

        return "".join(masked)

    def find_matching_brace(self, source_code: str, opening_index: int) -> int:
        """Return index of the closing brace for a code-level opening brace."""
        masked = self._mask_non_code(source_code)

        if (
            opening_index < 0
            or opening_index >= len(masked)
            or masked[opening_index] != "{"
        ):
            raise ValueError("Invalid opening brace index")

        depth = 0
        for index in range(opening_index, len(masked)):
            if masked[index] == "{":
                depth += 1
            elif masked[index] == "}":
                depth -= 1
                if depth == 0:
                    return index

        raise ValueError("No matching closing brace found")

    def find_class_ranges(self, source_code: str) -> list[tuple[str, int, int]]:
        """Return (simple_class_name, opening_index, closing_index) tuples."""
        masked = self._mask_non_code(source_code)
        pattern = re.compile(
            r"\bclass\s+(?P<class_name>[A-Za-z_]\w*)"
            r"(?:\s*<[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*>)?"
            r"(?:\s*:\s*[^{};]+?)?"
            r"(?:\s+where\s+[^{};]+)?"
            r"\s*\{"
        )

        class_ranges = []
        for match in pattern.finditer(masked):
            opening_index = match.end() - 1
            closing_index = self.find_matching_brace(source_code, opening_index)
            class_ranges.append(
                (match.group("class_name"), opening_index, closing_index)
            )
        return class_ranges

    def extract_methods(self) -> list[SourceChunk]:
        """Extract common C# methods as SourceChunk objects.

        Recognizes typical visibility/static/async modifiers, generic methods,
        and nested classes. Complex C# constructs may need a full parser.
        """
        source_code = self.read_source()
        masked = self._mask_non_code(source_code)
        class_ranges = self.find_class_ranges(source_code)

        pattern = re.compile(
            r"^[ \t]*(?:(?:public|private|protected|internal|static|async|"
            r"virtual|override|sealed|new|partial|extern|unsafe)\s+)+"
            r"(?P<return_type>[A-Za-z_][\w.<>,?\[\] \t]*)\s+"
            r"(?P<method_name>[A-Za-z_]\w*)"
            r"(?:<[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*>)?"
            r"\s*\([^()]*\)"
            r"(?:\s+where\s+[A-Za-z_]\w*\s*:\s*[^{};]+)?"
            r"\s*\{",
            re.MULTILINE,
        )

        chunks: list[SourceChunk] = []
        for match in pattern.finditer(masked):
            opening_index = match.end() - 1
            closing_index = self.find_matching_brace(source_code, opening_index)

            # Choose the innermost enclosing class for nested declarations.
            enclosing = [
                entry for entry in class_ranges
                if entry[1] < match.start() < entry[2]
            ]
            class_name = (
                min(enclosing, key=lambda entry: entry[2] - entry[1])[0]
                if enclosing else None
            )

            method_name = match.group("method_name")
            start_line = source_code.count("\n", 0, match.start()) + 1
            end_line = source_code.count("\n", 0, closing_index) + 1

            chunks.append(
                SourceChunk(
                    chunk_id=f"{self.file_path.stem}:{method_name}:{start_line}",
                    source_type="code",
                    file_path=str(self.file_path),
                    content=source_code[match.start():closing_index + 1],
                    start_line=start_line,
                    end_line=end_line,
                    class_name=class_name,
                    method_name=method_name,
                )
            )

        return chunks
