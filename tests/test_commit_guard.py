from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HOOKS = Path(__file__).resolve().parents[1] / "harness" / "git-hooks"


class CommitGuardTests(unittest.TestCase):
    """The guard must hold for any assistant, and must not touch human prose."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.com")
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        for name in ("commit-msg", "pre-commit"):
            (hooks / name).symlink_to(HOOKS / name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _git(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(self.repo), capture_output=True, text=True,
            env={**os.environ, **(env or {})},
        )

    def _commit(self, message: str, filename: str, env: dict[str, str] | None = None):
        (self.repo / filename).write_text(filename)
        self._git("add", ".")
        msg = self.repo / ".msg"
        msg.write_text(message)
        return self._git("commit", "-F", str(msg), env=env)

    def _last_message(self) -> str:
        return self._git("log", "-1", "--format=%B").stdout

    def test_strips_co_authored_by_for_every_vendor(self) -> None:
        # The regression that shipped broken once: the vendor alternation used
        # BRE `\|` inside `grep -E`, where it means a literal pipe, so every
        # Co-Authored-By trailer survived while only the emoji line was cut.
        for i, trailer in enumerate(
            (
                "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>",
                "Co-authored-by: GitHub Copilot <copilot@github.com>",
                "Co-Authored-By: Cursor <cursor@cursor.sh>",
                "Co-authored-by: Codex <codex@openai.com>",
                "Co-Authored-By: Gemini <gemini@google.com>",
                "Co-authored-by: devin-ai-integration[bot] <devin@cognition.ai>",
                "Assisted-by: some assistant <x@example.com>",
            )
        ):
            result = self._commit(f"real subject\n\n{trailer}\n", f"f{i}.txt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("uthored", self._last_message(), f"survived: {trailer}")
            self.assertIn("real subject", self._last_message())

    def test_strips_generated_with_and_robot_lines(self) -> None:
        self._commit(
            "add thing\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n", "g.txt"
        )
        body = self._last_message()
        self.assertNotIn("Generated with", body)
        self.assertNotIn("🤖", body)
        self.assertIn("add thing", body)

    def test_keeps_human_co_author_and_prose_mentioning_tools(self) -> None:
        # False positives would be worse than the problem: a human co-author is
        # legitimate, and prose may discuss these tools by name.
        message = (
            "fix codex parsing and the claude transcript reader\n\n"
            "The assistant docs said generated with care; keep that wording.\n"
            "Co-Authored-By: Jane Human <jane@example.com>\n"
        )
        self._commit(message, "h.txt")
        body = self._last_message()
        self.assertIn("Co-Authored-By: Jane Human", body)
        self.assertIn("claude transcript reader", body)
        self.assertIn("generated with care", body)

    def test_refuses_a_commit_made_under_an_assistant_identity(self) -> None:
        result = self._commit(
            "sneaky\n", "i.txt",
            env={"GIT_AUTHOR_NAME": "Claude", "GIT_AUTHOR_EMAIL": "noreply@anthropic.com"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assistant identity", result.stderr)
        self.assertEqual(self._git("log", "--oneline").stdout.strip(), "")

    def test_ordinary_commit_is_untouched(self) -> None:
        result = self._commit("add the c file\n", "c.txt")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._last_message().strip(), "add the c file")
        self.assertIn("Test User", self._git("log", "-1", "--format=%an <%ae>").stdout)

    def test_hooks_are_executable_and_posix_sh(self) -> None:
        for name in ("commit-msg", "pre-commit"):
            hook = HOOKS / name
            self.assertTrue(os.access(hook, os.X_OK), f"{name} not executable")
            self.assertEqual(
                subprocess.run(["sh", "-n", str(hook)], capture_output=True).returncode, 0
            )


if __name__ == "__main__":
    unittest.main()
