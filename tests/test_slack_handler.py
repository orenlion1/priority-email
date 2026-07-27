"""Tests for the Slack events handler's command execution.

Exercises on_command directly (signature verification, which slackkit owns and
its own tests cover, is bypassed) against a fake S3, Secrets Manager, and Lambda
so no AWS or `age` binary is touched. Skipped without slackkit, like the poller
tests are not.
"""

import io
import os
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

try:
    import slackkit  # noqa: F401
    import boto3  # noqa: F401  (the handler imports it at module load)
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("slackkit/boto3 not installed (ship into the CI/Lambda env)")

# The handler reads configuration and creates boto3 clients at import; give it an
# environment and a region before importing it.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ["STATE_BUCKET"] = "priority-email-state-test"
os.environ["SLACK_SIGNING_SECRET_ARN"] = "arn:sig"
os.environ["RUNTIME_SECRET_ID"] = "priority-email/runtime"
os.environ["POLLER_FUNCTION_NAME"] = "priority-email-poller"
os.environ.pop("SLACK_BOT_TOKEN_ARN", None)
os.environ.pop("MANAGE_CHANNEL_ID", None)

from slack import slack_handler  # noqa: E402
from slack.filter_store import S3FilterStore, render_filter_file  # noqa: E402


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def get_object(self, Bucket, Key):
        if Key not in self.store:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.store[Key])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.store[Key] = Body if isinstance(Body, bytes) else Body.encode()
        return {}


class FakeSecrets:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_secret_value(self, SecretId):
        return {"SecretString": self.mapping[SecretId]}


class FakeLambda:
    def __init__(self):
        self.invocations = []

    def invoke(self, FunctionName, InvocationType):
        self.invocations.append((FunctionName, InvocationType))
        return {}


# A placeholder bot token the handler only forwards to a stubbed post_reply; kept
# clear of the real `xoxb-` shape so the secret scanner does not flag the fixture.
RUNTIME_ENV = "SLACK_BOT_TOKEN=test-bot-token\nEMAIL_POLL_ENABLED_PROVIDERS=gmail\n"


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.secrets = FakeSecrets(
            {"priority-email/runtime": RUNTIME_ENV, "arn:sig": "signing"}
        )
        self.lam = FakeLambda()
        self.replies = []

        slack_handler._s3 = self.s3
        slack_handler._secrets = self.secrets
        slack_handler._lambda = self.lam
        slack_handler._secret_cache.clear()
        slack_handler.post_reply = lambda token, channel, text, thread_ts, **kw: (
            self.replies.append((channel, text, thread_ts))
        )
        # A store that uses the fake S3 and never shells out to `age`.
        slack_handler._filter_store = lambda: S3FilterStore(
            s3=self.s3,
            bucket="priority-email-state-test",
            recipients_path="unused",
            encrypt=lambda plaintext: b"ENC:" + plaintext.encode(),
            now=lambda: "20260101T000000Z",
        )

    def _seed(self, kind, entries):
        self.s3.store[f"filters/{kind}-filters.txt"] = render_filter_file(entries).encode()

    def _run(self, text):
        slack_handler.on_command(text, "C123", "1700000000.000100", "U42")

    def _last_reply(self):
        return self.replies[-1][1]

    def test_help_replies_with_reference(self):
        self._run("help")
        self.assertIn("priority-email commands", self._last_reply())

    def test_parse_error_replies_with_usage(self):
        self._run("add example.com")
        self.assertIn("Unknown command", self._last_reply())

    def test_filter_add_writes_file_and_appends_op(self):
        self._run("filter add domain coralogix*.com")
        stored = self.s3.store["filters/domain-filters.txt"].decode()
        self.assertEqual(stored, "coralogix*.com\n")
        ops = [k for k in self.s3.store if k.startswith("filters/ops/")]
        self.assertEqual(len(ops), 1)
        self.assertIn("Added", self._last_reply())

    def test_filter_add_newest_first(self):
        self._seed("domain", ["old.com"])
        self._run("filter add domain new.com")
        self.assertEqual(
            self.s3.store["filters/domain-filters.txt"].decode(), "new.com\nold.com\n"
        )

    def test_duplicate_add_does_not_write_or_append_op(self):
        self._seed("domain", ["example.com"])
        self._run("filter add domain @example.com")
        # File unchanged, no op appended.
        self.assertEqual(
            self.s3.store["filters/domain-filters.txt"].decode(), "example.com\n"
        )
        self.assertFalse([k for k in self.s3.store if k.startswith("filters/ops/")])
        self.assertIn("already", self._last_reply())

    def test_filter_remove_writes_and_appends_op(self):
        self._seed("email-address", ["a@x.com", "b@x.com"])
        self._run("filter remove email-address a@x.com")
        self.assertEqual(
            self.s3.store["filters/email-address-filters.txt"].decode(), "b@x.com\n"
        )
        self.assertTrue([k for k in self.s3.store if k.startswith("filters/ops/")])

    def test_remove_absent_is_noop(self):
        self._run("filter remove domain missing.com")
        self.assertFalse([k for k in self.s3.store if k.startswith("filters/ops/")])
        self.assertIn("not a", self._last_reply())

    def test_provider_list_reads_enabled_set(self):
        self._run("provider list")
        reply = self._last_reply()
        self.assertIn("`gmail` — enabled", reply)
        self.assertIn("`yahoo` — disabled", reply)

    def test_poll_now_invokes_poller_async(self):
        self._run("poll now")
        self.assertEqual(self.lam.invocations, [("priority-email-poller", "Event")])
        self.assertIn("Started a poll", self._last_reply())


if __name__ == "__main__":
    unittest.main()
