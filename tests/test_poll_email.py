import importlib.util
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
