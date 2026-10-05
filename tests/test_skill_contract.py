from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = sorted((REPO / "harness" / "skills").glob("*/SKILL.md"))

# A skill that shells out to one of these depends on something setup.sh cannot
# install for the user.
EXTERNAL = re.compile(r"^\s*(?:`|\$\()?(gh|npx|node)\s", re.M)
DEGRADES = re.compile(
    r"skip it and \*\*say so|missing source|unavailable|skipped and called out"
    r"|say so in|absent or unauthenticated|not installed",
    re.I,
)


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
            text = path.read_text()
            if EXTERNAL.search(text):
                self.assertRegex(
                    text,
                    DEGRADES,
                    f"{path.parent.name} calls an external tool but never says what to do "
                    "when it is missing, so the user gets a thin answer with no warning",
                )

    def test_setup_reports_the_prerequisites_it_cannot_install(self) -> None:
        setup = (REPO / "setup.sh").read_text()
        for tool in ("git", "gh", "node"):
            self.assertIn(f"report_tool {tool}", setup, f"setup.sh never mentions {tool}")
        self.assertIn("gh auth status", setup, "an unauthenticated gh looks installed but returns nothing")


if __name__ == "__main__":
    unittest.main()
