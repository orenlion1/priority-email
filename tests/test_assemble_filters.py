import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "filters" / "assemble-filters.py"
spec = importlib.util.spec_from_file_location("assemble_filters", MODULE_PATH)
assemble_filters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_filters)


def ops_stream(*ops):
    return io.StringIO("".join(json.dumps(op) + "\n" for op in ops))


class AssembleFiltersTest(unittest.TestCase):
    def test_baseline_then_add_keeps_newest_first(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "baseline", "kind": "domain", "values": ["old.com", "older.com"]},
                {"action": "add", "kind": "domain", "value": "new.com"},
            )
        )
        self.assertEqual(lists["domain"], ["new.com", "old.com", "older.com"])

    def test_add_is_deduplicated_case_insensitively(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "add", "kind": "sender-name", "value": "Ada Lovelace"},
                {"action": "add", "kind": "sender-name", "value": "ada lovelace"},
            )
        )
        self.assertEqual(lists["sender-name"], ["Ada Lovelace"])

    def test_domain_dedupe_ignores_leading_at_sign(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "add", "kind": "domain", "value": "example.com"},
                {"action": "add", "kind": "domain", "value": "@Example.com"},
            )
        )
        self.assertEqual(lists["domain"], ["example.com"])

    def test_remove_deletes_matching_entry(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "baseline", "kind": "email-address", "values": ["a@x.com", "b@x.com"]},
                {"action": "remove", "kind": "email-address", "value": "A@X.com"},
            )
        )
        self.assertEqual(lists["email-address"], ["b@x.com"])

    def test_remove_of_absent_value_is_noop(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "add", "kind": "domain", "value": "keep.com"},
                {"action": "remove", "kind": "domain", "value": "missing.com"},
            )
        )
        self.assertEqual(lists["domain"], ["keep.com"])

    def test_later_baseline_replaces_earlier_state(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {"action": "add", "kind": "domain", "value": "before.com"},
                {"action": "baseline", "kind": "domain", "values": ["reset.com"]},
            )
        )
        self.assertEqual(lists["domain"], ["reset.com"])

    def test_baseline_deduplicates_values(self):
        lists = assemble_filters.assemble(
            ops_stream(
                {
                    "action": "baseline",
                    "kind": "sender-name",
                    "values": ["Ada", "  ada ", "Grace"],
                }
            )
        )
        self.assertEqual(lists["sender-name"], ["Ada", "Grace"])

    def test_value_whitespace_is_collapsed(self):
        lists = assemble_filters.assemble(
            ops_stream({"action": "add", "kind": "sender-name", "value": "  Ada   Lovelace  "})
        )
        self.assertEqual(lists["sender-name"], ["Ada Lovelace"])

    def test_unknown_action_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "replace", "kind": "domain", "value": "x.com"})
            )

    def test_unknown_kind_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "subject", "value": "x"})
            )

    def test_invalid_json_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(io.StringIO("not-json\n"))

    def test_empty_value_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "domain", "value": "   "})
            )

    def test_control_characters_fail(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "domain", "value": "bad\x00.com"})
            )

    def test_comment_style_value_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "domain", "value": "# comment"})
            )

    def test_overlong_value_fails(self):
        with self.assertRaises(ValueError):
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "domain", "value": "a" * 400})
            )

    def test_error_message_never_contains_filter_value(self):
        secret_value = "very-private-sender\x01@example.com"
        try:
            assemble_filters.assemble(
                ops_stream({"action": "add", "kind": "email-address", "value": secret_value})
            )
        except ValueError as exc:
            self.assertNotIn("very-private-sender", str(exc))
        else:
            self.fail("expected ValueError")

    def test_write_filter_files_writes_all_three_kinds(self):
        lists = assemble_filters.assemble(
            ops_stream({"action": "add", "kind": "domain", "value": "example.com"})
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            assemble_filters.write_filter_files(lists, out)
            self.assertEqual((out / "domain-filters.txt").read_text(), "example.com\n")
            self.assertEqual((out / "email-address-filters.txt").read_text(), "")
            self.assertEqual((out / "sender-name-filters.txt").read_text(), "")


if __name__ == "__main__":
    unittest.main()
