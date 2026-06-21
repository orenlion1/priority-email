import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "poll-email.py"
spec = importlib.util.spec_from_file_location("poll_email", MODULE_PATH)
poll_email = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poll_email)


class FakeGmailPoller(poll_email.GmailPoller):
    def __init__(self, pages, metadata):
        self.pages = pages
        self.metadata = metadata
        self.page_calls = []

    def access_token(self, values):
        return "fake-token"

    def list_messages_page(self, headers, max_results, checkpoint, page_token=None):
        self.page_calls.append(
            {
                "max_results": max_results,
                "checkpoint": checkpoint,
                "page_token": page_token,
            }
        )
        return self.pages.get(page_token)

    def get_metadata(self, headers, message_id):
        return self.metadata[message_id]


def message(message_id, epoch):
    return {
        "id": message_id,
        "thread_id": f"thread-{message_id}",
        "internal_epoch": epoch,
        "internal_time": f"epoch-{epoch}",
        "from": "sender@example.com",
        "subject": f"subject {message_id}",
        "date": "",
    }


class FailingPoller(poll_email.BaseProviderPoller):
    name = "failing"

    def poll(self, values, provider_state):
        raise poll_email.EmailProviderRequestError(
            method="GET",
            url="https://mail.example.test/messages?access_token=secret-token&page=1",
            status=503,
            reason="provider_unavailable",
            details='{"error":"temporarily unavailable"}',
        )


class GmailPollerTests(unittest.TestCase):
    def test_initial_poll_inspects_only_first_page_with_configured_limit(self):
        poller = FakeGmailPoller(
            pages={
                None: {
                    "messages": [{"id": "newest"}, {"id": "older"}],
                    "nextPageToken": "next-page",
                },
                "next-page": {"messages": [{"id": "should-not-read"}]},
            },
            metadata={
                "newest": message("newest", 300),
                "older": message("older", 200),
                "should-not-read": message("should-not-read", 100),
            },
        )

        state = {}
        result = poller.poll({"EMAIL_POLL_INITIAL_MAX_MESSAGES": "20"}, state)

        self.assertTrue(result.initialized)
        self.assertEqual(["newest", "older"], [item["id"] for item in result.messages])
        self.assertEqual(300, state["checkpoint_epoch"])
        self.assertEqual(
            [{"max_results": 20, "checkpoint": None, "page_token": None}],
            poller.page_calls,
        )

    def test_incremental_poll_pages_all_messages_newer_than_checkpoint(self):
        poller = FakeGmailPoller(
            pages={
                None: {
                    "messages": [{"id": "newest"}, {"id": "middle"}],
                    "nextPageToken": "next-page",
                },
                "next-page": {
                    "messages": [{"id": "old-new"}, {"id": "already-seen"}],
                },
            },
            metadata={
                "newest": message("newest", 400),
                "middle": message("middle", 300),
                "old-new": message("old-new", 200),
                "already-seen": message("already-seen", 100),
            },
        )

        state = {"checkpoint_epoch": 150}
        result = poller.poll({"EMAIL_POLL_MAX_MESSAGES": "2"}, state)

        self.assertFalse(result.initialized)
        self.assertEqual(["newest", "middle", "old-new"], [item["id"] for item in result.messages])
        self.assertEqual(400, state["checkpoint_epoch"])
        self.assertEqual(
            [
                {"max_results": 2, "checkpoint": 150, "page_token": None},
                {"max_results": 2, "checkpoint": 150, "page_token": "next-page"},
            ],
            poller.page_calls,
        )

    def test_provider_request_error_posts_to_slack_and_saves_error_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            state_file = Path(tmpdir) / "state.json"
            env_file.write_text(
                "\n".join(
                    [
                        "SLACK_BOT_TOKEN=slack-test-token",
                        "SLACK_CHANNEL_ID=C123",
                        f"EMAIL_POLL_STATE_FILE={state_file}",
                    ]
                )
                + "\n"
            )
            posted = []

            def fake_post(token, channel, text):
                posted.append({"token": token, "channel": channel, "text": text})
                return {"ok": True}

            original = dict(poll_email.PROVIDERS)
            poll_email.PROVIDERS["failing"] = FailingPoller()
            try:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "poll-email.py",
                        "--env-file",
                        str(env_file),
                        "--provider",
                        "failing",
                    ],
                ), mock.patch.object(poll_email, "post_slack_message", fake_post):
                    poll_email.main()
            finally:
                poll_email.PROVIDERS.clear()
                poll_email.PROVIDERS.update(original)

            self.assertEqual(1, len(posted))
            self.assertEqual("slack-test-token", posted[0]["token"])
            self.assertEqual("C123", posted[0]["channel"])
            self.assertIn("Priority Email provider request failed: failing", posted[0]["text"])
            self.assertIn("status: 503", posted[0]["text"])
            self.assertIn("access_token=%5Bredacted%5D", posted[0]["text"])
            self.assertNotIn("secret-token", posted[0]["text"])

            state = json.loads(state_file.read_text())
            error = state["providers"]["failing"]["last_error"]
            self.assertEqual("503", error["status"])
            self.assertEqual("provider_unavailable", error["reason"])
            self.assertIn("access_token=%5Bredacted%5D", error["url"])
            self.assertNotIn("secret-token", error["url"])

    def test_slack_error_notifications_can_be_disabled(self):
        error = poll_email.EmailProviderRequestError(
            method="GET",
            url="https://mail.example.test/messages",
            status=429,
            reason="rate_limited",
        )
        with mock.patch.object(poll_email, "post_slack_message") as post:
            posted = poll_email.notify_provider_error(
                {
                    "EMAIL_POLL_SLACK_ERROR_NOTIFICATIONS_ENABLED": "false",
                    "SLACK_BOT_TOKEN": "slack-test-token",
                    "SLACK_CHANNEL_ID": "C123",
                },
                "gmail",
                error,
            )
        self.assertFalse(posted)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
