#!/usr/bin/env python3
"""Assemble plaintext filter files from a stream of decrypted filter operations.

Reads one JSON operation per line from stdin, oldest first, and writes the
three filter files into --output-dir. Operations are untrusted input: any
malformed operation aborts assembly so a bad op can never silently drop or
corrupt live filters. Error messages never include filter values.
"""
import argparse
import json
import pathlib
import sys


KINDS = ("domain", "email-address", "sender-name")
ACTIONS = ("baseline", "add", "remove")
MAX_VALUE_LENGTH = 320


def collapse(value):
    return " ".join(str(value).strip().split())


def comparison_key(kind, value):
    key = collapse(value).lower()
    if kind == "domain":
        key = key.removeprefix("@")
    return key


def validate_value(value):
    if not isinstance(value, str):
        raise ValueError("filter value must be a string")
    collapsed = collapse(value)
    if not collapsed:
        raise ValueError("filter value is empty")
    if len(collapsed) > MAX_VALUE_LENGTH:
        raise ValueError("filter value is too long")
    if collapsed.startswith("#"):
        raise ValueError("filter value may not start with '#'")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in collapsed):
        raise ValueError("filter value contains control characters")
    return collapsed


def apply_operation(lists, op):
    if not isinstance(op, dict):
        raise ValueError("operation must be a JSON object")
    action = op.get("action")
    kind = op.get("kind")
    if action not in ACTIONS:
        raise ValueError("unknown action")
    if kind not in KINDS:
        raise ValueError("unknown kind")
    entries = lists[kind]
    if action == "baseline":
        values = op.get("values")
        if not isinstance(values, list):
            raise ValueError("baseline requires a list of values")
        entries.clear()
        seen = set()
        for value in values:
            collapsed = validate_value(value)
            key = comparison_key(kind, collapsed)
            if key in seen:
                continue
            entries.append(collapsed)
            seen.add(key)
        return
    collapsed = validate_value(op.get("value"))
    key = comparison_key(kind, collapsed)
    if action == "add":
        if all(comparison_key(kind, existing) != key for existing in entries):
            # Newest entries stay at the head of each filter file.
            entries.insert(0, collapsed)
        return
    entries[:] = [
        existing for existing in entries if comparison_key(kind, existing) != key
    ]


def assemble(stream):
    lists = {kind: [] for kind in KINDS}
    for line_number, line in enumerate(stream, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            op = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"operation {line_number}: invalid JSON") from None
        try:
            apply_operation(lists, op)
        except ValueError as exc:
            raise ValueError(f"operation {line_number}: {exc}") from None
    return lists


def write_filter_files(lists, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        path = output_dir / f"{kind}-filters.txt"
        path.write_text("".join(entry + "\n" for entry in lists[kind]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        lists = assemble(sys.stdin)
    except ValueError as exc:
        print(f"filter assembly failed: {exc}", file=sys.stderr)
        return 1
    write_filter_files(lists, args.output_dir)
    for kind in KINDS:
        print(f"{kind}: {len(lists[kind])} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
