#!/usr/bin/env python3
import argparse
import http.server
import json
import os
import secrets
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def load_client_secret(path):
    with path.open() as f:
        data = json.load(f)
    config = data.get("installed") or data.get("web")
    if not config:
        raise SystemExit("OAuth client file must contain an installed or web client.")
    for key in ("client_id", "client_secret"):
        if not config.get(key):
            raise SystemExit(f"OAuth client file is missing {key}.")
    return config


def update_env(path, updates):
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)

    if updates.keys() - seen:
        if out and out[-1] != "":
            out.append("")
        for key in updates:
            if key not in seen:
                out.append(f"{key}={updates[key]}")

    path.write_text("\n".join(out) + "\n")


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    response = {}
    expected_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        state = params.get("state", [""])[0]
        if state != self.expected_state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid OAuth state. You can close this tab.")
            CallbackHandler.response = {"error": "invalid_state"}
            return

        if "error" in params:
            CallbackHandler.response = {"error": params["error"][0]}
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization failed. You can close this tab.")
            return

        CallbackHandler.response = {"code": params.get("code", [""])[0]}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            b"Gmail authorization complete. You can close this tab and return to Codex."
        )

    def log_message(self, format, *args):
        return


def exchange_code(client, code, redirect_uri):
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors="replace")
        raise SystemExit(f"Token exchange failed with HTTP {exc.code}: {details}")


def main():
    parser = argparse.ArgumentParser(
        description="Run local Gmail OAuth and store refresh token in .env."
    )
    parser.add_argument(
        "--client-secret",
        type=Path,
        default=None,
        help="Path to downloaded Google OAuth client JSON.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    client_secret = args.client_secret
    if client_secret is None:
        matches = sorted(Path(".").glob("client_secret_*.apps.googleusercontent.com*.json"))
        if not matches:
            raise SystemExit("No Google OAuth client JSON found.")
        client_secret = matches[0]

    client = load_client_secret(client_secret)
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://localhost:{args.port}/"
    CallbackHandler.expected_state = state
    CallbackHandler.response = {}

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    with socketserver.TCPServer(("127.0.0.1", args.port), CallbackHandler) as httpd:
        httpd.timeout = 300
        thread = threading.Thread(target=httpd.handle_request, daemon=True)
        thread.start()

        if args.no_browser:
            print("Open this URL to authorize Gmail access:", flush=True)
            print(auth_url, flush=True)
        else:
            print("Opening browser for Gmail authorization...", flush=True)
            webbrowser.open(auth_url)

        thread.join(timeout=300)

    response = CallbackHandler.response
    if not response:
        raise SystemExit("Timed out waiting for Gmail authorization.")
    if response.get("error"):
        raise SystemExit(f"Authorization failed: {response['error']}")
    if not response.get("code"):
        raise SystemExit("Authorization response did not include a code.")

    token = exchange_code(client, response["code"], redirect_uri)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "Token response did not include refresh_token. Re-run with prompt=consent or revoke the app grant and try again."
        )

    update_env(
        args.env_file,
        {
            "GMAIL_CLIENT_ID": client["client_id"],
            "GMAIL_CLIENT_SECRET": client["client_secret"],
            "GMAIL_REFRESH_TOKENS": refresh_token,
        },
    )
    print(f"Updated {args.env_file} with Gmail OAuth client values and refresh token.")


if __name__ == "__main__":
    main()
