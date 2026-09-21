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

    def test_shared_block_names_all_four_principles(self) -> None:
        text = (REPO / "harness" / "standing-instructions.md").read_text()
        for needle in ("Think before coding", "Simplicity first", "Surgical changes", "Goal-driven execution"):
            self.assertIn(needle, text, f"standing instructions lost: {needle}")

    def test_detailed_reference_covers_every_principle_with_a_check(self) -> None:
        text = (REPO / "harness" / "coding-discipline.md").read_text()
        for n, title in enumerate(
            ("Think before coding", "Simplicity first", "Surgical changes", "Goal-driven execution"), start=1
        ):
            self.assertIn(f"## {n}. {title}", text, f"coding-discipline.md lost principle {n}")
        # Each rule must end in something the agent can actually run or observe.
        self.assertEqual(text.count("**Check before you"), 4, "every principle needs its own check")

    def test_pointer_paths_match_what_setup_installs(self) -> None:
        # A pointer to a path setup.sh does not write is worse than no pointer.
        for installed in ("agent-workbench/coding-discipline.md", "agent-workbench/review-rules.md"):
            self.assertIn(installed, (REPO / "setup.sh").read_text(), installed)
            self.assertIn(installed, (REPO / "harness" / "standing-instructions.md").read_text(), installed)
            self.assertIn(installed, (REPO / "uninstall.sh").read_text(), installed)

    def test_self_review_is_expected_without_invoking_the_skill(self) -> None:
        # The rules existed only inside /pr-review, so nothing applied them to
        # the agent's own diff unless a human asked for a review.
        text = (REPO / "harness" / "standing-instructions.md").read_text()
        self.assertIn("review your OWN diff", text.replace("Review your OWN", "review your OWN"))
        self.assertIn("Gate tier", text)


if __name__ == "__main__":
    unittest.main()
