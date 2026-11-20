"""Safety-focused batch migration tests; no external API or .NET execution."""

import json
import tempfile
import unittest
from pathlib import Path

from codemigrate.pipeline.batch_migrator import (
    conservative_configuration_cleanup,
    make_run_directory,
    review_contracts,
    scan_csharp_sources,
    write_draft,
    write_report,
)


class BatchMigratorTests(unittest.TestCase):
    def test_scanner_skips_generated_and_large_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "legacy"
            root.mkdir()
            (root / "Customer.cs").write_text("public class Customer {}", encoding="utf-8")
            (root / "Customer.g.cs").write_text("public class Generated {}", encoding="utf-8")
            (root / "Large.cs").write_text("x" * 90, encoding="utf-8")
            (root / "obj").mkdir()
            (root / "obj" / "Other.cs").write_text("public class Hidden {}", encoding="utf-8")

            records, content = scan_csharp_sources(root, max_source_chars=80)
            states = {r.relative_path: (r.scan_status, r.reason) for r in records}
            self.assertEqual(states["Customer.cs"][0], "planned")
            self.assertEqual(states["Customer.g.cs"][1], "generated_file")
            self.assertEqual(states["Large.cs"][1], "source_context_too_long")
            self.assertEqual(states["obj/Other.cs"][1], "excluded_directory")
            self.assertEqual(set(content), {"Customer.cs"})

    def test_draft_is_always_written_outside_original_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "legacy"
            (root / "Models").mkdir(parents=True)
            original_file = root / "Models" / "NotificationSettings.cs"
            original_code = (
                "using System.Configuration;\n"
                "namespace Demo;\npublic class NotificationSettings {\n"
                " public string GetName() => ConfigurationManager.AppSettings[\"Name\"];\n}"
            )
            modern_code = (
                "using System.Configuration;\n"
                "using Microsoft.Extensions.Configuration;\n"
                "namespace Demo;\npublic class NotificationSettings {\n"
                " private readonly IConfiguration _configuration;\n"
                " public string GetName() => _configuration[\"Name\"];\n}"
            )
            original_file.write_text(original_code, encoding="utf-8")
            records, content = scan_csharp_sources(root)
            output_root = Path(temp) / "outputs"
            run_dir = make_run_directory(output_root)
            paths = write_draft(run_dir, records[0], content[records[0].relative_path], modern_code)
            self.assertTrue(Path(paths["draft_path"]).is_file())
            self.assertTrue(Path(paths["raw_path"]).is_file())
            self.assertTrue(Path(paths["diff_path"]).is_file())
            self.assertTrue(paths["obsolete_using_removed"])
            self.assertNotIn("using System.Configuration;", Path(paths["draft_path"]).read_text())
            self.assertIn("using System.Configuration;", Path(paths["raw_path"]).read_text())
            self.assertEqual(original_file.read_text(encoding="utf-8"), original_code)

            report_file = run_dir / "migration_report.json"
            write_report(report_file, [{"status": "draft_generated"}], metadata={"test": True})
            report = json.loads(report_file.read_text())
            self.assertFalse(report["source_files_modified"])
            self.assertEqual(report["validation_status"], "not_run")

    def test_contract_warning_for_missing_public_type(self):
        self.assertIn(
            "Original type declaration missing: CustomerService",
            review_contracts(
                "namespace Demo; public class CustomerService {}",
                "namespace Demo; public class Renamed {}",
            ),
        )

    def test_context_limit_prevents_silent_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "VeryLong.cs").write_text("public class Foo { } " * 100, encoding="utf-8")
            records, content = scan_csharp_sources(root, max_source_chars=30)
            self.assertEqual(records[0].reason, "source_context_too_long")
            self.assertFalse(content)


if __name__ == "__main__":
    unittest.main()
