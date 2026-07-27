"""The filter store the Slack handler reads and writes, backed by S3.

The poller reads three plaintext filter files from S3 each cycle
(`filters/<kind>-filters.txt`); this module is how a runtime `filter add` /
`filter remove` from Slack changes them so the very next poll sees the edit.

Two writes happen on every mutation, and both matter:

  1. The plaintext filter file is rewritten in S3 -- immediate effect, the
     poller's next cycle picks it up.
  2. An age-encrypted operation is appended to `filters/ops/` in S3 -- the
     durable, auditable record. The deploy-time assembler
     (scripts/filters/sync-filters-to-s3.sh) reconciles from the ops log, so a
     Slack edit survives the next deploy instead of being clobbered by a
     re-assembly from the git baseline.

Encryption uses ONLY the age *recipients* (public) key, committed at
filters/age-recipients.pub and bundled into this Lambda. The public endpoint
never holds the private key: it can add to the encrypted log, never read it.
That is the same privacy boundary add-filter-op.sh keeps for operators and
coding agents -- write a filter without seeing the existing ones.

The plaintext read/write, the op append, and the age call are isolated here (and
injectable) so the handler's command orchestration is testable without S3 or age.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Protocol

# The kinds the poller matches and the assembler recognises, in the order the
# filter files list them. Mirrors scripts/slack/commands.FILTER_KINDS and
# scripts/filters/assemble-filters.KINDS so the three cannot drift.
FILTER_KINDS = ("domain", "email-address", "sender-name")


class _Clock(Protocol):
    def __call__(self) -> str: ...


def _default_now() -> str:
    # Import lazily so tests can inject a fixed clock without patching module load.
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _token_hex() -> str:
    import secrets

    return secrets.token_hex(3)


def parse_filter_file(text: str) -> list[str]:
    """The stored entries of one filter file, newest first, comments dropped.

    Matches how poll-email.load_filter_values reads them: collapse whitespace,
    skip blanks and `#` comments, preserve order. Kept lenient on read so a
    hand-edited file still loads.
    """
    entries: list[str] = []
    for raw in text.splitlines():
        item = " ".join(raw.strip().split())
        if not item or item.startswith("#"):
            continue
        entries.append(item)
    return entries


def render_filter_file(entries: list[str]) -> str:
    """The on-disk form the assembler writes: one entry per line, newest first."""
    return "".join(entry + "\n" for entry in entries)


class S3FilterStore:
    """Reads and writes the poller's S3 filter files and encrypted ops log.

    `s3` is a boto3 S3 client (injected in tests). `bucket` is the poller's
    state bucket. `recipients_path` points at the committed age public key.
    `filters_prefix`/`ops_prefix` locate the plaintext files and the op log.
    """

    def __init__(
        self,
        *,
        s3,
        bucket: str,
        recipients_path: str,
        filters_prefix: str = "filters/",
        ops_prefix: str = "filters/ops/",
        now: _Clock = _default_now,
        encrypt=None,
    ) -> None:
        self._s3 = s3
        self._bucket = bucket
        self._recipients_path = recipients_path
        self._filters_prefix = filters_prefix
        self._ops_prefix = ops_prefix
        self._now = now
        # The age call is injectable so unit tests never shell out.
        self._encrypt = encrypt or self._age_encrypt

    # --- plaintext filter files ------------------------------------------------
    def read_filters(self) -> dict[str, list[str]]:
        """The current entries for every kind, newest first.

        A missing filter object is an empty kind, not an error: the poller treats
        an absent file the same way, and `filter list` must distinguish "no
        domain filters" from a load failure rather than blow up on first use.
        """
        lists: dict[str, list[str]] = {}
        for kind in FILTER_KINDS:
            key = f"{self._filters_prefix}{kind}-filters.txt"
            try:
                body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
            except self._s3.exceptions.NoSuchKey:
                lists[kind] = []
                continue
            lists[kind] = parse_filter_file(body.decode("utf-8"))
        return lists

    def write_filter(self, kind: str, entries: list[str]) -> None:
        """Replace one kind's filter file with `entries` (newest first)."""
        key = f"{self._filters_prefix}{kind}-filters.txt"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=render_filter_file(entries).encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )

    # --- encrypted ops log -----------------------------------------------------
    def append_op(self, action: str, kind: str, value: str) -> str:
        """Append one age-encrypted `{action, kind, value}` op to the S3 ops log.

        Returns the op's S3 key. The op is the durable record the deploy-time
        assembler reconciles from; the plaintext write above is only the
        immediately-visible copy. Encryption uses the public recipients key, so
        this never needs, and never holds, the key that could read the log back.
        """
        op = json.dumps({"action": action, "kind": kind, "value": value})
        ciphertext = self._encrypt(op)
        name = f"{self._now()}-{_token_hex()}.age"
        key = f"{self._ops_prefix}{name}"
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=ciphertext)
        return key

    def _age_encrypt(self, plaintext: str) -> bytes:
        """Encrypt with the committed age recipients key via the `age` binary.

        Mirrors scripts/filters/add-filter-op.sh (`age --encrypt -R <recipients>
        -a`) so an op this writes is one decrypt-filters.sh can read. ASCII-armored
        so the object is a text blob. The `age` binary must be on PATH or bundled
        beside the handler; the deploy packages it for the Lambda architecture.
        """
        age_bin = os.environ.get("AGE_BIN", "age")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            tmp.write(plaintext)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                [age_bin, "--encrypt", "-R", self._recipients_path, "-a", tmp_path],
                capture_output=True,
                check=True,
            )
        finally:
            os.unlink(tmp_path)
        return result.stdout
