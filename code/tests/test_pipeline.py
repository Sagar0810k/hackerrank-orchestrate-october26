"""Regression tests on the real participant dataset (needs dataset/ next to code/).

Run from the repository root:  python -m unittest discover -s code/tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as pipeline  # noqa: E402
from audit.loader import DATASET, read_csv  # noqa: E402
from evaluation.main import custom_suite, evaluate, load_answers  # noqa: E402

HAS_DATA = (DATASET / "deletion_requests.csv").exists()


@unittest.skipUnless(HAS_DATA, "dataset/ not present")
class SampleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = load_answers(DATASET / "sample_output.csv")
        cls.predicted = pipeline.run_pipeline(read_csv(DATASET / "sample_deletion_requests.csv"))
        cls.metrics = evaluate(cls.predicted, cls.expected)

    def test_every_status_correct(self):
        self.assertEqual(self.metrics["status_correct"], self.metrics["cases"])

    def test_step_quality_floor(self):
        self.assertGreaterEqual(self.metrics["step_precision"], 0.99)
        self.assertGreaterEqual(self.metrics["step_recall"], 0.95)

    def test_incomplete_remediation_and_checks_have_no_evidence(self):
        for status, steps in self.predicted.values():
            for s in steps:
                if s["phase"] == "REMEDIATION" or (status == "INCOMPLETE" and s["phase"] == "VERIFICATION"):
                    self.assertEqual(s["evidence_id"], "")
                if s["phase"] == "FINDING" or status == "COMPLETE":
                    self.assertTrue(s["evidence_id"])


@unittest.skipUnless(HAS_DATA, "dataset/ not present")
class CustomCaseTests(unittest.TestCase):
    def test_all_custom_cases_pass(self):
        requests, expected, _ = custom_suite()
        m = evaluate(pipeline.run_pipeline(requests), expected)
        self.assertEqual(m["sequence_correct"], m["cases"])


@unittest.skipUnless(HAS_DATA, "dataset/ not present")
class FullRunTests(unittest.TestCase):
    def test_full_run_is_deterministic_and_complete(self):
        requests = read_csv(DATASET / "deletion_requests.csv")
        a = pipeline.run_pipeline(requests)
        b = pipeline.run_pipeline(requests)
        self.assertEqual(a, b)
        self.assertEqual(set(a), {r["case_id"] for r in requests})


if __name__ == "__main__":
    unittest.main()
