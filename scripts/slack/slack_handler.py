"""AWS Lambda entry point for the priority-email Slack management channel.

Reached through a public Function URL, so every request is untrusted until
slackkit's signing-secret verification says otherwise. slackkit owns the parts
that must not drift between this app and re-rank -- request verification, the
Events lifecycle (challenge echo, retry ack, bot-echo suppression, subtype
filtering, the channel gate), and the `command sub-command` grammar with its
generated `help`. This module supplies only the priority-email half: turning a
parsed command into an action against the S3 filter store or the poller.

The counterpart to the poller (scripts/aws/lambda_function.py): the poller reads
the filter files this handler writes, so a `filter add` here changes what the
next poll treats as priority mail. The two never call each other except through
`poll now`, which asynchronously invokes the poller for an immediate cycle.
"""

from __future__ import annotations

import logging
import os

import boto3

# slackkit: shared verification, Events lifecycle, and command-grammar core.
from slackkit import ParseError, SlackEventsHandler, post_reply

# The priority-email command surface: parser, help, and the filter-list algebra.
from slack import commands
from slack.commands import Action
from slack.filter_store import S3FilterStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

STATE_BUCKET = os.environ["STATE_BUCKET"]
SLACK_SIGNING_SECRET_ARN = os.environ["SLACK_SIGNING_SECRET_ARN"]
SLACK_BOT_TOKEN_ARN = os.environ.get("SLACK_BOT_TOKEN_ARN", "")
RUNTIME_SECRET_ID = os.environ.get("RUNTIME_SECRET_ID", "priority-email/runtime")
MANAGE_CHANNEL_ID = os.environ.get("MANAGE_CHANNEL_ID") or None
POLLER_FUNCTION_NAME = os.environ.get("POLLER_FUNCTION_NAME", "priority-email-poller")
# The committed age recipients (public) key, bundled beside this handler.
RECIPIENTS_PATH = os.environ.get(
    "AGE_RECIPIENTS_PATH",
    os.path.join(os.environ.get("LAMBDA_TASK_ROOT", ""), "filters", "age-recipients.pub"),
)

_secrets = boto3.client("secretsmanager")
_s3 = boto3.client("s3")
_lambda = boto3.client("lambda")

# Cache secret fetches across warm invocations: a signing-secret read on every
# request would add a Secrets Manager call to a path Slack retries after 3s.
_secret_cache: dict[str, str] = {}


def _secret(arn: str) -> str:
    if arn not in _secret_cache:
        _secret_cache[arn] = _secrets.get_secret_value(SecretId=arn)["SecretString"]
    return _secret_cache[arn]


def _parse_env(text: str) -> dict[str, str]:
    """Parse the runtime .env secret (KEY=VALUE lines) into a mapping.

    The runtime secret's value is the .env verbatim, the same file poll-email.py
    loads; this reads the couple of keys the handler needs (bot token, enabled
    providers) without importing the poller.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _bot_token() -> str:
    """The bot token, from its own secret if configured, else the runtime .env.

    A dedicated secret is preferred (least privilege: this role can be scoped to
    it), but the token already lives in the runtime .env the poller uses, so fall
    back to that rather than require a migration to stand the handler up.
    """
    if SLACK_BOT_TOKEN_ARN:
        return _secret(SLACK_BOT_TOKEN_ARN)
    return _parse_env(_secret(RUNTIME_SECRET_ID)).get("SLACK_BOT_TOKEN", "")


def _filter_store() -> S3FilterStore:
    return S3FilterStore(s3=_s3, bucket=STATE_BUCKET, recipients_path=RECIPIENTS_PATH)


def _reply(channel: str, text: str, thread_ts: str | None) -> None:
    post_reply(_bot_token(), channel, text, thread_ts, logger=logger)


def _describe_providers() -> str:
    """`provider list`: every known provider and whether it is enabled.

    The enabled set comes from the same EMAIL_POLL_ENABLED_PROVIDERS the poller
    reads, so the channel reports what actually runs rather than a hardcoded list.
    """
    env = _parse_env(_secret(RUNTIME_SECRET_ID))
    enabled_raw = env.get("EMAIL_POLL_ENABLED_PROVIDERS", "gmail")
    enabled = {p.strip().lower() for p in enabled_raw.split(",") if p.strip()}
    lines = ["*Mail providers*:"]
    for provider in commands.PROVIDERS:
        state = "enabled" if provider in enabled else "disabled"
        note = " (live)" if provider == "gmail" else " (stub)"
        lines.append(f"• `{provider}` — {state}{note}")
    return "\n".join(lines)


def _run_poll_now() -> str:
    """`poll now`: invoke the poller asynchronously and confirm.

    Event invocation, not RequestResponse: a poll runs for many seconds and Slack
    retries a response slower than 3s, which would double-invoke. The handler
    hands the work off and replies at once.
    """
    _lambda.invoke(FunctionName=POLLER_FUNCTION_NAME, InvocationType="Event")
    return (
        "Started a poll cycle. New matches post to the alert channel within a "
        "minute or two."
    )


def _apply_filter(parsed, channel, thread_ts, user) -> None:
    """Execute a parsed `filter` command against the S3 filter store.

    Read the current filters, run the same add/remove/list algebra the assembler
    uses (commands.apply_to), and -- only when an add or remove actually changed a
    kind -- write the plaintext file back and append an encrypted op. A no-op add
    ("already a filter") or remove ("not a filter") replies without writing, so
    the ops log records only real changes.
    """
    store = _filter_store()
    current = store.read_filters()
    result = commands.apply_to(parsed, current)
    if isinstance(result, ParseError):
        _reply(channel, result.message, thread_ts)
        return

    new_lists, message = result
    if parsed.action in (Action.FILTER_ADD, Action.FILTER_REMOVE):
        kind = parsed.kind
        if new_lists[kind] != current.get(kind, []):
            store.write_filter(kind, new_lists[kind])
            op = "add" if parsed.action is Action.FILTER_ADD else "remove"
            store.append_op(op, kind, parsed.value)
            # Log the actor on a state-changing command; never the value at INFO
            # beyond what the reply already echoes to the channel.
            logger.info("filter %s %s by user=%s", op, kind, user)
    _reply(channel, message, thread_ts)


def on_command(text: str, channel: str, thread_ts: str | None, user: str | None) -> None:
    """Route one verified channel message to its handler.

    slackkit has already verified the signature, echoed any challenge, dropped
    retries and bot echoes, and applied the channel gate; this only parses and
    dispatches. Every branch replies -- a command that does nothing visible is
    indistinguishable from a broken bot.
    """
    parsed = commands.parse(text)
    if isinstance(parsed, ParseError):
        _reply(channel, parsed.message, thread_ts)
        return

    if parsed.action is Action.HELP:
        _reply(channel, commands.help_text(parsed.topic), thread_ts)
    elif parsed.action is Action.PROVIDER_LIST:
        _reply(channel, _describe_providers(), thread_ts)
    elif parsed.action is Action.POLL_NOW:
        _reply(channel, _run_poll_now(), thread_ts)
    else:  # FILTER_LIST / FILTER_ADD / FILTER_REMOVE
        _apply_filter(parsed, channel, thread_ts, user)


handler = SlackEventsHandler(
    signing_secret=lambda: _secret(SLACK_SIGNING_SECRET_ARN),
    allowed_channel=MANAGE_CHANNEL_ID,
    on_command=on_command,
    logger=logger,
).handle
