from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "harness" / "skills" / "pr-review" / "rules.md"
SKILL = REPO / "harness" / "skills" / "pr-review" / "SKILL.md"
AGENTS = REPO / "AGENTS.md"

IDS = re.compile(r"\bCR-(\d{2})\b")


def rule_ids(text: str) -> list[int]:
    """Ids of defined rules: the first cell of a table row, not a mention."""
    return [int(m.group(1)) for m in re.finditer(r"^\|\s*CR-(\d{2})\s*\|", text, re.M)]


class ReviewRuleTests(unittest.TestCase):
    """The rule ids are cited in three files; drift makes a review cite a rule
    the reader cannot look up, which is the whole point of numbering them."""

    def setUp(self) -> None:
        self.rules_text = RULES.read_text()
        self.ids = rule_ids(self.rules_text)

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(self.ids), len(set(self.ids)), "duplicate CR id defined")

    def test_ids_are_contiguous_from_one(self) -> None:
        self.assertEqual(sorted(self.ids), list(range(1, len(self.ids) + 1)), "gap in the CR sequence")

    def test_every_rule_states_the_evidence_it_demands(self) -> None:
        # A rule without required evidence turns a finding back into taste.
        for line in self.rules_text.splitlines():
            if re.match(r"^\|\s*CR-\d{2}\s*\|", line):
                cells = [c.strip() for c in line.strip("|").split("|")]
                self.assertEqual(len(cells), 3, f"malformed rule row: {line}")
                self.assertTrue(cells[2], f"{cells[0]} names no evidence")

    def test_cited_range_matches_the_rule_file(self) -> None:
        highest = max(self.ids)
        for path in (SKILL, AGENTS):
            cited = {int(m.group(1)) for m in IDS.finditer(path.read_text())}
            self.assertIn(
                highest, cited, f"{path.name} does not cite the highest rule (CR-{highest:02d})"
            )
            self.assertFalse(
                [c for c in cited if c > highest],
                f"{path.name} cites a rule that does not exist in rules.md",
            )

    def test_every_tier_is_named_for_its_cost(self) -> None:
        for tier in ("tier: Gate", "tier: Justify", "tier: Lock"):
            self.assertIn(tier, self.rules_text)


class StandingInstructionTests(unittest.TestCase):
    """The pre-coding rules must reach every harness, so they live in the
    shared block rather than in one vendor's config."""

    def test_shared_block_covers_assumptions_scope_and_verification(self) -> None:
        text = (REPO / "harness" / "standing-instructions.md").read_text()
        for needle in ("surface what you are assuming", "minimum that solves", "verify:"):
            self.assertIn(needle, text, f"standing instructions lost: {needle}")


if __name__ == "__main__":
    unittest.main()
