#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


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


def request_json(url, *, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {details}")


def access_token(values):
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
        raise SystemExit("Token response did not include access_token.")
    return token["access_token"]


def main():
    values = load_env(Path(".env"))
    token = access_token(values)
    headers = {"Authorization": f"Bearer {token}"}
    list_url = f"{GMAIL_API}/messages?{urllib.parse.urlencode({'maxResults': 1, 'q': 'in:anywhere'})}"
    listing = request_json(list_url, headers=headers)
    messages = listing.get("messages", [])
    if not messages:
        print("Gmail read validation succeeded, but no messages were returned.")
        return

    message_id = messages[0]["id"]
    metadata_headers = ["From", "Subject", "Date"]
    get_url = (
        f"{GMAIL_API}/messages/{message_id}?"
        + urllib.parse.urlencode(
            [
                ("format", "metadata"),
                *[("metadataHeaders", header) for header in metadata_headers],
            ]
        )
    )
    message = request_json(get_url, headers=headers)
    headers_by_name = {
        item.get("name", ""): item.get("value", "")
        for item in message.get("payload", {}).get("headers", [])
    }

    print("Gmail read validation succeeded.")
    print(f"Message ID: {message.get('id', '')}")
    print(f"Thread ID: {message.get('threadId', '')}")
    for name in metadata_headers:
        print(f"{name}: {headers_by_name.get(name, '')}")


if __name__ == "__main__":
    main()
