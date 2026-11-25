from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS = sorted((REPO / "harness" / "agents").glob("*.md"))
VALIDATOR = REPO / "harness" / "agents" / "validate_return.py"

_spec = importlib.util.spec_from_file_location("validate_return", VALIDATOR)
validate_return = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_return)


class ReturnSchemaTests(unittest.TestCase):
    """Prose reads the same whether a claim was checked or guessed.

    Each agent type declares what a record must carry, and the parent runs the
    validator before it believes anything. A single bad record rejects the whole
    return on purpose: dropping it would lose work silently, which is the
    failure this exists to prevent.
    """

    def test_every_agent_type_declares_a_schema(self) -> None:
        for path in AGENTS:
            schema = validate_return.load_schema(path.stem)
            for key in validate_return.SCHEMA_KEYS:
                self.assertIn(key, schema, f"{path.name}: schema lacks {key}")

    def test_every_declared_schema_demands_some_evidence(self) -> None:
        for path in AGENTS:
            schema = validate_return.load_schema(path.stem)
            self.assertTrue(
                schema["evidence_any_of"],
                f"{path.name}: a schema with no evidence field cannot reject an untraceable claim",
            )

    def test_every_agent_shows_an_example_its_own_schema_accepts(self) -> None:
        # An example that would be rejected teaches the agent the wrong shape.
        for path in AGENTS:
            text = path.read_text()
            fences = validate_return._JSON_FENCE.findall(text)
            self.assertTrue(fences, f"{path.name}: no ```json example for the agent to copy")
            self.assertEqual(
                validate_return.validate(path.stem, fences[-1]),
                [],
                f"{path.name}: its own example does not satisfy its schema",
            )

    def test_a_record_without_evidence_is_rejected(self) -> None:
        errors = validate_return.validate("scout", '{"records": [{"claim": "x", "status": "verified"}]}')
        self.assertTrue(any("names no evidence" in error for error in errors))

    def test_a_value_outside_the_enum_is_rejected(self) -> None:
        errors = validate_return.validate(
            "scout", '{"records": [{"claim": "x", "status": "probably", "path": "a.py:1"}]}'
        )
        self.assertTrue(any("not one of" in error for error in errors))

    def test_a_missing_required_field_is_rejected(self) -> None:
        errors = validate_return.validate("adversary", '{"records": [{"claim": "x", "confidence": "verified", "path": "a.py:1"}]}')
        self.assertTrue(any("failure" in error for error in errors))

    def test_an_unknown_field_is_rejected_rather_than_ignored(self) -> None:
        errors = validate_return.validate(
            "scout", '{"records": [{"claim": "x", "status": "verified", "path": "a.py:1", "vibes": "good"}]}'
        )
        self.assertTrue(any("vibes" in error for error in errors))

    def test_one_bad_record_rejects_the_whole_return(self) -> None:
        payload = json.dumps(
            {
                "records": [
                    {"claim": "good", "status": "verified", "path": "a.py:1"},
                    {"claim": "bad", "status": "verified"},
                ]
            }
        )
        self.assertNotEqual(validate_return.validate("scout", payload), [])

    def test_adversary_may_return_nothing_but_scout_may_not(self) -> None:
        # Finding no bug is a real answer; finding no information is not.
        self.assertEqual(validate_return.validate("adversary", '{"records": []}'), [])
        self.assertNotEqual(validate_return.validate("scout", '{"records": []}'), [])

    def test_an_implementer_change_needs_the_verification_it_ran(self) -> None:
        errors = validate_return.validate("implementer", '{"records": [{"path": "a.py", "summary": "did a thing"}]}')
        self.assertTrue(any("names no evidence" in error for error in errors))

    def test_records_are_read_from_the_last_json_fence_in_a_reply(self) -> None:
        reply = (
            "Here is an illustrative shape:\n\n```json\n{\"records\": [{\"claim\": \"ignore me\"}]}\n```\n\n"
            "And the real answer:\n\n```json\n{\"records\": "
            "[{\"claim\": \"real\", \"status\": \"verified\", \"path\": \"a.py:1\"}]}\n```\n"
        )
        self.assertEqual(validate_return.validate("scout", reply), [])

    def test_a_bare_list_is_accepted(self) -> None:
        self.assertEqual(
            validate_return.validate("scout", '[{"claim": "x", "status": "verified", "path": "a.py:1"}]'),
            [],
        )

    def test_a_reply_with_no_json_at_all_is_an_input_error(self) -> None:
        with self.assertRaises(ValueError):
            validate_return.validate("scout", "I had a look and it seems fine.")

    def test_an_unknown_agent_name_is_an_input_error(self) -> None:
        with self.assertRaises(FileNotFoundError):
            validate_return.load_schema("nonexistent")


if __name__ == "__main__":
    unittest.main()
