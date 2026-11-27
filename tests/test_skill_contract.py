from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = sorted((REPO / "harness" / "skills").glob("*/SKILL.md"))

CONVENTION = REPO / "harness" / "skills" / "fan-out-and-verify.md"
POINTER = "~/.config/agent-workbench/fan-out-and-verify.md"
EVIDENCE_SKILLS = ("standup", "brain-harvest", "postmortem", "why", "meeting-prep")

# A skill that shells out to one of these depends on something setup.sh cannot
# install for the user.
EXTERNAL = re.compile(r"^\s*(?:`|\$\()?(gh|npx|node)\s", re.M)
DEGRADES = "absent or unauthenticated"


def in_force(path: Path) -> str:
    """The skill as the model reads it: its own text plus the convention it points at."""
    text = path.read_text()
    return text + CONVENTION.read_text() if POINTER in text else text


class SkillContractTests(unittest.TestCase):
    """What a new user on a fresh machine silently misses.

    Every skill here reaches for tools the installer cannot guarantee: `gh`, a
    Slack or calendar connector, an authenticated account. The failure that
    matters is not the error, it is the quiet one: a thin answer that reads as
    a complete one because nothing said a source was missing.
    """

    def test_there_are_skills_to_check(self) -> None:
        self.assertGreater(len(SKILLS), 0)

    def test_every_skill_has_frontmatter_with_name_and_description(self) -> None:
        for path in SKILLS:
            head = path.read_text()[:2000]
            self.assertTrue(head.startswith("---\n"), f"{path.parent.name}: no frontmatter")
            for field in ("name", "description"):
                self.assertRegex(
                    head, rf"(?m)^{field}:\s*\S", f"{path.parent.name}: no {field}"
                )

    def test_a_skill_using_external_tools_says_what_happens_without_them(self) -> None:
        for path in SKILLS:
            text = in_force(path)
            if EXTERNAL.search(text):
                self.assertIn(
                    DEGRADES,
                    text,
                    f"{path.parent.name} calls an external tool but never says what to do "
                    "when it is missing, so the user gets a thin answer with no warning",
                )

    def test_every_fan_out_skill_resolves_exact_keys_first(self) -> None:
        # A loose name match handed to several agents gives every one the wrong set.
        step = "**Resolve exact keys first.** Before searching in parallel or briefing a subagent"
        for name in ("standup", "postmortem", "why", "meeting-prep", "brain-harvest", "pr-review"):
            text = in_force(REPO / "harness" / "skills" / name / "SKILL.md")
            self.assertIn(step, text, f"{name} fans out without resolving exact keys first")

    def test_evidence_skills_point_at_the_convention_instead_of_restating_it(self) -> None:
        # Five inline copies drifted into five phrasings; one file keeps them one convention.
        convention = CONVENTION.read_text()
        for name in EVIDENCE_SKILLS:
            text = (REPO / "harness" / "skills" / name / "SKILL.md").read_text()
            self.assertIn(f"**Read `{POINTER}` before gathering.**", text, name)
            self.assertNotIn("**Resolve exact keys first.**", text, f"{name} restates the convention")
            self.assertNotIn("U0…", text, f"{name} restates the Slack id rule")
        for rule in ("Resolve exact keys first", "in parallel", DEGRADES, "U0…",
                     "Verify before presenting", "Cite a surface", "Do not store the output"):
            self.assertIn(rule, convention, f"the convention lost: {rule}")

    def test_convention_pointer_matches_what_setup_installs(self) -> None:
        # A pointer to a path setup.sh does not write is worse than no pointer.
        installed = POINTER.removeprefix("~/.config/")
        for script in ("setup.sh", "uninstall.sh"):
            self.assertIn(installed, (REPO / script).read_text(), script)
        self.assertIn('"$WORKBENCH/harness/skills/fan-out-and-verify.md"', (REPO / "setup.sh").read_text())

    def test_voice_stores_through_the_rule_engine_rather_than_its_own_profile(self) -> None:
        """The decision that kept /voice from duplicating the rule engine.

        Voice is one context (audience:<person>), so a voice pattern is an
        ordinary contextual rule. A separate profile note would reimplement
        scoped storage, correction-learning and retrieval a second time, and the
        two copies would drift.
        """
        text = (REPO / "harness" / "skills" / "voice" / "SKILL.md").read_text()
        for tool in ("brain_rule_remember", "brain_rules_in_force", "brain_context"):
            self.assertIn(tool, text, f"voice does not reach the rule engine via {tool}")
        self.assertNotIn(
            "brain_voice_profile",
            text,
            "voice reintroduced a store of its own; audience-scoped rules are the profile",
        )

    def test_voice_refuses_to_store_raw_messages_or_slack_ids(self) -> None:
        text = (REPO / "harness" / "skills" / "voice" / "SKILL.md").read_text()
        self.assertRegex(text, r"[Nn]o raw message bodies")
        self.assertRegex(text, r"U0", "voice must say that Slack ids are resolved to names, not stored")

    def test_setup_reports_the_prerequisites_it_cannot_install(self) -> None:
        setup = (REPO / "setup.sh").read_text()
        for tool in ("git", "gh", "node"):
            self.assertIn(f"report_tool {tool}", setup, f"setup.sh never mentions {tool}")
        self.assertIn("gh auth status", setup, "an unauthenticated gh looks installed but returns nothing")


if __name__ == "__main__":
    unittest.main()
