#!/usr/bin/env python3
import argparse
import datetime as dt
import email.utils
import imaplib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import Telemetry


GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"
METADATA_HEADERS = ["From", "Subject", "Date"]
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
SENSITIVE_QUERY_KEYS = {"access_token", "client_secret", "code", "key", "password", "token"}
FILTER_FILE_NAMES = {
    "domain": "domain-filters.txt",
    "email_address": "email-address-filters.txt",
    "sender_name": "sender-name-filters.txt",
}


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


def normalize_filter_line(value):
    return " ".join(str(value).strip().split())


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


def record_external_dependency_request_metrics(
    telemetry,
    *,
    dependency,
    operation,
    method,
    outcome,
    duration_ms,
    status="ok",
    reason="none",
):
    if telemetry is None:
        return
    labels = {
        "dependency": dependency,
        "operation": operation,
        "method": method,
        "outcome": outcome,
        "status": status or "unknown",
        "reason": reason or "none",
    }
    telemetry.count("priority_email_external_dependency_requests_total", **labels)
    telemetry.gauge(
        "priority_email_external_dependency_request_duration_ms", duration_ms, **labels
    )
    if outcome != "ok":
        telemetry.count("priority_email_external_dependency_request_errors_total", **labels)


def record_provider_request_metrics(
    telemetry,
    *,
    provider,
    operation,
    method,
    outcome,
    duration_ms,
    status="ok",
    reason="none",
):
    if telemetry is None:
        return
    record_external_dependency_request_metrics(
        telemetry,
        dependency=provider,
        operation=operation,
        method=method,
        outcome=outcome,
        duration_ms=duration_ms,
        status=status,
        reason=reason,
    )
    labels = {
        "provider": provider,
        "operation": operation,
        "method": method,
        "outcome": outcome,
        "status": status or "unknown",
        "reason": reason or "none",
    }
    telemetry.count("priority_email_provider_requests_total", **labels)
    telemetry.gauge("priority_email_provider_request_duration_ms", duration_ms, **labels)
    if outcome != "ok":
        telemetry.count("priority_email_provider_request_errors_total", **labels)


def metered_provider_request(
    telemetry,
    *,
    provider,
    operation,
    url,
    method="GET",
    data=None,
    headers=None,
):
    started = dt.datetime.now(dt.UTC)
    try:
        result = request_json(url, method=method, data=data, headers=headers)
    except EmailProviderRequestError as exc:
        duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
        record_provider_request_metrics(
            telemetry,
            provider=provider,
            operation=operation,
            method=method,
            outcome="error",
            duration_ms=duration_ms,
            status=exc.status or "unknown",
            reason=exc.reason or "unknown",
        )
        raise
    duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
    record_provider_request_metrics(
        telemetry,
        provider=provider,
        operation=operation,
        method=method,
        outcome="ok",
        duration_ms=duration_ms,
    )
    return result


def metered_imap_operation(telemetry, *, provider, operation, action):
    started = dt.datetime.now(dt.UTC)
    try:
        result = action()
    except EmailProviderRequestError as exc:
        duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
        record_provider_request_metrics(
            telemetry,
            provider=provider,
            operation=operation,
            method="IMAP",
            outcome="error",
            duration_ms=duration_ms,
            status=exc.status or "unknown",
            reason=exc.reason or "unknown",
        )
        raise
    duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
    record_provider_request_metrics(
        telemetry,
        provider=provider,
        operation=operation,
        method="IMAP",
        outcome="ok",
        duration_ms=duration_ms,
    )
    return result


def post_slack_message(token, channel, text, telemetry=None):
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
    started = dt.datetime.now(dt.UTC)
    outcome = "ok"
    status = "ok"
    reason = "none"
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read().decode())
        if not response.get("ok"):
            outcome = "error"
            status = "slack_error"
            reason = truncate(response.get("error", "unknown_error"), 120)
            raise RuntimeError(f"Slack post failed: {reason}")
    except urllib.error.HTTPError as exc:
        outcome = "error"
        status = str(exc.code)
        reason = truncate(exc.reason or "http_error", 120)
        details = truncate(exc.read().decode(errors="replace"), 240)
        if details:
            raise RuntimeError(f"Slack post HTTP failed: status={status} reason={reason}") from exc
        raise RuntimeError(f"Slack post HTTP failed: status={status} reason={reason}") from exc
    except urllib.error.URLError as exc:
        outcome = "error"
        status = "unknown"
        reason = truncate(exc.reason or type(exc).__name__, 120)
        raise RuntimeError(f"Slack post failed: reason={reason}") from exc
    except TimeoutError as exc:
        outcome = "error"
        status = "unknown"
        reason = "timeout"
        raise RuntimeError("Slack post failed: reason=timeout") from exc
    except json.JSONDecodeError as exc:
        outcome = "error"
        status = "unknown"
        reason = "invalid_json"
        raise RuntimeError("Slack post failed: reason=invalid_json") from exc
    finally:
        duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
        record_external_dependency_request_metrics(
            telemetry,
            dependency="slack",
            operation="chat_post_message",
            method="POST",
            outcome=outcome,
            duration_ms=duration_ms,
            status=status,
            reason=reason,
        )
    return response


def load_filter_values(path, *, normalize=lambda value: value.lower()):
    if not path.exists():
        return []
    values = []
    seen = set()
    for raw in path.read_text().splitlines():
        item = normalize_filter_line(raw)
        if not item or item.startswith("#"):
            continue
        item = normalize(item)
        if not item or item in seen:
            continue
        values.append(item)
        seen.add(item)
    return values


def normalize_domain_filter(value):
    return normalize_filter_line(value).lower().removeprefix("@")


def load_sender_filters(values):
    filter_dir = Path(values.get("EMAIL_FILTER_DIR", "filters"))
    return {
        "domain": load_filter_values(
            filter_dir / FILTER_FILE_NAMES["domain"],
            normalize=normalize_domain_filter,
        ),
        "email_address": load_filter_values(
            filter_dir / FILTER_FILE_NAMES["email_address"],
            normalize=lambda value: normalize_filter_line(value).lower(),
        ),
        "sender_name": load_filter_values(
            filter_dir / FILTER_FILE_NAMES["sender_name"],
            normalize=lambda value: normalize_filter_line(value).lower(),
        ),
    }


def parse_sender(from_header):
    display_name, address = email.utils.parseaddr(from_header or "")
    display_name = normalize_filter_line(display_name)
    address = normalize_filter_line(address or from_header).lower()
    if not display_name and address and "@" not in address:
        display_name = normalize_filter_line(from_header)
        address = ""
    domain = address.rsplit("@", 1)[1] if "@" in address else ""
    return display_name, address, domain


def matching_filters(message, filters):
    display_name, address, domain = parse_sender(message.get("from", ""))
    display_name_key = display_name.lower()
    matches = []
    if domain:
        for value in filters.get("domain", []):
            if domain == value:
                matches.append({"type": "domain", "value": value})
    if address:
        for value in filters.get("email_address", []):
            if address == value:
                matches.append({"type": "email_address", "value": value})
    if display_name_key:
        for value in filters.get("sender_name", []):
            if display_name_key == value:
                matches.append({"type": "sender_name", "value": value})
    return matches


def provider_message_link(provider, message):
    if provider == "gmail" and message.get("thread_id"):
        return f"https://mail.google.com/mail/u/0/#all/{urllib.parse.quote(message['thread_id'])}"
    return ""


def format_filter_match(match):
    if match["type"] == "domain":
        return f"domain:{match['value']}"
    if match["type"] == "email_address":
        return f"email:{match['value']}"
    return f"sender:{match['value']}"


def format_matched_email_message(provider, message, matches):
    display_name, address, _domain = parse_sender(message.get("from", ""))
    sender = display_name
    if address and display_name:
        sender = f"{display_name} <{address}>"
    elif address:
        sender = address
    link = provider_message_link(provider, message)
    lines = [
        "Priority Email match",
        f"provider: {provider}",
        f"sender: {sender or 'unknown'}",
        f"subject: {truncate(message.get('subject', '(no subject)'), 240)}",
        f"received: {message.get('internal_time') or message.get('date') or 'unknown'}",
        "matched: " + ", ".join(format_filter_match(match) for match in matches),
    ]
    if link:
        lines.append(f"link: {link}")
    else:
        lines.append(f"message_id: {message.get('id', 'unknown')}")
    return "\n".join(lines)


def message_notification_key(provider, message):
    return f"{provider}:{message.get('id', '')}"


def trim_notified_message_keys(provider_state, limit):
    keys = provider_state.get("notified_message_keys", [])
    if len(keys) > limit:
        provider_state["notified_message_keys"] = keys[-limit:]


def notify_matched_messages(values, provider_state, result, filters, telemetry=None):
    if result.initialized and not bool_config(values, "EMAIL_NOTIFY_ON_INITIALIZATION", False):
        if telemetry:
            telemetry.count(
                "priority_email_matched_messages_total",
                0,
                provider=result.provider,
                result="skipped_initialization",
            )
        return {"matched": 0, "posted": 0, "skipped": len(result.messages), "failed": 0}
    if not bool_config(values, "EMAIL_POLL_SLACK_SUMMARIES_ENABLED", True):
        return {"matched": 0, "posted": 0, "skipped": 0, "failed": 0}
    token = values.get("SLACK_BOT_TOKEN", "")
    channel = values.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        if telemetry:
            telemetry.log(
                "warning",
                "matched_email_slack_skipped",
                provider=result.provider,
                reason="missing_slack_config",
            )
        return {"matched": 0, "posted": 0, "skipped": 0, "failed": 0}

    notified = provider_state.setdefault("notified_message_keys", [])
    notified_set = set(notified)
    history_limit = int_config(values, "EMAIL_NOTIFIED_MESSAGE_HISTORY_LIMIT", 1000)
    counts = {"matched": 0, "posted": 0, "skipped": 0, "failed": 0}

    for message in result.messages:
        matches = matching_filters(message, filters)
        if not matches:
            continue
        counts["matched"] += 1
        key = message_notification_key(result.provider, message)
        if key in notified_set:
            counts["skipped"] += 1
            continue
        try:
            post_slack_message(
                token,
                channel,
                format_matched_email_message(result.provider, message, matches),
                telemetry=telemetry,
            )
        except Exception as exc:
            counts["failed"] += 1
            if telemetry:
                telemetry.log(
                    "error",
                    "matched_email_slack_failed",
                    provider=result.provider,
                    message_id=message.get("id", ""),
                    reason=truncate(exc, 240),
                )
            continue
        notified.append(key)
        notified_set.add(key)
        counts["posted"] += 1
        if telemetry:
            telemetry.log(
                "info",
                "matched_email_slack_posted",
                provider=result.provider,
                message_id=message.get("id", ""),
                match_count=len(matches),
            )

    trim_notified_message_keys(provider_state, history_limit)
    if telemetry:
        for status, count in (
            ("matched", counts["matched"]),
            ("posted", counts["posted"]),
            ("skipped", counts["skipped"]),
            ("failed", counts["failed"]),
        ):
            telemetry.count(
                "priority_email_matched_messages_total",
                count,
                provider=result.provider,
                result=status,
            )
    return counts


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


def notify_provider_error(values, provider_name, error, telemetry=None):
    if not bool_config(values, "EMAIL_POLL_SLACK_ERROR_NOTIFICATIONS_ENABLED", True):
        if telemetry:
            telemetry.log(
                "info",
                "slack_error_notification_skipped",
                provider=provider_name,
                reason="disabled",
            )
        else:
            print(f"{provider_name}: slack_error_notification=disabled")
        return False
    token = values.get("SLACK_BOT_TOKEN", "")
    channel = values.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        if telemetry:
            telemetry.log(
                "warning",
                "slack_error_notification_skipped",
                provider=provider_name,
                reason="missing_slack_config",
            )
        else:
            print(f"{provider_name}: slack_error_notification=skipped missing_slack_config")
        return False
    try:
        post_slack_message(
            token,
            channel,
            format_provider_error_message(provider_name, error),
            telemetry=telemetry,
        )
    except Exception as exc:
        if telemetry:
            telemetry.log(
                "error",
                "slack_error_notification_failed",
                provider=provider_name,
                reason=truncate(exc, 240),
            )
        else:
            print(f"{provider_name}: slack_error_notification=failed {truncate(exc, 240)}")
        return False
    if telemetry:
        telemetry.log("info", "slack_error_notification_posted", provider=provider_name)
    else:
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


def parse_imap_internaldate(value):
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    parsed = email.utils.parsedate_to_datetime(value) if value else None
    if parsed is None:
        return 0, ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    parsed = parsed.astimezone(dt.UTC).replace(microsecond=0)
    return int(parsed.timestamp()), parsed.isoformat()


class PollResult:
    def __init__(self, provider, initialized, checkpoint_before, checkpoint_after, messages):
        self.provider = provider
        self.initialized = initialized
        self.checkpoint_before = checkpoint_before
        self.checkpoint_after = checkpoint_after
        self.messages = messages


class BaseProviderPoller:
    name = ""

    def poll(self, values, provider_state, telemetry=None):
        raise NotImplementedError


class GmailPoller(BaseProviderPoller):
    name = "gmail"

    def access_token(self, values, telemetry=None):
        body = urllib.parse.urlencode(
            {
                "client_id": require(values, "GMAIL_CLIENT_ID"),
                "client_secret": require(values, "GMAIL_CLIENT_SECRET"),
                "refresh_token": require(values, "GMAIL_REFRESH_TOKENS"),
                "grant_type": "refresh_token",
            }
        ).encode()
        token = metered_provider_request(
            telemetry,
            provider=self.name,
            operation="oauth_token",
            url=GMAIL_TOKEN_URL,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not token.get("access_token"):
            raise EmailProviderRequestError(
                method="POST",
                url=GMAIL_TOKEN_URL,
                reason="missing_access_token",
                details="Token response did not include access_token.",
            )
        return token["access_token"]

    def list_messages_page(
        self, headers, max_results, checkpoint, page_token=None, telemetry=None
    ):
        params = {"maxResults": max_results, "q": "in:anywhere"}
        if checkpoint:
            params["q"] = f"in:anywhere after:{epoch_to_query_date(checkpoint)}"
        if page_token:
            params["pageToken"] = page_token
        url = f"{GMAIL_API}/messages?{urllib.parse.urlencode(params)}"
        return metered_provider_request(
            telemetry,
            provider=self.name,
            operation="list_messages",
            url=url,
            headers=headers,
        )

    def list_message_refs(self, headers, max_results, checkpoint, initialized, telemetry=None):
        page = self.list_messages_page(
            headers, max_results, checkpoint, telemetry=telemetry
        )
        messages = list(page.get("messages", []))
        if initialized:
            return messages

        next_page_token = page.get("nextPageToken")
        while next_page_token:
            page = self.list_messages_page(
                headers,
                max_results,
                checkpoint,
                page_token=next_page_token,
                telemetry=telemetry,
            )
            messages.extend(page.get("messages", []))
            next_page_token = page.get("nextPageToken")
        return messages

    def get_metadata(self, headers, message_id, telemetry=None):
        url = (
            f"{GMAIL_API}/messages/{message_id}?"
            + urllib.parse.urlencode(
                [
                    ("format", "metadata"),
                    *[("metadataHeaders", header) for header in METADATA_HEADERS],
                ]
            )
        )
        message = metered_provider_request(
            telemetry,
            provider=self.name,
            operation="get_message_metadata",
            url=url,
            headers=headers,
        )
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

    def poll(self, values, provider_state, telemetry=None):
        clear_provider_error(provider_state)
        checkpoint = provider_state.get("checkpoint_epoch")
        initialized = checkpoint is None
        max_results = int_config(
            values,
            "EMAIL_POLL_INITIAL_MAX_MESSAGES" if initialized else "EMAIL_POLL_MAX_MESSAGES",
            20 if initialized else 50,
        )
        token = self.access_token(values, telemetry=telemetry)
        headers = {"Authorization": f"Bearer {token}"}
        message_refs = self.list_message_refs(
            headers, max_results, checkpoint, initialized, telemetry=telemetry
        )
        messages = []
        max_epoch = checkpoint or 0

        for ref in message_refs:
            metadata = self.get_metadata(headers, ref["id"], telemetry=telemetry)
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


class YahooPoller(BaseProviderPoller):
    name = "yahoo"

    def access_token(self, values, provider_state, telemetry=None):
        refresh_token = provider_state.get("refresh_token") or require(
            values, "YAHOO_REFRESH_TOKENS"
        )
        body = urllib.parse.urlencode(
            {
                "client_id": require(values, "YAHOO_CLIENT_ID"),
                "client_secret": require(values, "YAHOO_CLIENT_SECRET"),
                "redirect_uri": require(values, "YAHOO_REDIRECT_URI"),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()
        token = metered_provider_request(
            telemetry,
            provider=self.name,
            operation="oauth_token",
            url=YAHOO_TOKEN_URL,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not token.get("access_token"):
            raise EmailProviderRequestError(
                method="POST",
                url=YAHOO_TOKEN_URL,
                reason="missing_access_token",
                details="Token response did not include access_token.",
            )
        if token.get("refresh_token"):
            provider_state["refresh_token"] = token["refresh_token"]
        return token["access_token"]

    def mailbox_email(self, values, access_token="", telemetry=None):
        configured = values.get("YAHOO_EMAIL") or values.get("YAHOO_EMAIL_ADDRESS", "")
        if configured:
            return configured
        if not access_token:
            raise SystemExit("Missing required .env value: YAHOO_EMAIL")
        userinfo = metered_provider_request(
            telemetry,
            provider=self.name,
            operation="userinfo",
            url=YAHOO_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        email_address = userinfo.get("email", "")
        if not email_address:
            raise EmailProviderRequestError(
                method="GET",
                url=YAHOO_USERINFO_URL,
                reason="missing_email",
                details="Yahoo userinfo response did not include email.",
            )
        return email_address

    def connect(self, values, email_address, credential, auth_method):
        host = values.get("YAHOO_IMAP_HOST", "imap.mail.yahoo.com")
        port = int_config(values, "YAHOO_IMAP_PORT", 993)
        try:
            conn = imaplib.IMAP4_SSL(host, port)
            if auth_method == "password":
                conn.login(email_address, credential)
            else:
                auth = f"user={email_address}\x01auth=Bearer {credential}\x01\x01"
                conn.authenticate("XOAUTH2", lambda _: auth.encode())
            conn.select("INBOX", readonly=True)
            return conn
        except (imaplib.IMAP4.error, OSError, TimeoutError) as exc:
            raise EmailProviderRequestError(
                method="IMAP",
                url=f"imaps://{host}:{port}/INBOX",
                reason=type(exc).__name__,
                details=truncate(exc, 500),
            ) from exc

    def search_uids(self, conn, checkpoint_uid):
        criterion = "ALL" if checkpoint_uid is None else f"UID {int(checkpoint_uid) + 1}:*"
        status, data = conn.uid("SEARCH", None, criterion)
        if status != "OK":
            raise EmailProviderRequestError(
                method="IMAP",
                url="imaps://imap.mail.yahoo.com/INBOX",
                reason="uid_search_failed",
                details=truncate(data, 500),
            )
        raw = data[0] if data else b""
        return [int(item) for item in raw.split() if item]

    def fetch_metadata(self, conn, uid):
        query = "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
        status, data = conn.uid("FETCH", str(uid), query)
        if status != "OK":
            raise EmailProviderRequestError(
                method="IMAP",
                url="imaps://imap.mail.yahoo.com/INBOX",
                reason="uid_fetch_failed",
                details=truncate(data, 500),
            )
        metadata = {}
        internal_epoch = 0
        internal_time = ""
        for item in data:
            if not isinstance(item, tuple):
                continue
            prefix, payload = item
            if isinstance(prefix, bytes):
                marker = b'INTERNALDATE "'
                start = prefix.find(marker)
                if start >= 0:
                    start += len(marker)
                    end = prefix.find(b'"', start)
                    internal_epoch, internal_time = parse_imap_internaldate(prefix[start:end])
            message = email.message_from_bytes(payload)
            metadata = {
                "id": str(uid),
                "thread_id": "",
                "internal_epoch": internal_epoch,
                "internal_time": internal_time,
                "from": message.get("From", ""),
                "subject": message.get("Subject", ""),
                "date": parse_email_date(message.get("Date", "")),
            }
        if not metadata:
            raise EmailProviderRequestError(
                method="IMAP",
                url="imaps://imap.mail.yahoo.com/INBOX",
                reason="missing_message_metadata",
                details=f"No metadata returned for UID {uid}.",
            )
        return metadata

    def poll(self, values, provider_state, telemetry=None):
        clear_provider_error(provider_state)
        checkpoint_uid = provider_state.get("checkpoint_uid")
        initialized = checkpoint_uid is None
        max_results = int_config(
            values,
            "EMAIL_POLL_INITIAL_MAX_MESSAGES" if initialized else "EMAIL_POLL_MAX_MESSAGES",
            20 if initialized else 50,
        )
        app_password = values.get("YAHOO_APP_PASSWORD", "")
        if app_password:
            email_address = self.mailbox_email(values)
            conn = metered_imap_operation(
                telemetry,
                provider=self.name,
                operation="imap_connect",
                action=lambda: self.connect(values, email_address, app_password, "password"),
            )
        else:
            token = self.access_token(values, provider_state, telemetry=telemetry)
            email_address = self.mailbox_email(values, token, telemetry=telemetry)
            conn = metered_imap_operation(
                telemetry,
                provider=self.name,
                operation="imap_connect",
                action=lambda: self.connect(values, email_address, token, "xoauth2"),
            )
        try:
            uids = metered_imap_operation(
                telemetry,
                provider=self.name,
                operation="imap_search",
                action=lambda: self.search_uids(conn, checkpoint_uid),
            )
            selected_uids = uids[-max_results:] if initialized else uids
            messages = [
                metered_imap_operation(
                    telemetry,
                    provider=self.name,
                    operation="imap_fetch_metadata",
                    action=lambda uid=uid: self.fetch_metadata(conn, uid),
                )
                for uid in selected_uids
            ]
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        checkpoint_before = checkpoint_uid
        max_uid = max([checkpoint_uid or 0, *uids], default=checkpoint_uid or 0)
        max_epoch = max([provider_state.get("checkpoint_epoch", 0), *[m["internal_epoch"] for m in messages]], default=0)
        provider_state["checkpoint_uid"] = max_uid
        provider_state["checkpoint_epoch"] = max_epoch
        provider_state["checkpoint_time"] = (
            dt.datetime.fromtimestamp(max_epoch, dt.UTC).replace(microsecond=0).isoformat()
            if max_epoch
            else ""
        )
        provider_state["last_polled_at"] = utc_now_iso()
        provider_state["initialized"] = True
        provider_state["mailbox"] = email_address
        return PollResult("yahoo", initialized, checkpoint_before, max_uid, messages)


class StubProviderPoller(BaseProviderPoller):
    def __init__(self, name):
        self.name = name

    def poll(self, values, provider_state, telemetry=None):
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
    "yahoo": YahooPoller(),
    "icloud": StubProviderPoller("icloud"),
}


def enabled_providers(values, requested):
    if requested:
        return requested
    configured = values.get("EMAIL_POLL_ENABLED_PROVIDERS", "gmail")
    return [item.strip() for item in configured.split(",") if item.strip()]


def log_result(result, telemetry, *, verbose=False):
    mode = "initialization" if result.initialized else "incremental"
    telemetry.log(
        "info",
        "poll_result",
        provider=result.provider,
        mode=mode,
        checkpoint_before=result.checkpoint_before or "none",
        checkpoint_after=result.checkpoint_after or "none",
        messages=len(result.messages),
    )
    if not verbose:
        return
    for message in result.messages:
        telemetry.log(
            "debug",
            "poll_message_metadata",
            provider=result.provider,
            id=message["id"],
            thread_id=message["thread_id"],
            internal_time=message["internal_time"],
            from_header=message["from"],
            subject=message["subject"],
            date=message["date"],
        )


def append_poll_log(log_file, record, telemetry=None):
    if not log_file:
        return
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        if telemetry:
            telemetry.log(
                "warning",
                "poll_log_append_failed",
                log_file=str(log_file),
                reason=truncate(exc, 240),
            )


def provider_state_summary(provider_state):
    return {
        key: provider_state[key]
        for key in (
            "checkpoint_epoch",
            "checkpoint_time",
            "checkpoint_uid",
            "initialized",
            "last_error_at",
            "last_polled_at",
            "mailbox",
            "status",
        )
        if key in provider_state
    }


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
    telemetry = Telemetry(values)
    state_file = args.state_file or Path(
        values.get("EMAIL_POLL_STATE_FILE", ".state/email-poller-state.json")
    )
    poll_log_file = Path(values.get("EMAIL_POLL_LOG_FILE", ".state/email-poller.log"))
    state = load_state(state_file)
    provider_state = state.setdefault("providers", {})
    sender_filters = load_sender_filters(values)

    for provider_name in enabled_providers(values, args.provider):
        poller = PROVIDERS.get(provider_name)
        if poller is None:
            raise SystemExit(f"Unknown provider: {provider_name}")
        if args.reset_provider_state:
            provider_state[provider_name] = {}
        current = provider_state.setdefault(provider_name, {})
        span = telemetry.start_span("email_provider_poll", provider=provider_name)
        started = dt.datetime.now(dt.UTC)
        try:
            result = poller.poll(values, current, telemetry=telemetry)
        except EmailProviderRequestError as exc:
            record_provider_error(current, exc)
            posted = notify_provider_error(values, provider_name, exc, telemetry=telemetry)
            telemetry.count(
                "priority_email_provider_request_errors_total",
                provider=provider_name,
                status=exc.status or "unknown",
                reason=exc.reason or "unknown",
            )
            telemetry.count(
                "priority_email_slack_error_notifications_total",
                provider=provider_name,
                result="posted" if posted else "skipped",
            )
            duration_ms = (
                dt.datetime.now(dt.UTC) - started
            ).total_seconds() * 1000
            telemetry.log(
                "error",
                "provider_poll_failed",
                provider=provider_name,
                duration_ms=round(duration_ms, 3),
                slack_error_notification_posted=posted,
                state_file=str(state_file),
                poll_log_file=str(poll_log_file),
                provider_state=provider_state_summary(current),
                **exc.summary(),
            )
            telemetry.gauge(
                "priority_email_poll_cycle_duration_ms",
                duration_ms,
                provider=provider_name,
                status="error",
            )
            append_poll_log(
                poll_log_file,
                {
                    "timestamp": utc_now_iso(),
                    "level": "ERROR",
                    "event": "provider_poll",
                    "provider": provider_name,
                    "status": "error",
                    "duration_ms": round(duration_ms, 3),
                    "error": exc.summary(),
                },
                telemetry=telemetry,
            )
            telemetry.end_span(
                span,
                status="error",
                message=str(exc),
                error_type=type(exc).__name__,
                error_reason=exc.reason or "unknown",
            )
            continue
        duration_ms = (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
        mode = "initialization" if result.initialized else "incremental"
        telemetry.count(
            "priority_email_poll_cycles_total",
            provider=provider_name,
            status="ok",
            mode=mode,
        )
        telemetry.count(
            "priority_email_messages_checked_total",
            len(result.messages),
            provider=provider_name,
            mode=mode,
        )
        telemetry.gauge(
            "priority_email_poll_cycle_duration_ms",
            duration_ms,
            provider=provider_name,
            status="ok",
        )
        notification_counts = notify_matched_messages(
            values,
            current,
            result,
            sender_filters,
            telemetry=telemetry,
        )
        telemetry.end_span(
            span,
            status="ok",
            mode=mode,
            messages=len(result.messages),
            initialized=result.initialized,
            matched_messages=notification_counts["matched"],
            slack_posts=notification_counts["posted"],
            slack_post_failures=notification_counts["failed"],
        )
        append_poll_log(
            poll_log_file,
            {
                "timestamp": utc_now_iso(),
                "level": "INFO",
                "event": "provider_poll",
                "provider": provider_name,
                "status": "ok",
                "mode": mode,
                "initialized": result.initialized,
                "messages": len(result.messages),
                "matched_messages": notification_counts["matched"],
                "slack_posts": notification_counts["posted"],
                "slack_post_failures": notification_counts["failed"],
                "checkpoint_before": result.checkpoint_before or "none",
                "checkpoint_after": result.checkpoint_after or "none",
                "duration_ms": round(duration_ms, 3),
            },
            telemetry=telemetry,
        )
        log_result(result, telemetry, verbose=args.verbose)

    save_state(state_file, state)
    telemetry.log("info", "state_saved", state_file=str(state_file))
    telemetry.flush_metrics()


if __name__ == "__main__":
    main()
