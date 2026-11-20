"""Offline unit tests; no API key, Qdrant, CrewAI execution or GPU required."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


if importlib.util.find_spec("crewai") is None:
    crewai_stub = types.ModuleType("crewai")
    for symbol in ("Agent", "Crew", "Process", "Task"):
        setattr(crewai_stub, symbol, object)
    sys.modules["crewai"] = crewai_stub

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codemigrate.agents import documentation_agent as docs  # noqa: E402


SOURCE = (
    'public string GetSenderName() { return '
    'ConfigurationManager.AppSettings["SenderName"] ?? "CodeMigrate"; }'
)

GOOD_DOCUMENT = (
    "Summary:\nReturns the sender name from configuration.\n"
    "Observed Behavior:\n"
    "- `NotificationSettings.GetSenderName` returns CodeMigrate if null, "
    "not when the setting is empty. [SOURCE 1]\n"
    "Migration Notes:\n"
    "- `IConfiguration` can replace `ConfigurationManager.AppSettings` "
    "while preserving null behavior. [SOURCE 1]\n"
    "Open Questions:\n- None."
)


class TestReviewDocumentation(unittest.TestCase):
    def test_correct_documentation_has_no_warnings(self):
        self.assertEqual(docs.review_documentation(GOOD_DOCUMENT, SOURCE, [1]), [])

    def test_detects_unsupported_operator_claim(self):
        bad = GOOD_DOCUMENT.replace(
            "while preserving null behavior",
            "because the ?? operator is not supported in modern C#",
        )
        self.assertIn(
            "False claim: the ?? operator is unsupported",
            docs.review_documentation(bad, SOURCE, [1]),
        )

    def test_detects_uncited_factual_bullet(self):
        bad = GOOD_DOCUMENT.replace(
            "if null, not when the setting is empty. [SOURCE 1]",
            "if null, not when the setting is empty.",
        )
        warnings = docs.review_documentation(bad, SOURCE, [1])
        self.assertIn("Uncited bullet in observed behavior: 1", warnings)

    def test_single_bounded_repair(self):
        class Retriever:
            def search(self, query, top_k):
                return [{
                    "file_path": "legacy/NotificationSettings.cs",
                    "class_name": "NotificationSettings",
                    "method_name": "GetSenderName",
                    "content": SOURCE,
                }]

        class Reranker:
            def rerank(self, query, candidates, top_k):
                return candidates[:top_k]

        bad = GOOD_DOCUMENT.replace("[SOURCE 1]", "")
        with patch.object(docs, "_run_documentation_task", side_effect=[bad, GOOD_DOCUMENT]) as task:
            result = docs.generate_documentation(
                "Explain GetSenderName", llm=object(), retriever=Retriever(),
                reranker=Reranker(), memory=None, top_k=1,
            )
        self.assertEqual(task.call_count, 2)
        self.assertEqual(result["repair_attempts"], 1)
        self.assertFalse(result["review_required"])
        self.assertEqual(result["review_warnings"], [])

    def test_repair_failure_keeps_draft_for_manual_review(self):
        class Retriever:
            def search(self, query, top_k):
                return [{
                    "file_path": "legacy/NotificationSettings.cs",
                    "class_name": "NotificationSettings",
                    "method_name": "GetSenderName",
                    "content": SOURCE,
                }]

        class Reranker:
            def rerank(self, query, candidates, top_k):
                return candidates[:top_k]

        incomplete = GOOD_DOCUMENT.replace("[SOURCE 1]", "")
        with patch.object(
            docs, "_run_documentation_task",
            side_effect=[incomplete, RuntimeError("Temporary network issue")],
        ):
            result = docs.generate_documentation(
                "Explain GetSenderName", llm=object(), retriever=Retriever(),
                reranker=Reranker(), memory=None, top_k=1,
            )
        self.assertEqual(result["documentation"], incomplete)
        self.assertTrue(result["review_required"])
        self.assertIn("Automatic repair failed: RuntimeError", result["review_warnings"])


if __name__ == "__main__":
    unittest.main()
