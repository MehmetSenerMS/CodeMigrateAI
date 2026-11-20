import unittest
from unittest.mock import patch

import preflight_github as preflight


class GitHubPreflightTests(unittest.TestCase):
    def mock_git(self, staged_files):
        paths = b"\0".join(name.encode("utf-8") for name in staged_files) + b"\0"

        def fake_git(*args):
            if args[0] == "ls-files":
                return paths
            if args[0] == "show":
                return staged_files[args[1][1:]]
            raise AssertionError(args)

        return fake_git

    def test_safe_readme_passes(self):
        with patch.object(preflight, "git_bytes", side_effect=self.mock_git({
            "README.md": b"A C# migration assistant with manual review.\n"
        })):
            self.assertEqual(preflight.scan_staged(), [])

    def test_env_file_is_flagged(self):
        with patch.object(preflight, "git_bytes", side_effect=self.mock_git({
            ".env": b"CODEMIGRATE_API_URL=https://example.test"
        })):
            self.assertTrue(any("environment" in reason for _, reason in preflight.scan_staged()))

    def test_secret_values_are_not_in_diagnostics(self):
        token = b"sk-proj-" + b"z" * 24
        with patch.object(preflight, "git_bytes", side_effect=self.mock_git({
            "settings.py": b"token = '" + token + b"'"
        })):
            findings = preflight.scan_staged()
            self.assertTrue(findings)
            self.assertNotIn(token.decode(), str(findings))

    def test_notebook_outputs_are_flagged(self):
        notebook = b'{"cells": [{"cell_type": "code", "outputs": [{"text": "ok"}]}]}'
        with patch.object(preflight, "git_bytes", side_effect=self.mock_git({
            "training.ipynb": notebook
        })):
            self.assertTrue(any("Notebook contains outputs" in reason
                                for _, reason in preflight.scan_staged()))


if __name__ == "__main__":
    unittest.main()
