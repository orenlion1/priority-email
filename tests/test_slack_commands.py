import importlib.util
import sys
from pathlib import Path
import unittest


def _load(module_name, filename):
    path = Path(__file__).resolve().parents[1] / "scripts" / "slack" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve the module's string
    # annotations (`from __future__ import annotations`) via sys.modules.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


commands = _load("slack_commands", "commands.py")
Action = commands.Action
Command = commands.Command
ParseError = commands.ParseError


class ParseTest(unittest.TestCase):
    def test_blank_message_is_usage(self):
        result = commands.parse("   ")
        self.assertIsInstance(result, ParseError)
        self.assertIn("command sub-command", result.message)

    def test_unknown_verb_points_at_help(self):
        result = commands.parse("frobnicate everything")
        self.assertIsInstance(result, ParseError)
        self.assertIn("help", result.message)

    def test_bare_verb_without_subcommand_is_rejected(self):
        # The grammar has no bare top-level verbs: `filter` alone is an error.
        for text in ("filter", "provider", "poll"):
            self.assertIsInstance(commands.parse(text), ParseError)

    def test_help_lists_every_command(self):
        self.assertEqual(commands.parse("help"), Command(Action.HELP))

    def test_help_for_one_command_carries_the_topic(self):
        self.assertEqual(
            commands.parse("help filter"), Command(Action.HELP, topic="filter")
        )

    def test_help_with_too_many_args_is_rejected(self):
        self.assertIsInstance(commands.parse("help filter provider"), ParseError)

    def test_provider_list(self):
        self.assertEqual(commands.parse("provider list"), Command(Action.PROVIDER_LIST))

    def test_provider_rejects_unknown_subcommand(self):
        self.assertIsInstance(commands.parse("provider add"), ParseError)

    def test_poll_now(self):
        self.assertEqual(commands.parse("poll now"), Command(Action.POLL_NOW))

    def test_poll_rejects_anything_else(self):
        self.assertIsInstance(commands.parse("poll later"), ParseError)


class FilterParseTest(unittest.TestCase):
    def test_filter_list_takes_no_args(self):
        self.assertEqual(commands.parse("filter list"), Command(Action.FILTER_LIST))
        self.assertIsInstance(commands.parse("filter list domain"), ParseError)

    def test_filter_add_domain(self):
        self.assertEqual(
            commands.parse("filter add domain example.com"),
            Command(Action.FILTER_ADD, kind="domain", value="example.com"),
        )

    def test_filter_add_rejects_unknown_kind(self):
        result = commands.parse("filter add subject urgent")
        self.assertIsInstance(result, ParseError)
        self.assertIn("filter kind", result.message)

    def test_filter_add_needs_a_value(self):
        self.assertIsInstance(commands.parse("filter add domain"), ParseError)

    def test_sender_name_value_keeps_its_spaces(self):
        # The value is the rest of the message, so a multi-word sender name is
        # captured whole rather than truncated to the first token.
        self.assertEqual(
            commands.parse("filter add sender-name Ada Lovelace"),
            Command(Action.FILTER_ADD, kind="sender-name", value="Ada Lovelace"),
        )

    def test_kind_is_case_insensitive(self):
        self.assertEqual(
            commands.parse("filter add DOMAIN Example.com"),
            Command(Action.FILTER_ADD, kind="domain", value="Example.com"),
        )

    def test_control_characters_are_rejected(self):
        self.assertIsInstance(commands.parse("filter add domain a\tb\x07"), ParseError)

    def test_hash_prefixed_value_is_rejected(self):
        # The assembler treats a leading '#' as a comment marker and refuses it;
        # reject it here so the operator sees the error where they typed it.
        self.assertIsInstance(commands.parse("filter add domain #example.com"), ParseError)

    def test_strips_slack_link_markup_on_an_email_address(self):
        # Slack renders a typed address as <mailto:x@y|x@y>; parsing must recover
        # the bare address, not store the markup.
        self.assertEqual(
            commands.parse("filter add email-address <mailto:a@b.com|a@b.com>"),
            Command(Action.FILTER_ADD, kind="email-address", value="a@b.com"),
        )

    def test_strips_code_backticks(self):
        self.assertEqual(
            commands.parse("filter add domain `example.com`"),
            Command(Action.FILTER_ADD, kind="domain", value="example.com"),
        )


class ApplyTest(unittest.TestCase):
    def test_add_inserts_newest_first(self):
        lists, reply = commands.apply_to(
            Command(Action.FILTER_ADD, kind="domain", value="new.com"),
            {"domain": ["old.com"]},
        )
        self.assertEqual(lists["domain"], ["new.com", "old.com"])
        self.assertIn("Added", reply)

    def test_add_is_case_insensitive_noop_when_present(self):
        lists, reply = commands.apply_to(
            Command(Action.FILTER_ADD, kind="sender-name", value="ada lovelace"),
            {"sender-name": ["Ada Lovelace"]},
        )
        self.assertEqual(lists["sender-name"], ["Ada Lovelace"])
        self.assertIn("already", reply)

    def test_domain_add_ignores_leading_at_when_deduping(self):
        lists, reply = commands.apply_to(
            Command(Action.FILTER_ADD, kind="domain", value="@example.com"),
            {"domain": ["example.com"]},
        )
        self.assertEqual(lists["domain"], ["example.com"])
        self.assertIn("already", reply)

    def test_remove_drops_the_entry(self):
        lists, reply = commands.apply_to(
            Command(Action.FILTER_REMOVE, kind="domain", value="drop.com"),
            {"domain": ["keep.com", "drop.com"]},
        )
        self.assertEqual(lists["domain"], ["keep.com"])
        self.assertIn("Removed", reply)

    def test_remove_absent_value_reports_it(self):
        lists, reply = commands.apply_to(
            Command(Action.FILTER_REMOVE, kind="domain", value="ghost.com"),
            {"domain": ["keep.com"]},
        )
        self.assertEqual(lists["domain"], ["keep.com"])
        self.assertIn("not a domain filter", reply)

    def test_list_empty_case(self):
        _, reply = commands.apply_to(
            Command(Action.FILTER_LIST), {kind: [] for kind in commands.FILTER_KINDS}
        )
        self.assertIn("No filters configured", reply)

    def test_list_groups_by_kind(self):
        _, reply = commands.apply_to(
            Command(Action.FILTER_LIST),
            {"domain": ["a.com"], "email-address": [], "sender-name": ["Bob"]},
        )
        self.assertIn("domain", reply)
        self.assertIn("a.com", reply)
        self.assertIn("Bob", reply)


class HelpTextTest(unittest.TestCase):
    def test_full_help_names_every_command(self):
        text = commands.help_text()
        for verb in ("filter", "provider", "poll", "help"):
            self.assertIn(verb, text)

    def test_help_for_one_command_returns_only_that_section(self):
        text = commands.help_text("provider")
        self.assertIn("Mail providers", text)
        self.assertNotIn("Sender filters", text)

    def test_help_alias_resolves(self):
        self.assertEqual(commands.help_text("filters"), commands.help_text("filter"))

    def test_unknown_topic_lists_the_valid_ones(self):
        text = commands.help_text("nonsense")
        self.assertIn("No help for", text)
        self.assertIn("filter", text)

    def test_help_lists_the_filter_kinds(self):
        text = commands.help_text("filter")
        for kind in commands.FILTER_KINDS:
            self.assertIn(kind, text)


if __name__ == "__main__":
    unittest.main()
