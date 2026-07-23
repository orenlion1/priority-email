"""Slack request signature verification.

A Slack Events endpoint is public and unauthenticated -- anyone on the internet
can POST to it. This module is the only thing standing between that and the
filter configuration and poller, so it fails closed everywhere: any missing
header, malformed value, stale timestamp or mismatched digest is a rejection,
never a warning.

Reference: https://api.slack.com/authentication/verifying-requests-from-slack
"""

from __future__ import annotations

import hashlib
import hmac
import time

VERSION = "v0"

# Slack recommends rejecting anything older than five minutes. This bounds
# replay: a captured request stops working shortly after it is captured.
MAX_AGE_SECONDS = 60 * 5


class SignatureError(Exception):
    """Request did not come from Slack, or came too long ago to trust."""


def _parse_timestamp(raw: str | None) -> int:
    if not raw:
        raise SignatureError("missing X-Slack-Request-Timestamp")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise SignatureError(f"malformed timestamp: {raw!r}") from exc


def verify(
    *,
    body: str,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str,
    now: float | None = None,
) -> None:
    """Raise SignatureError unless the request is a genuine, fresh Slack call.

    Returns None on success. Callers must treat any exception as a 401 and must
    not fall through to processing -- there is no partial-trust path.

    `now` is injectable for tests only; production passes None.
    """
    if not signing_secret:
        # An empty secret would make every signature comparison trivially
        # forgeable. Refuse to run rather than run insecurely.
        raise SignatureError("signing secret is empty")

    if not signature:
        raise SignatureError("missing X-Slack-Signature")

    ts = _parse_timestamp(timestamp)
    current = time.time() if now is None else now

    # Absolute value: a timestamp far in the FUTURE is as suspicious as a stale
    # one, and would otherwise sail through a naive `current - ts > MAX_AGE`.
    if abs(current - ts) > MAX_AGE_SECONDS:
        raise SignatureError(f"timestamp outside {MAX_AGE_SECONDS}s window")

    basestring = f"{VERSION}:{ts}:{body}".encode()
    digest = hmac.new(
        signing_secret.encode(), basestring, hashlib.sha256
    ).hexdigest()
    expected = f"{VERSION}={digest}"

    # compare_digest, not ==. String equality short-circuits on the first
    # differing byte, leaking how much of a guess was correct through timing.
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("signature mismatch")
