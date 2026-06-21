import contextlib
import importlib.util
import io
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

    def access_token(self, values, telemetry=None):
        return "fake-token"

    def list_messages_page(
        self, headers, max_results, checkpoint, page_token=None, telemetry=None
    ):
        self.page_calls.append(
            {
                "max_results": max_results,
                "checkpoint": checkpoint,
                "page_token": page_token,
            }
        )
        return self.pages.get(page_token)

    def get_metadata(self, headers, message_id, telemetry=None):
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

    def poll(self, values, provider_state, telemetry=None):
        raise poll_email.EmailProviderRequestError(
            method="GET",
            url="https://mail.example.test/messages?access_token=secret-token&page=1",
            status=503,
            reason="provider_unavailable",
            details='{"error":"temporarily unavailable"}',
        )


class SuccessfulPoller(poll_email.BaseProviderPoller):
    name = "successful"

    def poll(self, values, provider_state, telemetry=None):
        provider_state["checkpoint_epoch"] = 123
        provider_state["last_polled_at"] = poll_email.utc_now_iso()
        return poll_email.PollResult(
            "successful",
            True,
            None,
            123,
            [message("new-message", 123)],
        )


class FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b"{}"


class FakeYahooConnection:
    def __init__(self, uids, metadata):
        self.uids = uids
        self.metadata = metadata
        self.search_calls = []
        self.fetch_calls = []
        self.logged_out = False

    def uid(self, command, *args):
        if command == "SEARCH":
            criterion = args[-1]
            self.search_calls.append(criterion)
            if criterion == "ALL":
                selected = self.uids
            else:
                start = int(criterion.split()[1].split(":", 1)[0])
                selected = [uid for uid in self.uids if uid >= start]
            return "OK", [" ".join(str(uid) for uid in selected).encode()]
        if command == "FETCH":
            uid = int(args[0])
            self.fetch_calls.append(uid)
            item = self.metadata[uid]
            payload = (
                f"From: {item['from']}\r\n"
                f"Subject: {item['subject']}\r\n"
                f"Date: {item['date']}\r\n"
                "\r\n"
            ).encode()
            prefix = f'1 (UID {uid} INTERNALDATE "{item["internaldate"]}"'.encode()
            return "OK", [(prefix, payload)]
        raise AssertionError(f"unexpected IMAP command: {command}")

    def logout(self):
        self.logged_out = True


class FakeYahooPoller(poll_email.YahooPoller):
    def __init__(self, conn):
        self.conn = conn

    def access_token(self, values, provider_state, telemetry=None):
        provider_state["refresh_token"] = "rotated-refresh-token"
        return "fake-yahoo-token"

    def mailbox_email(self, values, access_token="", telemetry=None):
        return "user@yahoo.example"

    def connect(self, values, email_address, credential, auth_method):
        return self.conn


class GmailPollerTests(unittest.TestCase):
    def test_main_emits_structured_logs_with_priority_email_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            state_file = Path(tmpdir) / "state.json"
            poll_log_file = Path(tmpdir) / "poll.log"
            env_file.write_text(
                f"EMAIL_POLL_STATE_FILE={state_file}\n"
                f"EMAIL_POLL_LOG_FILE={poll_log_file}\n"
            )
            stdout = io.StringIO()

            original = dict(poll_email.PROVIDERS)
            poll_email.PROVIDERS["successful"] = SuccessfulPoller()
            try:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "poll-email.py",
                        "--env-file",
                        str(env_file),
                        "--provider",
                        "successful",
                    ],
                ), contextlib.redirect_stdout(stdout):
                    poll_email.main()
            finally:
                poll_email.PROVIDERS.clear()
                poll_email.PROVIDERS.update(original)

            records = [
                json.loads(line)
                for line in stdout.getvalue().splitlines()
                if line.strip().startswith("{")
            ]
            self.assertTrue(records)
            self.assertTrue(
                all(record["service"] == "priority-email-service" for record in records)
            )
            self.assertIn("poll_result", {record["event"] for record in records})
            poll_log_records = [
                json.loads(line) for line in poll_log_file.read_text().splitlines()
            ]
            self.assertEqual(1, len(poll_log_records))
            self.assertEqual("provider_poll", poll_log_records[0]["event"])
            self.assertEqual("INFO", poll_log_records[0]["level"])
            self.assertEqual("successful", poll_log_records[0]["provider"])
            self.assertEqual("ok", poll_log_records[0]["status"])

    def test_error_log_level_suppresses_success_stdout_but_keeps_poll_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            state_file = Path(tmpdir) / "state.json"
            poll_log_file = Path(tmpdir) / "poll.log"
            env_file.write_text(
                "\n".join(
                    [
                        "EMAIL_LOG_LEVEL=ERROR",
                        f"EMAIL_POLL_STATE_FILE={state_file}",
                        f"EMAIL_POLL_LOG_FILE={poll_log_file}",
                    ]
                )
                + "\n"
            )
            stdout = io.StringIO()

            original = dict(poll_email.PROVIDERS)
            poll_email.PROVIDERS["successful"] = SuccessfulPoller()
            try:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "poll-email.py",
                        "--env-file",
                        str(env_file),
                        "--provider",
                        "successful",
                    ],
                ), contextlib.redirect_stdout(stdout):
                    poll_email.main()
            finally:
                poll_email.PROVIDERS.clear()
                poll_email.PROVIDERS.update(original)

            self.assertEqual("", stdout.getvalue())
            poll_log_records = [
                json.loads(line) for line in poll_log_file.read_text().splitlines()
            ]
            self.assertEqual("INFO", poll_log_records[0]["level"])
            self.assertEqual("ok", poll_log_records[0]["status"])

    def test_otel_export_posts_trace_and_metric_payloads(self):
        telemetry = poll_email.Telemetry(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy.example.test:4318",
                "OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS": "1",
            }
        )
        posted = []

        def fake_urlopen(req, timeout):
            posted.append({"url": req.full_url, "body": json.loads(req.data.decode())})
            return FakeHttpResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            span = telemetry.start_span("email_provider_poll", provider="gmail")
            telemetry.end_span(span, status="ok")
            telemetry.count("priority_email_poll_cycles_total", provider="gmail", status="ok")
            telemetry.flush_metrics()

        self.assertEqual(
            [
                "http://alloy.example.test:4318/v1/traces",
                "http://alloy.example.test:4318/v1/metrics",
            ],
            [item["url"] for item in posted],
        )
        self.assertEqual(
            "priority-email-service",
            posted[0]["body"]["resourceSpans"][0]["resource"]["attributes"][0]["value"][
                "stringValue"
            ],
        )

    def test_provider_request_metrics_include_provider_operation_and_outcome(self):
        telemetry = poll_email.Telemetry({})

        with mock.patch.object(poll_email, "request_json", return_value={"ok": True}):
            result = poll_email.metered_provider_request(
                telemetry,
                provider="gmail",
                operation="list_messages",
                url="https://mail.example.test/messages",
            )

        self.assertEqual({"ok": True}, result)
        metric_names = [item[1] for item in telemetry.metrics]
        self.assertIn("priority_email_provider_requests_total", metric_names)
        self.assertIn("priority_email_provider_request_duration_ms", metric_names)
        request_metric = [
            item
            for item in telemetry.metrics
            if item[1] == "priority_email_provider_requests_total"
        ][0]
        self.assertEqual(
            {
                "provider": "gmail",
                "operation": "list_messages",
                "method": "GET",
                "outcome": "ok",
                "status": "ok",
                "reason": "none",
            },
            request_metric[3],
        )

    def test_provider_request_error_metrics_include_provider_and_reason(self):
        telemetry = poll_email.Telemetry({})
        error = poll_email.EmailProviderRequestError(
            method="GET",
            url="https://mail.example.test/messages?access_token=secret-token",
            status=503,
            reason="provider_unavailable",
        )

        with mock.patch.object(poll_email, "request_json", side_effect=error):
            with self.assertRaises(poll_email.EmailProviderRequestError):
                poll_email.metered_provider_request(
                    telemetry,
                    provider="gmail",
                    operation="list_messages",
                    url="https://mail.example.test/messages?access_token=secret-token",
                )

        metric_names = [item[1] for item in telemetry.metrics]
        self.assertIn("priority_email_provider_requests_total", metric_names)
        self.assertIn("priority_email_provider_request_errors_total", metric_names)
        self.assertIn("priority_email_provider_request_duration_ms", metric_names)
        error_metric = [
            item
            for item in telemetry.metrics
            if item[1] == "priority_email_provider_request_errors_total"
        ][0]
        self.assertEqual("gmail", error_metric[3]["provider"])
        self.assertEqual("list_messages", error_metric[3]["operation"])
        self.assertEqual("error", error_metric[3]["outcome"])
        self.assertEqual("503", error_metric[3]["status"])
        self.assertEqual("provider_unavailable", error_metric[3]["reason"])

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
            poll_log_file = Path(tmpdir) / "poll.log"
            env_file.write_text(
                "\n".join(
                    [
                        "SLACK_BOT_TOKEN=slack-test-token",
                        "SLACK_CHANNEL_ID=C123",
                        f"EMAIL_POLL_STATE_FILE={state_file}",
                        f"EMAIL_POLL_LOG_FILE={poll_log_file}",
                    ]
                )
                + "\n"
            )
            posted = []
            stdout = io.StringIO()

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
                ), mock.patch.object(
                    poll_email, "post_slack_message", fake_post
                ), contextlib.redirect_stdout(stdout):
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
            poll_log_records = [
                json.loads(line) for line in poll_log_file.read_text().splitlines()
            ]
            self.assertEqual(1, len(poll_log_records))
            self.assertEqual("provider_poll", poll_log_records[0]["event"])
            self.assertEqual("ERROR", poll_log_records[0]["level"])
            self.assertEqual("failing", poll_log_records[0]["provider"])
            self.assertEqual("error", poll_log_records[0]["status"])
            self.assertIn("access_token=%5Bredacted%5D", poll_log_records[0]["error"]["url"])
            self.assertNotIn("secret-token", json.dumps(poll_log_records[0]))
            stdout_records = [
                json.loads(line)
                for line in stdout.getvalue().splitlines()
                if line.strip().startswith("{")
            ]
            error_records = [
                record for record in stdout_records if record["event"] == "provider_poll_failed"
            ]
            self.assertEqual(1, len(error_records))
            self.assertEqual("error", error_records[0]["level"])
            self.assertEqual("failing", error_records[0]["provider"])
            self.assertIn("duration_ms", error_records[0])
            self.assertIn("provider_state", error_records[0])
            self.assertTrue(error_records[0]["slack_error_notification_posted"])
            self.assertNotIn("secret-token", json.dumps(error_records[0]))

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


class YahooPollerTests(unittest.TestCase):
    def test_initial_poll_inspects_latest_configured_uids(self):
        conn = FakeYahooConnection(
            [101, 102, 103],
            {
                101: {
                    "from": "old@example.com",
                    "subject": "old",
                    "date": "Mon, 01 Jun 2026 10:00:00 +0000",
                    "internaldate": "01-Jun-2026 10:00:00 +0000",
                },
                102: {
                    "from": "middle@example.com",
                    "subject": "middle",
                    "date": "Mon, 01 Jun 2026 11:00:00 +0000",
                    "internaldate": "01-Jun-2026 11:00:00 +0000",
                },
                103: {
                    "from": "new@example.com",
                    "subject": "new",
                    "date": "Mon, 01 Jun 2026 12:00:00 +0000",
                    "internaldate": "01-Jun-2026 12:00:00 +0000",
                },
            },
        )
        state = {}

        result = FakeYahooPoller(conn).poll({"EMAIL_POLL_INITIAL_MAX_MESSAGES": "2"}, state)

        self.assertTrue(result.initialized)
        self.assertEqual([102, 103], conn.fetch_calls)
        self.assertEqual("ALL", conn.search_calls[0])
        self.assertEqual(103, state["checkpoint_uid"])
        self.assertEqual("user@yahoo.example", state["mailbox"])
        self.assertEqual(["102", "103"], [item["id"] for item in result.messages])
        self.assertTrue(conn.logged_out)

    def test_app_password_path_does_not_request_oauth_token(self):
        conn = FakeYahooConnection(
            [201],
            {
                201: {
                    "from": "new@example.com",
                    "subject": "new",
                    "date": "Mon, 01 Jun 2026 12:00:00 +0000",
                    "internaldate": "01-Jun-2026 12:00:00 +0000",
                },
            },
        )
        poller = FakeYahooPoller(conn)
        with mock.patch.object(poller, "access_token") as access_token:
            result = poller.poll(
                {
                    "YAHOO_EMAIL": "user@yahoo.example",
                    "YAHOO_APP_PASSWORD": "test-app-password",
                },
                {},
            )

        access_token.assert_not_called()
        self.assertEqual(["201"], [item["id"] for item in result.messages])

    def test_incremental_poll_uses_uid_checkpoint(self):
        conn = FakeYahooConnection(
            [101, 102, 103, 104],
            {
                103: {
                    "from": "new@example.com",
                    "subject": "new",
                    "date": "Mon, 01 Jun 2026 12:00:00 +0000",
                    "internaldate": "01-Jun-2026 12:00:00 +0000",
                },
                104: {
                    "from": "newer@example.com",
                    "subject": "newer",
                    "date": "Mon, 01 Jun 2026 13:00:00 +0000",
                    "internaldate": "01-Jun-2026 13:00:00 +0000",
                },
            },
        )
        state = {"checkpoint_uid": 102, "checkpoint_epoch": 100}

        result = FakeYahooPoller(conn).poll({"EMAIL_POLL_MAX_MESSAGES": "1"}, state)

        self.assertFalse(result.initialized)
        self.assertEqual("UID 103:*", conn.search_calls[0])
        self.assertEqual([103, 104], conn.fetch_calls)
        self.assertEqual(104, state["checkpoint_uid"])
        self.assertEqual(["103", "104"], [item["id"] for item in result.messages])


if __name__ == "__main__":
    unittest.main()
