#!/usr/bin/env python3
import argparse
import json
import urllib.request
from pathlib import Path


SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


def load_env(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def require(values, key):
    value = values.get(key, "")
    if not value or value == "TODO":
        raise SystemExit(f"Missing required .env value: {key}")
    return value


def post_message(token, channel, text):
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
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Post a test message to Slack.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--message",
        default="Priority Email Slack test: notification path is connected.",
    )
    args = parser.parse_args()

    values = load_env(args.env_file)
    response = post_message(
        require(values, "SLACK_BOT_TOKEN"),
        require(values, "SLACK_CHANNEL_ID"),
        args.message,
    )
    if not response.get("ok"):
        raise SystemExit(f"Slack post failed: {response.get('error', 'unknown_error')}")
    print("Slack post succeeded.")
    print(f"channel={response.get('channel', '')}")
    print(f"ts={response.get('ts', '')}")


if __name__ == "__main__":
    main()
