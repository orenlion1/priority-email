"""Tests for the priority-email Slack command parser and filter algebra.

Parsing and the add/remove/list algebra are pure -- no S3, Slack, or network --
so they are exercised directly here. Skipped when slackkit is not importable
(it ships from CodeArtifact into the Lambda bundle and onto the test path in CI);
the poller tests do not depend on it, so a bare checkout still runs those.
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    import slackkit  # noqa: F401
except ImportError:  # pragma: no cover - environment without slackkit
    raise unittest.SkipTest("slackkit not installed (ships from CodeArtifact in CI)")

from slack import commands  # noqa: E402
from slack.commands import Action  # noqa: E402
from slackkit import ParseError  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_help_and_help_topic(self):
        self.assertEqual(commands.parse("help").action, Action.HELP)
        cmd = commands.parse("help filter")
        self.assertEqual(cmd.action, Action.HELP)
        self.assertEqual(cmd.topic, "filter")

    def test_filter_add_domain_including_wildcard(self):
        for value in ("example.com", "@example.com", "coralogix*.com"):
            cmd = commands.parse(f"filter add domain {value}")
            self.assertEqual(cmd.action, Action.FILTER_ADD)
            self.assertEqual(cmd.kind, "domain")
            self.assertEqual(cmd.value, value)

    def test_filter_add_sender_name_keeps_spaces(self):
        cmd = commands.parse("filter add sender-name Ada Lovelace")
        self.assertEqual(cmd.kind, "sender-name")
        self.assertEqual(cmd.value, "Ada Lovelace")

    def test_unknown_verb_and_bare_verb_are_parse_errors(self):
        self.assertIsInstance(commands.parse("add example.com"), ParseError)
        self.assertIsInstance(commands.parse("filter"), ParseError)
        self.assertIsInstance(commands.parse(""), ParseError)

    def test_bad_kind_is_rejected_where_typed(self):
        err = commands.parse("filter add nonsense x")
        self.assertIsInstance(err, ParseError)
        self.assertIn("not a filter kind", err.message)

    def test_provider_and_poll(self):
        self.assertEqual(commands.parse("provider list").action, Action.PROVIDER_LIST)
        self.assertEqual(commands.parse("poll now").action, Action.POLL_NOW)
        self.assertIsInstance(commands.parse("poll later"), ParseError)


class ApplyTests(unittest.TestCase):
    def _empty(self):
        return {kind: [] for kind in ("domain", "email-address", "sender-name")}

    def test_add_inserts_newest_first(self):
        lists = self._empty()
        lists["domain"] = ["old.com"]
        cmd = commands.parse("filter add domain new.com")
        new_lists, reply = commands.apply_to(cmd, lists)
        self.assertEqual(new_lists["domain"], ["new.com", "old.com"])
        self.assertIn("Added", reply)

    def test_add_duplicate_is_noop_reply(self):
        lists = self._empty()
        lists["domain"] = ["example.com"]
        cmd = commands.parse("filter add domain @example.com")  # dedupes to example.com
        new_lists, reply = commands.apply_to(cmd, lists)
        self.assertEqual(new_lists["domain"], ["example.com"])
        self.assertIn("already", reply)

    def test_remove_absent_is_noop_reply(self):
        cmd = commands.parse("filter remove domain missing.com")
        new_lists, reply = commands.apply_to(cmd, self._empty())
        self.assertEqual(new_lists["domain"], [])
        self.assertIn("not a", reply)

    def test_list_describes_each_kind(self):
        lists = self._empty()
        lists["domain"] = ["a.com"]
        cmd = commands.parse("filter list")
        _, reply = commands.apply_to(cmd, lists)
        self.assertIn("domain", reply)


if __name__ == "__main__":
    unittest.main()
