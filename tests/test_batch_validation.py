import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_batch_validation as validator


class BatchValidationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root / "legacy"
        self.batch = self.root / "outputs" / "batch_migration" / "run1"
        self.legacy.mkdir(parents=True)
        (self.batch / "drafts").mkdir(parents=True)

    def record(self, original, draft):
        path = self.legacy / "Demo.cs"
        path.write_text(original, encoding="utf-8")
        (self.batch / "drafts" / "Demo.cs").write_text(draft, encoding="utf-8")
        return {"relative_path": "Demo.cs", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def audit(self, entry):
        with patch.object(validator, "LEGACY_ROOT", self.legacy):
            return validator.audit_entry(entry, self.batch)

    def test_detect_invalid_configuration_pattern(self):
        old = "public class D { public string Get() { return ConfigurationManager.AppSettings[\"X\"]; } }"
        new = "public class D { public string Get() { return Configuration.AppSettings[\"X\"]; } }"
        row = self.audit(self.record(old, new))
        self.assertEqual(row["integrity"], "PASS")
        self.assertTrue(any("Invalid migration pattern" in x for x in row["warnings"]))

    def test_detect_changed_return_type(self):
        row = self.audit(self.record(
            "public class D { public T GetById(int x) { return default(T); } }",
            "public class D { public T? GetById(int x) { return default; } }",
        ))
        self.assertTrue(any("Review return type" in x for x in row["warnings"]))

    def test_detect_source_modification(self):
        row = self.record("public class D {}", "public class D {}")
        (self.legacy / "Demo.cs").write_text("changed", encoding="utf-8")
        self.assertEqual(self.audit(row)["integrity"], "FAILED")

    def test_reject_path_traversal(self):
        row = self.audit({"relative_path": "../escape.cs", "sha256": "x"})
        self.assertEqual(row["integrity"], "FAILED")

    def test_compiler_project_has_aspnet_core_framework(self):
        source = self.legacy / "Demo.cs"
        source.write_text("public class Demo {}", encoding="utf-8")
        project = validator.create_project(
            self.root / "compiler", {Path("Demo.cs"): source}, behavior=False
        )
        content = project.read_text(encoding="utf-8")
        self.assertIn('FrameworkReference Include="Microsoft.AspNetCore.App"', content)
        self.assertIn('TargetFramework>net10.0', content)


if __name__ == "__main__":
    unittest.main()
