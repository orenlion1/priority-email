#!/usr/bin/env python3
import argparse
import datetime as dt
import email.utils
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
METADATA_HEADERS = ["From", "Subject", "Date"]
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
SENSITIVE_QUERY_KEYS = {"access_token", "client_secret", "code", "key", "password", "token"}


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def require(values, key):
    value = values.get(key, "")
    if not value or value == "TODO":
        raise SystemExit(f"Missing required .env value: {key}")
    return value


def int_config(values, key, default):
    raw = values.get(key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{key} must be an integer.")


def bool_config(values, key, default):
    raw = values.get(key, "")
    if not raw:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SystemExit(f"{key} must be true or false.")


def truncate(value, limit=1200):
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def sanitize_url(url):
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe_query = [
        (key, "[redacted]" if key.lower() in SENSITIVE_QUERY_KEYS else value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(safe_query),
            parsed.fragment,
        )
    )


class EmailProviderRequestError(Exception):
    def __init__(self, *, method, url, status="", reason="", details=""):
        self.method = method
        self.url = sanitize_url(url)
        self.status = str(status) if status else ""
        self.reason = truncate(reason, 240)
        self.details = truncate(details, 1200)
        message_parts = [f"{self.method} {self.url}"]
        if self.status:
            message_parts.append(f"status={self.status}")
        if self.reason:
            message_parts.append(f"reason={self.reason}")
        super().__init__(" ".join(message_parts))

    def summary(self):
        return {
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "reason": self.reason,
            "details": self.details,
        }


def request_json(url, *, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors="replace")
        raise EmailProviderRequestError(
            method=method,
            url=url,
            status=exc.code,
            reason=exc.reason,
            details=details,
        ) from exc
    except urllib.error.URLError as exc:
        raise EmailProviderRequestError(method=method, url=url, reason=exc.reason) from exc
    except TimeoutError as exc:
        raise EmailProviderRequestError(method=method, url=url, reason="timeout") from exc
    except json.JSONDecodeError as exc:
        raise EmailProviderRequestError(
            method=method,
            url=url,
            reason="invalid_json",
            details=str(exc),
        ) from exc


def post_slack_message(token, channel, text):
    payload = json.dumps({"channel": channel, "text": text}).encode()
    req = urllib.request.Request(
        SLACK_POST_MESSAGE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        response = json.loads(resp.read().decode())
    if not response.get("ok"):
        raise RuntimeError(f"Slack post failed: {response.get('error', 'unknown_error')}")
    return response


def format_provider_error_message(provider_name, error):
    details = error.summary()
    lines = [
        f"Priority Email provider request failed: {provider_name}",
        f"method: {details['method']}",
        f"url: {details['url']}",
    ]
    if details["status"]:
        lines.append(f"status: {details['status']}")
    if details["reason"]:
        lines.append(f"reason: {details['reason']}")
    if details["details"]:
        lines.append(f"details: {details['details']}")
    return "\n".join(lines)


def notify_provider_error(values, provider_name, error):
    if not bool_config(values, "EMAIL_POLL_SLACK_ERROR_NOTIFICATIONS_ENABLED", True):
        print(f"{provider_name}: slack_error_notification=disabled")
        return False
    token = values.get("SLACK_BOT_TOKEN", "")
    channel = values.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        print(f"{provider_name}: slack_error_notification=skipped missing_slack_config")
        return False
    try:
        post_slack_message(token, channel, format_provider_error_message(provider_name, error))
    except Exception as exc:
        print(f"{provider_name}: slack_error_notification=failed {truncate(exc, 240)}")
        return False
    print(f"{provider_name}: slack_error_notification=posted")
    return True


def record_provider_error(provider_state, error):
    provider_state["last_polled_at"] = utc_now_iso()
    provider_state["last_error"] = error.summary()
    provider_state["last_error_at"] = provider_state["last_polled_at"]


def clear_provider_error(provider_state):
    provider_state.pop("last_error", None)
    provider_state.pop("last_error_at", None)


def load_state(path):
    if not path.exists():
        return {"providers": {}}
    with path.open() as f:
        return json.load(f)


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def utc_now_iso():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def epoch_to_query_date(epoch_seconds):
    return dt.datetime.fromtimestamp(epoch_seconds, dt.UTC).strftime("%Y/%m/%d")


def parse_email_date(value):
    parsed = email.utils.parsedate_to_datetime(value) if value else None
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0).isoformat()


class PollResult:
    def __init__(self, provider, initialized, checkpoint_before, checkpoint_after, messages):
        self.provider = provider
        self.initialized = initialized
        self.checkpoint_before = checkpoint_before
        self.checkpoint_after = checkpoint_after
        self.messages = messages


class BaseProviderPoller:
    name = ""

    def poll(self, values, provider_state):
        raise NotImplementedError


class GmailPoller(BaseProviderPoller):
    name = "gmail"

    def access_token(self, values):
        body = urllib.parse.urlencode(
            {
                "client_id": require(values, "GMAIL_CLIENT_ID"),
                "client_secret": require(values, "GMAIL_CLIENT_SECRET"),
                "refresh_token": require(values, "GMAIL_REFRESH_TOKENS"),
                "grant_type": "refresh_token",
            }
        ).encode()
        token = request_json(
            TOKEN_URL,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not token.get("access_token"):
            raise EmailProviderRequestError(
                method="POST",
                url=TOKEN_URL,
                reason="missing_access_token",
                details="Token response did not include access_token.",
            )
        return token["access_token"]

    def list_messages_page(self, headers, max_results, checkpoint, page_token=None):
        params = {"maxResults": max_results, "q": "in:anywhere"}
        if checkpoint:
            params["q"] = f"in:anywhere after:{epoch_to_query_date(checkpoint)}"
        if page_token:
            params["pageToken"] = page_token
        url = f"{GMAIL_API}/messages?{urllib.parse.urlencode(params)}"
        return request_json(url, headers=headers)

    def list_message_refs(self, headers, max_results, checkpoint, initialized):
        page = self.list_messages_page(headers, max_results, checkpoint)
        messages = list(page.get("messages", []))
        if initialized:
            return messages

        next_page_token = page.get("nextPageToken")
        while next_page_token:
            page = self.list_messages_page(
                headers, max_results, checkpoint, page_token=next_page_token
            )
            messages.extend(page.get("messages", []))
            next_page_token = page.get("nextPageToken")
        return messages

    def get_metadata(self, headers, message_id):
        url = (
            f"{GMAIL_API}/messages/{message_id}?"
            + urllib.parse.urlencode(
                [
                    ("format", "metadata"),
                    *[("metadataHeaders", header) for header in METADATA_HEADERS],
                ]
            )
        )
        message = request_json(url, headers=headers)
        header_values = {
            item.get("name", ""): item.get("value", "")
            for item in message.get("payload", {}).get("headers", [])
        }
        internal_epoch = int(message.get("internalDate", "0")) // 1000
        return {
            "id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
            "internal_epoch": internal_epoch,
            "internal_time": dt.datetime.fromtimestamp(internal_epoch, dt.UTC)
            .replace(microsecond=0)
            .isoformat(),
            "from": header_values.get("From", ""),
            "subject": header_values.get("Subject", ""),
            "date": parse_email_date(header_values.get("Date", "")),
        }

    def poll(self, values, provider_state):
        clear_provider_error(provider_state)
        checkpoint = provider_state.get("checkpoint_epoch")
        initialized = checkpoint is None
        max_results = int_config(
            values,
            "EMAIL_POLL_INITIAL_MAX_MESSAGES" if initialized else "EMAIL_POLL_MAX_MESSAGES",
            20 if initialized else 50,
        )
        token = self.access_token(values)
        headers = {"Authorization": f"Bearer {token}"}
        message_refs = self.list_message_refs(headers, max_results, checkpoint, initialized)
        messages = []
        max_epoch = checkpoint or 0

        for ref in message_refs:
            metadata = self.get_metadata(headers, ref["id"])
            if checkpoint is not None and metadata["internal_epoch"] <= checkpoint:
                continue
            messages.append(metadata)
            max_epoch = max(max_epoch, metadata["internal_epoch"])

        provider_state["checkpoint_epoch"] = max_epoch
        provider_state["checkpoint_time"] = (
            dt.datetime.fromtimestamp(max_epoch, dt.UTC).replace(microsecond=0).isoformat()
            if max_epoch
            else ""
        )
        provider_state["last_polled_at"] = utc_now_iso()
        provider_state["initialized"] = True
        return PollResult("gmail", initialized, checkpoint, max_epoch, messages)


class StubProviderPoller(BaseProviderPoller):
    def __init__(self, name):
        self.name = name

    def poll(self, values, provider_state):
        clear_provider_error(provider_state)
        provider_state["last_polled_at"] = utc_now_iso()
        provider_state["status"] = "not_implemented"
        return PollResult(
            self.name,
            provider_state.get("checkpoint_epoch") is None,
            provider_state.get("checkpoint_epoch"),
            provider_state.get("checkpoint_epoch"),
            [],
        )


PROVIDERS = {
    "gmail": GmailPoller(),
    "yahoo": StubProviderPoller("yahoo"),
    "icloud": StubProviderPoller("icloud"),
}


def enabled_providers(values, requested):
    if requested:
        return requested
    configured = values.get("EMAIL_POLL_ENABLED_PROVIDERS", "gmail")
    return [item.strip() for item in configured.split(",") if item.strip()]


def print_result(result, *, verbose=False):
    mode = "initialization" if result.initialized else "incremental"
    print(f"{result.provider}: {mode} poll")
    print(f"{result.provider}: checkpoint_before={result.checkpoint_before or 'none'}")
    print(f"{result.provider}: checkpoint_after={result.checkpoint_after or 'none'}")
    print(f"{result.provider}: messages={len(result.messages)}")
    if not verbose:
        return
    for message in result.messages:
        print(
            json.dumps(
                {
                    "id": message["id"],
                    "thread_id": message["thread_id"],
                    "internal_time": message["internal_time"],
                    "from": message["from"],
                    "subject": message["subject"],
                    "date": message["date"],
                },
                sort_keys=True,
            )
        )


def main():
    parser = argparse.ArgumentParser(description="Poll configured email providers.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--state-file", type=Path, default=None)
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(PROVIDERS.keys()),
        help="Provider to poll. May be repeated. Defaults to EMAIL_POLL_ENABLED_PROVIDERS.",
    )
    parser.add_argument(
        "--reset-provider-state",
        action="store_true",
        help="Forget checkpoints for selected providers before polling.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print message metadata. By default only counts and checkpoints are printed.",
    )
    args = parser.parse_args()

    values = load_env(args.env_file)
    state_file = args.state_file or Path(
        values.get("EMAIL_POLL_STATE_FILE", ".state/email-poller-state.json")
    )
    state = load_state(state_file)
    provider_state = state.setdefault("providers", {})

    for provider_name in enabled_providers(values, args.provider):
        poller = PROVIDERS.get(provider_name)
        if poller is None:
            raise SystemExit(f"Unknown provider: {provider_name}")
        if args.reset_provider_state:
            provider_state[provider_name] = {}
        current = provider_state.setdefault(provider_name, {})
        try:
            result = poller.poll(values, current)
        except EmailProviderRequestError as exc:
            record_provider_error(current, exc)
            print(f"{provider_name}: provider_request_error={exc}")
            notify_provider_error(values, provider_name, exc)
            continue
        print_result(result, verbose=args.verbose)

    save_state(state_file, state)
    print(f"state_file={state_file}")


if __name__ == "__main__":
    main()
