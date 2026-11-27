from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_workbench import cli, prompt_recall
from agent_workbench.brain import remember
from agent_workbench.config import WorkbenchConfig

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "harness" / "hooks" / "subagent-recall.sh"
FILLER = [
    "Lori asked me to look at the code and tell her what I think before the review.",
    "When you check this, tell me what you think and look at the tests too.",
    "Can you look at the deploy and check what failed, then tell me.",
    "I think we should look at the logs first and check what the code does.",
    "Please check the branch and tell me what you think of the change.",
    "Look at what the job does and check the code path you think is wrong.",
]
SPECIFIC = "milog probe install-service rewrites the systemd unit from defaults, dropping custom flags."


def run_hook(state: str, payload: dict) -> str:
    env = {**os.environ, "AGENT_WORKBENCH_STATE_DIR": state}
    result = subprocess.run(
        ["bash", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=state, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def spawn(state: str, prompt: str, agent_type: str = "general-purpose", session: str = "s1") -> str:
    """Run the hook as Claude Code does for one Agent call: PreToolUse, then SubagentStart."""
    pre = run_hook(state, {
        "session_id": session,
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {"prompt": prompt, "subagent_type": agent_type, "description": "task"},
    })
    assert pre == "", pre
    return run_hook(state, {
        "session_id": session, "hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": agent_type,
    })


class SubagentRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = tmp.name
        config = WorkbenchConfig(workbench_home=Path(self.state))
        for content in FILLER:
            remember(content, config=config)
        self.specific_id = remember(SPECIFIC, kind="gotcha", project="milog", config=config)["id"]

    def test_a_matching_spawn_prompt_gets_a_bounded_context_block(self) -> None:
        out = json.loads(spawn(self.state, "Find out why milog install-service breaks the systemd unit."))
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SubagentStart")
        self.assertIn(f"[gotcha#{self.specific_id}]", context)
        self.assertLessEqual(len(context), cli.SUBAGENT_CONTEXT_CHARS)

    def test_a_non_matching_spawn_prompt_injects_nothing(self) -> None:
        self.assertEqual(spawn(self.state, "can you look at the code and tell me what you think"), "")

    def test_the_parent_session_having_seen_a_note_does_not_hide_it_from_the_subagent(self) -> None:
        prompt = "why does milog install-service break systemd"
        cli._recall_brief(prompt, WorkbenchConfig(workbench_home=Path(self.state)), "s1")
        self.assertIn(f"#{self.specific_id}]", spawn(self.state, prompt))

    def test_a_start_with_nothing_stashed_or_a_bad_payload_injects_nothing(self) -> None:
        start = {"session_id": "s1", "hook_event_name": "SubagentStart", "agent_type": "Explore"}
        self.assertEqual(run_hook(self.state, start), "")
        env = {**os.environ, "AGENT_WORKBENCH_STATE_DIR": self.state}
        result = subprocess.run(["bash", str(HOOK)], input="not json", capture_output=True, text=True, env=env)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


class SpawnStashTests(unittest.TestCase):
    def test_parallel_spawns_claim_prompts_in_order_and_prefer_their_own_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            prompt_recall.stash_spawn_prompt("s1", "general-purpose", "alpha", config)
            prompt_recall.stash_spawn_prompt("s1", "Explore", "beta", config)
            prompt_recall.stash_spawn_prompt("s1", "general-purpose", "gamma", config)
            prompt_recall.stash_spawn_prompt("s2", "general-purpose", "other session", config)
            self.assertEqual(prompt_recall.pop_spawn_prompt("s1", "Explore", config), "beta")
            self.assertEqual(prompt_recall.pop_spawn_prompt("s1", "general-purpose", config), "alpha")
            self.assertEqual(prompt_recall.pop_spawn_prompt("s1", "fork", config), "gamma")
            self.assertEqual(prompt_recall.pop_spawn_prompt("s1", "general-purpose", config), "")

    def test_an_expired_stash_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            prompt_recall.stash_spawn_prompt("s1", "Explore", "stale", config)
            (stashed,) = (Path(tmp) / prompt_recall.SPAWN_DIR).iterdir()
            old = stashed.stat().st_mtime - prompt_recall.SPAWN_TTL_SECONDS - 1
            os.utime(stashed, (old, old))
            self.assertEqual(prompt_recall.pop_spawn_prompt("s1", "Explore", config), "")
            self.assertFalse(stashed.exists())


if __name__ == "__main__":
    unittest.main()
