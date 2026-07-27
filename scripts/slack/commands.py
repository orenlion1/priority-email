"""Parsing for the priority-email Slack management channel.

Every command follows one shape: `command sub-command [args]`. A top-level
verb (`filter`, `provider`, `poll`, `help`) names the area; its sub-command
names the action (`filter add domain example.com`, `provider list`, `poll
now`). The uniform shape is what makes the channel learnable -- `help` groups
by the same top-level verbs, and `help <command>` narrows to one group. New
commands and new actions on existing commands follow the same shape; there are
no bare top-level verbs (`add example.com`, `poll`).

Anything else gets a usage hint rather than silence -- a channel command that
does nothing visible is indistinguishable from a broken bot.

Parsing is separated from execution so the rules are testable without S3,
Slack, or a network. Execution (reading the assembled filter store, invoking
the poller Lambda) lives in the handler; only the shape and the value
validation are decided here. The value rules deliberately mirror
scripts/filters/assemble-filters.py, the source of truth the Deploy workflow
runs, so a filter accepted here is one the assembler will also accept.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Shared Slack command-grammar primitives (verb dispatch, markup stripping, the
# ParseError reply type, and the help renderer) live in slackkit; only the
# priority-email verbs, validation, and help text are local.
from slackkit import Help, ParseError, dispatch

# The filter kinds the poller matches on, and the assembler recognises. Kept in
# the same order assemble-filters.py lists them so the two cannot drift.
FILTER_KINDS = ("domain", "email-address", "sender-name")

# The mail providers the poller knows about. gmail is live; yahoo and icloud are
# stubbed for future implementation (see README). Named here only so `provider`
# help and usage can list them; the live enabled set is read by the handler.
PROVIDERS = ("gmail", "yahoo", "icloud")

# Mirrors assemble-filters.MAX_VALUE_LENGTH so a value this accepts is one the
# assembler will also accept rather than reject after it is committed.
MAX_VALUE_LENGTH = 320

USAGE = (
    "Commands are `command sub-command`. Try `help` for the full list, or "
    "e.g. `filter list`, `filter add domain example.com`, `provider list`."
)


class Action(Enum):
    FILTER_LIST = "filter_list"
    FILTER_ADD = "filter_add"
    FILTER_REMOVE = "filter_remove"
    PROVIDER_LIST = "provider_list"
    POLL_NOW = "poll_now"
    HELP = "help"


# ---------------------------------------------------------------------------
# Value rules, mirrored from assemble-filters.py so this module and the
# assembler agree on what a filter value is. collapse/comparison_key/validate
# are the same three the assembler applies before writing a filter file.
# ---------------------------------------------------------------------------
def collapse(value: str) -> str:
    return " ".join(str(value).strip().split())


def comparison_key(kind: str, value: str) -> str:
    key = collapse(value).lower()
    if kind == "domain":
        # A domain filter matches with or without a leading `@`, so the two
        # spellings must dedupe to the same entry.
        key = key.removeprefix("@")
    return key


def _validate_value(value: str) -> str | None:
    """The collapsed value, or None when it is not a storable filter value.

    The same constraints assemble-filters.validate_value enforces, so a value
    this accepts survives the assembler the Deploy workflow runs. Returns None
    rather than raising: every rejection has a user-facing reply.
    """
    collapsed = collapse(value)
    if not collapsed:
        return None
    if len(collapsed) > MAX_VALUE_LENGTH:
        return None
    if collapsed.startswith("#"):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in collapsed):
        return None
    return collapsed


# ---------------------------------------------------------------------------
# Per-command usage strings. Each names its command's sub-commands in the same
# `command sub-command` form the parser accepts, so a rejection shows exactly
# what to type.
# ---------------------------------------------------------------------------
def _filter_usage() -> str:
    kinds = ", ".join(f"`{k}`" for k in FILTER_KINDS)
    return (
        "Usage: `filter list`, `filter add <kind> <value>`, or "
        f"`filter remove <kind> <value>`. Kinds: {kinds}. "
        "E.g. `filter add domain example.com`."
    )


def _provider_usage() -> str:
    return "Usage: `provider list` — show the mail providers and their state."


def _poll_usage() -> str:
    return "Usage: `poll now` — run a poll cycle immediately."


# ---------------------------------------------------------------------------
# Help. One section per top-level command, keyed by the command's verb, so
# `help` can join them all and `help <command>` can return just one.
# ---------------------------------------------------------------------------
def _help_sections() -> dict[str, str]:
    """The help section for each top-level command, keyed by its verb.

    Built lazily so the kind list stays sourced from FILTER_KINDS and the
    provider list from PROVIDERS, and cannot drift from what the poller and the
    assembler actually recognise.
    """
    kinds = "\n".join(f"    • `{k}`" for k in FILTER_KINDS)
    providers = ", ".join(f"`{p}`" for p in PROVIDERS)
    return {
        "filter": (
            "*Sender filters* (`filter …`) — which senders raise a priority "
            "alert:\n"
            "• `filter list` — show the configured filters, grouped by kind\n"
            "• `filter add <kind> <value>` — start matching on a sender, e.g. "
            "`filter add domain example.com`. A domain matches with or without a "
            "leading `@`; adding one already present is a no-op\n"
            "• `filter remove <kind> <value>` — stop matching on one, e.g. "
            "`filter remove sender-name \"Ada Lovelace\"`\n"
            f"  Kinds:\n{kinds}"
        ),
        "provider": (
            "*Mail providers* (`provider …`) — the accounts the poller reads:\n"
            f"• `provider list` — show the providers ({providers}) and which are "
            "enabled. gmail is live; yahoo and icloud are stubbed for future "
            "implementation."
        ),
        "poll": (
            "*Run a poll* (`poll …`) — check for new priority mail without "
            "waiting for the scheduled run:\n"
            "• `poll now` — run one poll cycle immediately. New matches post to "
            "the alert channel within a minute or two"
        ),
        "help": (
            "*Help* (`help …`):\n"
            "• `help` — show every command\n"
            "• `help <command>` — show help for one command, e.g. `help filter`"
        ),
    }


# Friendly spellings for `help <command>`, so `help filters` or `help providers`
# still resolves rather than erroring on a near miss.
_HELP_ALIASES = {
    "filters": "filter",
    "providers": "provider",
    "provides": "provider",
    "polls": "poll",
    "add": "filter",
    "remove": "filter",
    "list": "filter",
}


# slackkit.Help renders `help` / `help <command>` from the per-verb sections
# above, keyed by the same verbs the parser dispatches on. Built at import so the
# sections stay sourced lazily from FILTER_KINDS / PROVIDERS.
_HELP = Help(
    intro=(
        "*priority-email commands* — every command is `command sub-command`. "
        "`help <command>` shows help for just one command.\n"
    ),
    sections=_help_sections,
    aliases=_HELP_ALIASES,
)


def help_text(topic: str | None = None) -> str:
    """The command reference, whole or for one command (via slackkit.Help)."""
    return _HELP.text(topic)


@dataclass(frozen=True)
class Command:
    action: Action
    kind: str | None = None
    value: str | None = None
    # For HELP: the command the user asked help for, or None for the full list.
    topic: str | None = None


def parse(text: str) -> Command | ParseError:
    """Parse a channel message into a Command, or a ParseError to reply with.

    slackkit.dispatch handles the shared mechanics -- Slack markup stripping,
    tokenising, case-insensitive verb lookup, and the empty-message /
    unknown-verb replies -- then hands the tokens to the matching `_parse_<verb>`
    below. Returns a ParseError rather than raising: every bad input has a
    user-facing answer.
    """
    parsers = {
        "help": _parse_help,
        "filter": _parse_filter,
        "provider": _parse_provider,
        "poll": _parse_poll,
    }
    return dispatch(text, parsers, usage=USAGE)


def _parse_help(parts: list[str]) -> Command | ParseError:
    """`help` (everything) and `help <command>` (one command)."""
    if len(parts) == 1:
        return Command(Action.HELP)
    if len(parts) == 2:
        return Command(Action.HELP, topic=parts[1].lower())
    return ParseError("Usage: `help`, or `help <command>` for one command.")


def _parse_filter(parts: list[str]) -> Command | ParseError:
    """`filter list`, `filter add <kind> <value>`, `filter remove <kind> <value>`.

    Both a bad kind and an unstorable value are rejected here rather than
    passed on: an unknown kind would be dropped by the assembler and an empty or
    control-character value would be refused after it was committed, and in both
    cases the operator would see the failure far from where they typed it.
    """
    if len(parts) < 2:
        return ParseError(f"`filter` needs a sub-command. {_filter_usage()}")

    sub = parts[1].lower()

    if sub == "list":
        if len(parts) != 2:
            return ParseError(f"`filter list` takes no arguments. {_filter_usage()}")
        return Command(Action.FILTER_LIST)

    if sub in ("add", "remove"):
        if len(parts) < 3:
            return ParseError(f"`filter {sub}` needs a kind. {_filter_usage()}")
        kind = parts[2].lower()
        if kind not in FILTER_KINDS:
            return ParseError(f"`{parts[2]}` is not a filter kind. {_filter_usage()}")
        if len(parts) < 4:
            return ParseError(
                f"`filter {sub} {kind}` needs a value. {_filter_usage()}"
            )
        # The value is the rest of the message, so a sender name with spaces
        # ("Ada Lovelace") is captured whole rather than truncated to one token.
        raw = " ".join(parts[3:])
        value = _validate_value(raw)
        if value is None:
            return ParseError(
                f"`{raw}` is not a usable filter value. {_filter_usage()}"
            )
        action = Action.FILTER_ADD if sub == "add" else Action.FILTER_REMOVE
        return Command(action, kind=kind, value=value)

    return ParseError(f"Did not understand `filter {parts[1]}`. {_filter_usage()}")


def _parse_provider(parts: list[str]) -> Command | ParseError:
    """`provider list` — show the mail providers and their state."""
    if len(parts) == 2 and parts[1].lower() == "list":
        return Command(Action.PROVIDER_LIST)
    return ParseError(f"Did not understand that. {_provider_usage()}")


def _parse_poll(parts: list[str]) -> Command | ParseError:
    """`poll now` — run the poller on demand."""
    if len(parts) == 2 and parts[1].lower() == "now":
        return Command(Action.POLL_NOW)
    return ParseError(f"Did not understand that. {_poll_usage()}")


def apply_to(
    command: Command, current: dict[str, list[str]]
) -> tuple[dict[str, list[str]], str] | ParseError:
    """Apply a parsed filter command to the current filter lists.

    `current` maps each kind to its entries (newest first, as the assembler
    stores them). Returns (new_lists, reply) or a ParseError. Only filter
    actions reach here; the handler routes `provider` and `poll` before calling
    this, mirroring how the assembler is the one place filter values change.

    The dedupe and ordering match assemble-filters exactly: an add inserts at
    the head when the value is not already present (by comparison_key), and a
    remove drops every entry with the same key. Doing it the same way here means
    a preview reply cannot disagree with what the assembler will produce.
    """
    lists = {kind: list(current.get(kind, [])) for kind in FILTER_KINDS}

    if command.action is Action.FILTER_LIST:
        return lists, _describe_filters(lists)

    assert command.kind is not None and command.value is not None  # from parse()
    entries = lists[command.kind]
    key = comparison_key(command.kind, command.value)

    if command.action is Action.FILTER_ADD:
        if any(comparison_key(command.kind, existing) == key for existing in entries):
            return lists, (
                f"`{command.value}` is already a {command.kind} filter."
            )
        # Newest entries stay at the head of each filter file, as the assembler
        # inserts them.
        entries.insert(0, command.value)
        return lists, (
            f"Added {command.kind} filter `{command.value}`. "
            f"Now {len(entries)} {command.kind} filters."
        )

    # FILTER_REMOVE.
    kept = [e for e in entries if comparison_key(command.kind, e) != key]
    if len(kept) == len(entries):
        return lists, f"`{command.value}` is not a {command.kind} filter."
    lists[command.kind] = kept
    return lists, (
        f"Removed {command.kind} filter `{command.value}`. "
        f"Now {len(kept)} {command.kind} filters."
    )


def _describe_filters(lists: dict[str, list[str]]) -> str:
    """A per-kind listing of the configured filters, or the empty case.

    Reports each kind even when empty so "no domain filters" is distinguishable
    from a kind that failed to load, the same way `filter list` should never be
    silent about a whole category.
    """
    if not any(lists.get(kind) for kind in FILTER_KINDS):
        return "No filters configured. Add one with `filter add <kind> <value>`."

    blocks = []
    for kind in FILTER_KINDS:
        entries = lists.get(kind, [])
        if not entries:
            blocks.append(f"*{kind}* — none")
            continue
        shown = "\n".join(f"• {e}" for e in entries)
        blocks.append(f"*{kind}* ({len(entries)}):\n{shown}")
    return "\n\n".join(blocks)
