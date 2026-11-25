from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMANDS = sorted((REPO / "harness" / "commands").glob("*.md"))


def _allowed_tools(text: str) -> set[str]:
    match = re.search(r"(?m)^allowed-tools:\s*(.+)$", text)
    if not match:
        return set()
    return {entry.strip().split("(")[0].strip() for entry in match.group(1).split(",")}


class CommandTests(unittest.TestCase):
    """A slash command fails quietly in two ways, so both are asserted here.

    It can ask for a tool its own allowlist withholds, which surfaces as a
    permission prompt on every invocation rather than an error. Or it can be
    added to the repo and never linked into ~/.claude/commands, in which case
    the command simply does not exist on any machine but the author's.
    """

    def test_there_are_commands_to_check(self) -> None:
        self.assertGreater(len(COMMANDS), 0)

    def test_every_command_declares_a_description_and_its_tools(self) -> None:
        for path in COMMANDS:
            text = path.read_text()
            self.assertTrue(text.startswith("---\n"), f"{path.name}: no frontmatter")
            self.assertRegex(text, r"(?m)^description:\s*\S", f"{path.name}: no description")
            self.assertTrue(_allowed_tools(text), f"{path.name}: no allowed-tools")

    def test_a_command_only_asks_for_tools_it_allows(self) -> None:
        for path in COMMANDS:
            text = path.read_text()
            allowed = _allowed_tools(text)
            body = text.split("---", 2)[-1]
            for tool in ("Write", "Edit", "Read", "Bash"):
                if re.search(rf"\b{tool} tool\b", body):
                    self.assertIn(tool, allowed, f"{path.name} uses {tool} without allowing it")

    def test_setup_and_uninstall_both_handle_the_commands_directory(self) -> None:
        linked = "harness/commands/*.md"
        for script in ("setup.sh", "uninstall.sh"):
            text = (REPO / script).read_text()
            self.assertIn(linked, text, f"{script} never walks harness/commands")
            self.assertIn(".claude/commands", text, f"{script} never touches ~/.claude/commands")

    def test_say_states_what_happens_without_the_macos_binary(self) -> None:
        text = (REPO / "harness" / "commands" / "say.md").read_text()
        self.assertIn("macOS-only", text)
        self.assertRegex(text, r"If it is missing")


if __name__ == "__main__":
    unittest.main()
