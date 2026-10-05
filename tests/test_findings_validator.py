from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "harness" / "skills" / "pr-review" / "validate_findings.py"


def run(records) -> subprocess.CompletedProcess:
    payload = records if isinstance(records, str) else json.dumps(records)
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "-"], input=payload, capture_output=True, text=True
    )


CONFIRMED = {
    "verdict": "confirmed",
    "rule": "CR-01",
    "path": "app/handler.py",
    "line": 42,
    "failure": "a crafted name reaches the query unescaped",
    "fix": "bind the parameter",
}


class FindingsValidatorTests(unittest.TestCase):
    """The point of the validator: a finding that cannot support itself fails
    here rather than reaching the author as a confident claim."""

    def test_a_complete_confirmed_finding_passes(self) -> None:
        self.assertEqual(run([CONFIRMED]).returncode, 0)

    def test_empty_findings_is_a_valid_clean_review(self) -> None:
        result = run([])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_confirmed_without_its_trace_fails(self) -> None:
        for missing in ("line", "failure", "fix"):
            record = {k: v for k, v in CONFIRMED.items() if k != missing}
            result = run([record])
            self.assertEqual(result.returncode, 1, f"{missing} was not required")
            self.assertIn(missing, result.stderr)

    def test_unknown_rule_id_fails(self) -> None:
        # Citing a rule nobody can look up defeats the numbering.
        result = run([{**CONFIRMED, "rule": "CR-99"}])
        self.assertEqual(result.returncode, 1)
        self.assertIn("not defined in rules.md", result.stderr)

    def test_needs_validation_must_not_carry_severity(self) -> None:
        record = {"verdict": "needs_validation", "rule": "CR-14", "path": "a.py",
                  "unresolved": "row count at scale", "severity": "high"}
        result = run([record])
        self.assertEqual(result.returncode, 1)
        self.assertIn("severity", result.stderr)

    def test_needs_validation_must_name_the_open_fact(self) -> None:
        result = run([{"verdict": "needs_validation", "rule": "CR-14", "path": "a.py"}])
        self.assertEqual(result.returncode, 1)
        self.assertIn("unresolved", result.stderr)

    def test_rejected_must_say_what_disproved_it(self) -> None:
        result = run([{"verdict": "rejected", "rule": "CR-12", "path": "a.py"}])
        self.assertEqual(result.returncode, 1)
        self.assertIn("disproved_by", result.stderr)

    def test_unknown_verdict_fails(self) -> None:
        self.assertEqual(run([{**CONFIRMED, "verdict": "probably"}]).returncode, 1)

    def test_unreadable_input_exits_two_not_one(self) -> None:
        # Exit 2 keeps "could not check" distinct from "checked and failed".
        self.assertEqual(run("not json").returncode, 2)
        self.assertEqual(run({"verdict": "confirmed"}).returncode, 2)


if __name__ == "__main__":
    unittest.main()
