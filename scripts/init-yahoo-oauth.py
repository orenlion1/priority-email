#!/usr/bin/env python3
import argparse
import http.server
import json
import secrets
import socketserver
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
SCOPES = ["openid", "profile", "email"]


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    return values


def require(values, key):
    value = values.get(key, "")
    if not value or value == "TODO":
        raise SystemExit(f"Missing required .env value: {key}")
    return value


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
        for key, value in updates.items():
            if key not in seen:
                out.append(f"{key}={value}")

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
            b"Yahoo authorization complete. You can close this tab and return to Codex."
        )

    def log_message(self, format, *args):
        return


def exchange_code(values, code, redirect_uri):
    body = urllib.parse.urlencode(
        {
            "client_id": require(values, "YAHOO_CLIENT_ID"),
            "client_secret": require(values, "YAHOO_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
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


def refresh_access_token(values, refresh_token, redirect_uri):
    body = urllib.parse.urlencode(
        {
            "client_id": require(values, "YAHOO_CLIENT_ID"),
            "client_secret": require(values, "YAHOO_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(
        description="Run local Yahoo OAuth and store refresh token in .env."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--redirect-uri", default="")
    parser.add_argument(
        "--manual-code",
        action="store_true",
        help="Print the authorization URL and prompt for a pasted code from an HTTPS callback URL.",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    values = load_env(args.env_file)
    redirect_uri = args.redirect_uri or values.get("YAHOO_REDIRECT_URI") or f"http://localhost:{args.port}/"
    state = secrets.token_urlsafe(24)

    params = {
        "client_id": require(values, "YAHOO_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    if args.manual_code:
        if not args.no_browser:
            webbrowser.open(auth_url)
        print("Open this URL to authorize Yahoo access:", flush=True)
        print(auth_url, flush=True)
        code = input("Paste Yahoo authorization code: ").strip()
    else:
        CallbackHandler.expected_state = state
        CallbackHandler.response = {}
        with socketserver.TCPServer(("127.0.0.1", args.port), CallbackHandler) as httpd:
            thread = threading.Thread(target=httpd.handle_request, daemon=True)
            thread.start()
            if args.no_browser:
                print("Open this URL to authorize Yahoo access:", flush=True)
                print(auth_url, flush=True)
            else:
                print("Opening browser for Yahoo authorization...", flush=True)
                webbrowser.open(auth_url)
            thread.join(timeout=300)

        response = CallbackHandler.response
        if not response:
            raise SystemExit("Timed out waiting for Yahoo authorization.")
        if response.get("error"):
            raise SystemExit(f"Authorization failed: {response['error']}")
        code = response.get("code", "")

    if not code:
        raise SystemExit("Authorization response did not include a code.")

    token = exchange_code(values, code, redirect_uri)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise SystemExit("Token response did not include refresh_token.")

    validated = refresh_access_token(values, refresh_token, redirect_uri)
    if not validated.get("access_token"):
        raise SystemExit("Refresh token validation did not return access_token.")

    updates = {
        "YAHOO_REFRESH_TOKENS": refresh_token,
        "YAHOO_REDIRECT_URI": redirect_uri,
    }
    update_env(args.env_file, updates)
    print(f"Updated {args.env_file} with Yahoo refresh token.")


if __name__ == "__main__":
    main()
