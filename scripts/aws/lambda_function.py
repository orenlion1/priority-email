"""AWS Lambda entry point for the Priority Email poller.

The service was a looping pod on EKS (run-poller-loop.sh). After the cost-reduction
migration it runs as a scheduled Lambda: EventBridge invokes this handler on an interval,
and each invocation performs exactly one poll cycle — the same unit run-poller-loop.sh ran
in its loop. poll-email.py is executed unchanged (as a subprocess) so its behaviour and
tests are identical to the container.

Durable state that used to live on a k8s PVC now lives in S3:
  s3://<bucket>/state/email-poller-state.json   provider checkpoints
  s3://<bucket>/filters/<kind>-filters.txt      assembled sender filters

Secrets (OAuth tokens, Slack, push) come from the Secrets Manager secret that
sync-runtime-secret.sh already maintains; its value is the .env file verbatim.
"""

import os
import subprocess
import sys
from pathlib import Path

import boto3

TASK_ROOT = os.environ.get("LAMBDA_TASK_ROOT", str(Path(__file__).resolve().parent.parent.parent))
POLL_SCRIPT = os.path.join(TASK_ROOT, "scripts", "poll-email.py")

STATE_BUCKET = os.environ["STATE_BUCKET"]
RUNTIME_SECRET_ID = os.environ.get("RUNTIME_SECRET_ID", "priority-email/runtime")
STATE_KEY = os.environ.get("STATE_S3_KEY", "state/email-poller-state.json")
FILTERS_PREFIX = os.environ.get("FILTERS_S3_PREFIX", "filters/")

ENV_PATH = "/tmp/.env"
FILTER_DIR = "/tmp/filters"
STATE_PATH = "/tmp/email-poller-state.json"
FILTER_FILES = ("domain-filters.txt", "email-address-filters.txt", "sender-name-filters.txt")

_s3 = boto3.client("s3")
_secrets = boto3.client("secretsmanager")


def _write_runtime_env():
    """Materialize the runtime .env from Secrets Manager (its value is the .env verbatim)."""
    secret = _secrets.get_secret_value(SecretId=RUNTIME_SECRET_ID)["SecretString"]
    Path(ENV_PATH).write_text(secret)


def _sync_filters():
    """Hydrate the assembled filter files from S3 into /tmp; absent files become empty."""
    os.makedirs(FILTER_DIR, exist_ok=True)
    for name in FILTER_FILES:
        dest = os.path.join(FILTER_DIR, name)
        try:
            _s3.download_file(STATE_BUCKET, FILTERS_PREFIX + name, dest)
        except _s3.exceptions.ClientError:
            Path(dest).write_text("")


def _download_state():
    try:
        _s3.download_file(STATE_BUCKET, STATE_KEY, STATE_PATH)
    except _s3.exceptions.ClientError:
        pass  # first run — poll-email.py initializes a fresh checkpoint


def _upload_state():
    if os.path.exists(STATE_PATH):
        _s3.upload_file(STATE_PATH, STATE_BUCKET, STATE_KEY)


def handler(event, context):
    _write_runtime_env()
    _sync_filters()
    _download_state()

    # os.environ overrides the .env inside poll-email.py's load_env(), so pointing the
    # filter/state locations at /tmp here is authoritative for the child process.
    env = {
        **os.environ,
        "EMAIL_FILTER_DIR": FILTER_DIR,
        "EMAIL_POLL_STATE_FILE": STATE_PATH,
    }
    proc = subprocess.run(
        [sys.executable, POLL_SCRIPT, "--env-file", ENV_PATH, "--state-file", STATE_PATH],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    # Persist the checkpoint even on partial failure so progress is not lost.
    _upload_state()

    if proc.returncode != 0:
        raise RuntimeError(f"poll cycle failed with exit code {proc.returncode}")
    return {"ok": True, "returncode": proc.returncode}
