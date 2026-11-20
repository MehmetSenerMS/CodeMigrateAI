"""CodeMigrate AI QLoRA migration worker.

The fine-tuned model is accessed through the Colab /migrate endpoint.
CrewAI's base-model chat agent is not asked to call this API as a tool,
because the current CodeLlama adapter does not support tool calling.
"""

from dataclasses import dataclass
import re

import requests


@dataclass(frozen=True)
class MigrationResult:
    generated_code: str
    generation_time: float | None
    generated_tokens: int | None
    warnings: tuple[str, ...]


class CodeMigrationAgent:
    def __init__(self, base_url: str, api_key: str, timeout: int = 120):
        if not base_url or not base_url.startswith("https://"):
            raise ValueError("An HTTPS API base URL is required")
        if not api_key:
            raise ValueError("An API key is required")
        if timeout < 1:
            raise ValueError("timeout must be positive")

        self.endpoint = base_url.rstrip("/") + "/migrate"
        self._api_key = api_key
        self.timeout = timeout

    def migrate(self, instruction: str, legacy_code: str) -> MigrationResult:
        if not instruction or not instruction.strip():
            raise ValueError("The migration instruction cannot be empty")
        if not legacy_code or not legacy_code.strip():
            raise ValueError("Legacy C# code cannot be empty")

        # These are the FastAPI request limits from the Colab service.
        if len(instruction) > 2000 or len(legacy_code) > 15000:
            raise ValueError("Request exceeds the /migrate input size limits")

        response = requests.post(
            self.endpoint,
            headers={"X-API-Key": self._api_key},
            json={
                "instruction": instruction.strip(),
                "legacy_code": legacy_code.strip(),
            },
            timeout=self.timeout,
            allow_redirects=False,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"CodeMigrate /migrate returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        payload = response.json()
        code = payload.get("generated_code")
        if not isinstance(code, str) or not code.strip():
            raise RuntimeError("QLoRA returned no generated C# code")

        warnings = self._check_output(legacy_code, code)

        return MigrationResult(
            generated_code=code.strip(),
            generation_time=payload.get("generation_time"),
            generated_tokens=payload.get("generated_tokens"),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _check_output(legacy_code: str, generated_code: str) -> list[str]:
        """Cheap diagnostics, not a C# compiler or behavioral verifier."""
        warnings = []

        if re.search(r"```", generated_code):
            warnings.append("Output contains a Markdown code fence")

        for legacy_api in (
            r"\bConfigurationManager\b",
            r"\bSystem\.Web\.Mvc\b",
            r"\bSystem\.Data\.Entity\b",
            r"\bHttpContext\.Current\b",
        ):
            if re.search(legacy_api, generated_code):
                warnings.append(f"Legacy API remains: {legacy_api}")

        if "ConfigurationManager" in legacy_code and re.search(
            r"\busing\s+System\.Configuration\s*;", generated_code
        ):
            warnings.append("Obsolete System.Configuration using remains")

        # Only warn: a migration instruction may explicitly allow renaming.
        old_classes = set(re.findall(
            r"\b(?:class|struct|record)\s+(\w+)", legacy_code
        ))
        for class_name in sorted(old_classes):
            if not re.search(rf"\b{re.escape(class_name)}\b", generated_code):
                warnings.append(f"Original type name is missing: {class_name}")

        old_public_methods = set(re.findall(
            r"\bpublic\s+(?:(?:static|virtual|override|async)\s+)*"
            r"[\w<>?,\[\]]+\s+(\w+)\s*\(",
            legacy_code,
        ))
        for method_name in sorted(old_public_methods):
            if not re.search(rf"\b{re.escape(method_name)}\s*\(", generated_code):
                warnings.append(f"Original public method is missing: {method_name}")

        known_legacy_indicators = (
            "ConfigurationManager",
            "System.Web",
            "System.Data.Entity",
            "HttpContext.Current",
        )
        if not any(x in legacy_code for x in known_legacy_indicators):
            if legacy_code.strip() != generated_code.strip():
                warnings.append(
                    "No recognized legacy API in input; verify that "
                    "every generated change is necessary"
                )

        return warnings
