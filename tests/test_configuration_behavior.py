import unittest

import run_batch_configuration_behavior as module


class ConfigurationBehaviorTests(unittest.TestCase):
    def test_four_expected_scenarios(self):
        self.assertEqual(
            {item["id"] for item in module.SCENARIOS},
            {"configured", "missing", "empty", "whitespace"},
        )

    def test_compare_succeeds_for_matching_behavior(self):
        cases = [{"id": item["id"], "success": True,
                  "result": item["expected"], "error_type": None}
                 for item in module.SCENARIOS]
        output = {"status": "PASS", "cases": cases}
        self.assertEqual(module.compare_cases(output, output)["passed"], 4)

    def test_compare_fails_for_missing_fallback(self):
        cases = [{"id": item["id"], "success": True,
                  "result": item["expected"], "error_type": None}
                 for item in module.SCENARIOS]
        changed = [dict(item) for item in cases]
        changed[1]["result"] = None
        result = module.compare_cases(
            {"status": "PASS", "cases": cases},
            {"status": "PASS", "cases": changed},
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["passed"], 3)


if __name__ == "__main__":
    unittest.main()
