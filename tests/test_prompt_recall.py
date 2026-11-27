from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_workbench import cli, prompt_recall, rules
from agent_workbench.brain import remember
from agent_workbench.config import WorkbenchConfig

FILLER = [
    "Lori asked me to look at the code and tell her what I think before the review.",
    "When you check this, tell me what you think and look at the tests too.",
    "Can you look at the deploy and check what failed, then tell me.",
    "I think we should look at the logs first and check what the code does.",
    "Please check the branch and tell me what you think of the change.",
    "Look at what the job does and check the code path you think is wrong.",
    "Tell me what you think about this plan before we look at the code.",
    "Check the config and look at what changed, then tell me what you think.",
]
SPECIFIC = "milog probe install-service rewrites the systemd unit from defaults, dropping custom flags."


class PromptRecallTests(unittest.TestCase):
    def _brain(self, tmp: str) -> WorkbenchConfig:
        config = WorkbenchConfig(workbench_home=Path(tmp))
        for content in FILLER:
            remember(content, config=config)
        self.specific_id = remember(SPECIFIC, kind="gotcha", project="milog", config=config)["id"]
        return config

    def test_a_generic_prompt_injects_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain(tmp)
            prompt = "can you look at the code and tell me what you think"
            self.assertEqual(prompt_recall.prompt_hits(prompt, config=config), [])
            self.assertEqual(cli._recall_brief(prompt, config, "s1"), "")

    def test_a_prompt_naming_a_specific_term_gets_its_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain(tmp)
            hits = prompt_recall.prompt_hits("why does milog install-service break systemd", config=config)
            self.assertEqual([hit["id"] for hit in hits], [self.specific_id])
            self.assertGreaterEqual(hits[0]["strength"], prompt_recall.RELEVANCE_FLOOR)

    def test_a_note_is_not_repeated_in_the_same_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain(tmp)
            prompt = "why does milog install-service break systemd"
            self.assertIn(f"#{self.specific_id}]", cli._recall_brief(prompt, config, "s1"))
            self.assertEqual(cli._recall_brief(prompt, config, "s1"), "")
            self.assertIn(f"#{self.specific_id}]", cli._recall_brief(prompt, config, "s2"))

    def test_a_stronger_match_is_injected_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain(tmp)
            weak = prompt_recall.prompt_hits("why does milog install-service break", session_id="s1", config=config)
            self.assertEqual([hit["id"] for hit in weak], [self.specific_id])
            strong = prompt_recall.prompt_hits(
                "milog install-service rewrites systemd unit defaults", session_id="s1", config=config
            )
            self.assertEqual([hit["id"] for hit in strong], [self.specific_id])
            self.assertGreater(strong[0]["strength"], weak[0]["strength"])

    def test_expired_and_corrupt_session_state_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._brain(tmp)
            path = Path(tmp) / prompt_recall.SESSIONS_FILE
            path.write_text(json.dumps({"old": {"at": 0, "notes": {str(self.specific_id): 99}}}))
            prompt = "why does milog install-service break systemd"
            self.assertEqual(len(prompt_recall.prompt_hits(prompt, session_id="old", config=config)), 1)
            self.assertNotIn("0", [str(entry["at"]) for entry in json.loads(path.read_text()).values()])
            path.write_text("not json")
            self.assertEqual(len(prompt_recall.prompt_hits(prompt, session_id="new", config=config)), 1)


class RulesBriefTests(unittest.TestCase):
    def test_an_out_of_scope_rule_is_not_injected_even_on_its_trigger_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            rules.remember_rule(
                "give the exact kubectl command",
                scope=["task:trigger-shared-env"],
                trigger=["how", "trigger"],
                config=config,
            )
            rules.remember_rule("holds everywhere", config=config)
            brief = cli._rules_brief(config)
            self.assertIn("holds everywhere", brief)
            self.assertNotIn("kubectl", brief)

    def test_a_rule_scoped_to_this_repo_is_injected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkbenchConfig(workbench_home=Path(tmp))
            repo = Path(__file__).resolve().parents[1].name
            rules.remember_rule("run the whole suite", scope=[f"repo:{repo}"], config=config)
            self.assertIn("run the whole suite", cli._rules_brief(config))


if __name__ == "__main__":
    unittest.main()
