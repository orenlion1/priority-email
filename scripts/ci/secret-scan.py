#!/usr/bin/env python3
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".state", "__pycache__"}
SKIP_SUFFIXES = {".png", ".pyc"}
FORBIDDEN_PATH = re.compile(
    r"(^|/)(\.env$|\.env\.(?!example)|client_secret_|filters/.*\.txt$|\.state|__pycache__|.*secret.*\.yaml$)"
)
SECRET_PATTERNS = {
    "slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    "github token": re.compile(r"gh[opsu]_[A-Za-z0-9_]{20,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "nonempty AWS_SECRET_ACCESS_KEY": re.compile(r"(?m)^AWS_SECRET_ACCESS_KEY=\S+"),
    "nonempty AWS_ACCESS_KEY_ID": re.compile(r"(?m)^AWS_ACCESS_KEY_ID=\S+"),
    "nonempty AWS_SESSION_TOKEN": re.compile(r"(?m)^AWS_SESSION_TOKEN=\S+"),
    "nonempty GMAIL_CLIENT_SECRET": re.compile(r"(?m)^GMAIL_CLIENT_SECRET=\S+"),
    "nonempty GMAIL_REFRESH_TOKENS": re.compile(r"(?m)^GMAIL_REFRESH_TOKENS=\S+"),
    "nonempty SLACK_BOT_TOKEN": re.compile(r"(?m)^SLACK_BOT_TOKEN=\S+"),
    "nonempty PUSH_PROVIDER_TOKEN": re.compile(r"(?m)^PUSH_PROVIDER_TOKEN=\S+"),
}


def tracked_files():
    try:
        output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
        candidates = output.splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError):
        candidates = [path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()]
    for rel in candidates:
        path = ROOT / rel
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in pathlib.PurePosixPath(rel).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield rel, path


def main():
    failures = []
    for rel, path in tracked_files():
        if FORBIDDEN_PATH.search(rel):
            failures.append(f"forbidden path present in scan scope: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"possible secret ({label}) in {rel}")
    if failures:
        print("CI secret scan failed:")
        print("\n".join(failures))
        return 1
    print("CI secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
