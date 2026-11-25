from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_workbench import rules
from agent_workbench.config import WorkbenchConfig


class ContextualRuleTests(unittest.TestCase):
    """A correction is knowledge about how to behave, and it has a scope.

    The two acceptance criteria from issue #22 are the last two tests here: a
    rule comes back when its context returns even if the wording shares nothing
    with the correction, and two contexts can hold opposite rules for the same
    situation.
    """

    def _config(self, tmp: str) -> WorkbenchConfig:
        return WorkbenchConfig(workbench_home=Path(tmp))

    def test_a_rule_needs_a_statement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = rules.remember_rule("   ", config=self._config(tmp))
            self.assertFalse(result["stored"])

    def test_a_malformed_scope_key_is_refused_with_the_known_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = rules.remember_rule("x", scope=["runtime upgrade"], config=self._config(tmp))
            self.assertFalse(result["stored"])
            self.assertIn("repo", result["known_types"])

    def test_a_global_rule_is_stored_but_warned_about(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = rules.remember_rule("never overclaim", config=self._config(tmp))
            self.assertTrue(result["stored"])
            self.assertEqual(result["scope"], "global")
            self.assertIn("applies everywhere", result["warning"])

    def test_restating_a_rule_in_the_same_scope_sharpens_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            first = rules.remember_rule(
                "only test what the upgrade changed",
                scope=["workstream:runtime-upgrade"],
                example="skipped the full suite on service A",
                config=config,
            )
            second = rules.remember_rule(
                "only test what the upgrade actually changed",
                scope=["workstream:runtime-upgrade"],
                example="again on service B",
                config=config,
            )
            self.assertEqual(second["id"], first["id"])
            self.assertTrue(second["amended"])
            held = rules.rules_in_force(context=["workstream:runtime-upgrade"], config=config)["rules"]
            self.assertEqual(len(held), 1)
            self.assertIn("service A", held[0]["example"])
            self.assertIn("service B", held[0]["example"])

    def test_the_same_statement_in_another_scope_is_a_separate_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            a = rules.remember_rule("use the full id", scope=["audience:qa"], config=config)
            b = rules.remember_rule("use the full id", scope=["audience:client"], config=config)
            self.assertNotEqual(a["id"], b["id"])

    def test_a_rule_applies_only_when_every_scope_key_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule(
                "paste the full command", scope=["repo:svc", "audience:qa"], config=config
            )
            partial = rules.rules_in_force(context=["repo:svc"], config=config)["rules"]
            self.assertEqual(partial, [])
            both = rules.rules_in_force(context=["repo:svc", "audience:qa"], config=config)["rules"]
            self.assertEqual(len(both), 1)

    def test_declaring_two_contexts_inherits_the_rules_of_each(self) -> None:
        # The whole inheritance mechanism: no parent pointers, just the key set.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("diff-driven scope", scope=["workstream:runtime-upgrade"], config=config)
            rules.remember_rule("never push to main", scope=["repo:svc"], config=config)
            held = rules.rules_in_force(context=["repo:svc", "workstream:runtime-upgrade"], config=config)["rules"]
            self.assertEqual(len(held), 2)

    def test_a_more_specific_rule_sorts_above_a_less_specific_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("be careful", config=config)
            narrow = rules.remember_rule("be careful here", scope=["repo:svc", "task:deploy"], config=config)
            held = rules.rules_in_force(context=["repo:svc", "task:deploy"], config=config)["rules"]
            self.assertEqual(held[0]["id"], narrow["id"])

    def test_a_repo_rule_outranks_a_workstream_rule_at_equal_specificity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("workstream says one thing", scope=["workstream:w"], config=config)
            repo_rule = rules.remember_rule("repo says another thing", scope=["repo:svc"], config=config)
            held = rules.rules_in_force(context=["repo:svc", "workstream:w"], config=config)["rules"]
            self.assertEqual(held[0]["id"], repo_rule["id"])

    def test_overlapping_statements_at_equal_standing_are_reported_as_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("write the summary in english", scope=["repo:a"], config=config)
            rules.remember_rule("write the summary in indonesian", scope=["repo:b"], config=config)
            report = rules.rules_in_force(context=["repo:a", "repo:b"], config=config)
            self.assertIn("conflicts", report)

    def test_rules_that_say_different_things_are_not_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("never push to main", scope=["repo:a"], config=config)
            rules.remember_rule("stage files by name", scope=["repo:a"], config=config)
            report = rules.rules_in_force(context=["repo:a"], config=config)
            self.assertNotIn("conflicts", report)

    def test_surfacing_is_counted_and_a_correction_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = rules.remember_rule("use the full id", scope=["audience:qa"], config=config)
            rules.rules_in_force(context=["audience:qa"], config=config)
            rules.rule_feedback(stored["id"], "corrected", config=config)
            view = rules.context_view("audience:qa", config=config)
            self.assertEqual(view["rules"][0]["surfaced_count"], 1)
            self.assertEqual(view["rules"][0]["corrected_count"], 1)

    def test_an_unknown_feedback_outcome_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = rules.remember_rule("x", scope=["repo:a"], config=config)
            result = rules.rule_feedback(stored["id"], "applied", config=config)
            self.assertFalse(result["recorded"])

    def test_a_retired_rule_stops_being_in_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            stored = rules.remember_rule("obsolete rule", scope=["repo:a"], config=config)
            rules.rule_feedback(stored["id"], "retire", config=config)
            self.assertEqual(rules.rules_in_force(context=["repo:a"], config=config)["rules"], [])

    def test_a_context_view_flags_a_rule_that_has_never_been_surfaced(self) -> None:
        # Scoped to two keys that never co-occur in practice, so it can never
        # fire. That is the mis-scoping the flag exists to expose.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            unreachable = rules.remember_rule(
                "never shown anywhere", scope=["repo:a", "audience:nobody"], config=config
            )
            rules.rules_in_force(context=["repo:a"], config=config)
            view = rules.context_view("repo:a", config=config)
            self.assertIn(unreachable["id"], view["never_surfaced"])

    def test_a_context_view_flags_a_rule_that_keeps_being_corrected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            failing = rules.remember_rule("keeps being wrong", scope=["repo:a"], config=config)
            rules.rules_in_force(context=["repo:a"], config=config)
            for _ in range(2):
                rules.rule_feedback(failing["id"], "corrected", config=config)
            view = rules.context_view("repo:a", config=config)
            self.assertIn(failing["id"], view["failing"])
            self.assertNotIn(failing["id"], view.get("never_surfaced", []))

    def test_a_context_key_must_be_well_formed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = rules.context_view("repo", config=self._config(tmp))
            self.assertIn("error", result)

    def test_a_rule_returns_on_context_even_when_the_wording_shares_nothing(self) -> None:
        # Acceptance criterion: the next task in the same context gets the rule
        # without the user repeating it, and text similarity would not find it.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule(
                "state the evidence for every test claim",
                scope=["workstream:runtime-upgrade"],
                why="saying tested without running it burned a release",
                config=config,
            )
            held = rules.rules_in_force(
                prompt="is this ready for handoff?",
                context=["workstream:runtime-upgrade"],
                config=config,
            )["rules"]
            self.assertEqual(len(held), 1)
            self.assertEqual(held[0]["matched_by"], "scope")

    def test_two_contexts_hold_opposite_rules_for_the_same_situation(self) -> None:
        # Acceptance criterion: each context gets its own answer.
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule("write it in casual indonesian", scope=["audience:teammate"], config=config)
            rules.remember_rule("write it in formal english", scope=["audience:client"], config=config)
            teammate = rules.rules_in_force(context=["audience:teammate"], config=config)["rules"]
            client = rules.rules_in_force(context=["audience:client"], config=config)["rules"]
            self.assertEqual([r["statement"] for r in teammate], ["write it in casual indonesian"])
            self.assertEqual([r["statement"] for r in client], ["write it in formal english"])

    def test_a_trigger_word_surfaces_a_rule_whose_context_is_not_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            rules.remember_rule(
                "paste the full command, never a placeholder",
                scope=["audience:qa"],
                trigger=["runbook", "handoff"],
                config=config,
            )
            held = rules.rules_in_force(prompt="write the handoff doc", config=config)["rules"]
            self.assertEqual(len(held), 1)
            self.assertEqual(held[0]["matched_by"], "trigger")


if __name__ == "__main__":
    unittest.main()
