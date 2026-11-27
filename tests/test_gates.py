from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "harness" / "gates"))

import check_diff  # noqa: E402

GUARD = REPO / "harness" / "hooks" / "pretooluse-guard.sh"

# Built by concatenation so this file never carries a literal the checker flags.
AWS_KEY = "AKIA" + "Q7" * 8
GITHUB_TOKEN = "ghp_" + "a1B2" * 9
SLACK_TOKEN = "xoxb-" + "123456789012-" + "abcDEF123456"
KEY_HEADER = "-----BEGIN " + "RSA PRIVATE KEY-----"


def added(path: str, *lines: str) -> str:
    body = "".join(f"+{line}\n" for line in lines)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


def rules(diff: str) -> list[str]:
    return [f.rule for f in check_diff.check(diff)]


class SecretCheckTests(unittest.TestCase):
    def test_catches_each_token_shape(self) -> None:
        for value in (AWS_KEY, GITHUB_TOKEN, SLACK_TOKEN, KEY_HEADER):
            self.assertEqual(rules(added("config.yml", f"key: {value}")), ["CR-02"], value[:6])

    def test_near_misses_do_not_fire(self) -> None:
        for line in (
            "aws_key: AKIAIOSFODNN7EXAMPLE",
            "token: ghp_short",
            "slack: xoxb-your-token-here",
            'password = os.environ["DB_PASSWORD"]',
            'password = "hunter2hunter2"',
            "BEGIN PUBLIC KEY",
        ):
            self.assertEqual(rules(added("config.py", line)), [], line)

    def test_finding_never_prints_the_value(self) -> None:
        finding = check_diff.check(added("a.env", f"T={GITHUB_TOKEN}"))[0]
        self.assertNotIn(GITHUB_TOKEN, " ".join(map(str, finding)))
        self.assertEqual((finding.path, finding.line), ("a.env", 1))


class SwallowedFailureTests(unittest.TestCase):
    def test_python_broad_except_pass(self) -> None:
        for lines in (
            ("try:", "    f()", "except:", "    pass"),
            ("try:", "    f()", "except Exception as exc:", "    pass"),
            ("try: f()", "except BaseException: pass"),
        ):
            self.assertEqual(rules(added("m.py", *lines)), ["CR-09"], lines)

    def test_python_near_misses(self) -> None:
        for lines in (
            ("try:", "    f()", "except KeyError:", "    pass"),
            ("try:", "    f()", "except Exception:", "    log.warning('x')"),
            ("try:", "    f()", "except Exception:", "    raise"),
        ):
            self.assertEqual(rules(added("m.py", *lines)), [], lines)

    def test_python_check_skips_non_python_files(self) -> None:
        self.assertEqual(rules(added("rules.md", "except: pass")), [])

    def test_js_empty_catch(self) -> None:
        for lines in (
            ("try { f() } catch (e) {}",),
            ("try {", "  f()", "} catch (err) {", "}"),
            ("load().catch(() => {})",),
        ):
            self.assertEqual(rules(added("a.ts", *lines)), ["CR-09"], lines)

    def test_js_near_misses(self) -> None:
        for lines in (
            ("try { f() } catch (e) { report(e) }",),
            ("} catch (err) {", "  // cache miss is expected", "}"),
            ("load().catch((e) => log(e))",),
        ):
            self.assertEqual(rules(added("a.js", *lines)), [], lines)

    def test_go_ignored_error(self) -> None:
        self.assertEqual(rules(added("x.go", "\t_ = err")), ["CR-09"])
        self.assertEqual(rules(added("x.go", "\tif err != nil {}")), ["CR-09"])
        self.assertEqual(rules(added("x.go", "\tif err != nil { return err }", "\t_ = cancel")), [])


class DiffScopeTests(unittest.TestCase):
    def test_context_lines_never_fire_on_their_own(self) -> None:
        diff = (
            "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -10,2 +10,3 @@\n"
            " except Exception: pass\n"
            f" T = '{AWS_KEY}'\n"
            "+x = 1\n"
        )
        self.assertEqual(rules(diff), [])

    def test_line_numbers_follow_the_hunk_header(self) -> None:
        diff = "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -40,0 +41,2 @@\n+except:\n+    pass\n"
        self.assertEqual([f.line for f in check_diff.check(diff)], [41])

    def test_inline_marker_overrides_only_the_named_rule(self) -> None:
        self.assertEqual(rules(added("m.py", "except Exception: pass  # gate-allow: CR-09")), [])
        self.assertEqual(rules(added("m.py", "except Exception:", "    pass  # gate-allow: CR-09")), [])
        self.assertEqual(rules(added("m.py", "except Exception: pass  # gate-allow: CR-02")), ["CR-09"])
        self.assertEqual(rules(added("a.env", f"T={AWS_KEY}  # gate-allow: CR-02")), [])


class GitIntegrationTests(unittest.TestCase):
    """The checker reads only what is staged, and the guard denies a commit that adds a violation."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.com")
        (self.repo / "old.py").write_text("try:\n    f()\nexcept:\n    pass\n")
        self._git("add", "old.py")
        self._git("commit", "-q", "-m", "seed")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def _check(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO / "harness" / "gates" / "check_diff.py"), "-C", str(self.repo), *args],
            capture_output=True, text=True,
        )

    def _guard(self, command: str, patterns: str | None = None) -> str:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)})
        env = dict(os.environ, AGENT_WORKBENCH_GUARD_PATTERNS=patterns or str(self.repo / "no-patterns"))
        out = subprocess.run(["bash", str(GUARD)], input=payload, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0)
        return out.stdout

    def test_existing_code_does_not_block(self) -> None:
        (self.repo / "new.py").write_text("x = 1\n")
        self._git("add", "new.py")
        self.assertEqual(self._check().returncode, 0)
        self.assertEqual(self._guard("git commit -m 'add new'").strip(), "")

    def test_staged_violation_fails_and_guard_denies(self) -> None:
        (self.repo / "new.py").write_text("try:\n    g()\nexcept Exception:\n    pass\n")
        self._git("add", "new.py")
        result = self._check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("new.py:3: CR-09", result.stdout)
        decision = json.loads(self._guard(f"cd {self.repo} && git commit -m 'add new'"))
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("new.py:3: CR-09", reason)
        self.assertIn("gate-allow", reason)

    def test_unstaged_change_is_ignored_unless_commit_all(self) -> None:
        (self.repo / "old.py").write_text(f"T = '{AWS_KEY}'\n")
        self.assertEqual(self._guard("git commit -m x").strip(), "")
        self.assertIn('"deny"', self._guard("git commit -am x"))

    def test_guard_ignores_commands_that_are_not_commits(self) -> None:
        (self.repo / "new.py").write_text("except:\n    pass\n")
        self._git("add", "new.py")
        self.assertEqual(self._guard("git log --grep commit").strip(), "")
        self.assertEqual(self._guard("git diff --cached").strip(), "")

    def test_range_mode_reads_a_commit_range(self) -> None:
        (self.repo / "new.go").write_text("package x\nfunc f() {\n\t_ = err\n}\n")
        self._git("add", "new.go")
        self._git("commit", "-q", "-m", "go")
        result = self._check("HEAD~1..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("new.go:3: CR-09", result.stdout)

    def test_unreadable_range_exits_two(self) -> None:
        self.assertEqual(self._check("no-such-ref..HEAD").returncode, 2)


if __name__ == "__main__":
    unittest.main()
