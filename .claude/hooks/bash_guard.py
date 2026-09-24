#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Blocks a short list of commands that are almost always a mistake rather than
an intentional action: force-pushing to main branches, hard resets/cleans,
wide-open rm -rf, and bulk docker/db wipes. Everything else is allowed —
this is a guardrail, not a sandbox; the permission system already asks for
confirmation on risky-but-legitimate actions.

Registered in .claude/settings.json under hooks.PreToolUse (matcher "Bash").
Fails open: any error reading/parsing input allows the command through
rather than blocking Claude Code from working.

Add a rule by appending a (pattern, reason) tuple to RULES below.
"""

import json
import re
import sys

PROTECTED_BRANCHES = r"(main|master|prod|production)"

RULES = [
    (
        re.compile(rf"git\s+push\s+.*--force(?!-with-lease)\b.*\b{PROTECTED_BRANCHES}\b"),
        "force-push to a protected branch",
    ),
    (
        re.compile(r"git\s+push\s+.*-f\b"),
        "force-push (use --force-with-lease if this is intentional, and confirm with the user first)",
    ),
    (
        re.compile(r"git\s+reset\s+--hard"),
        "git reset --hard discards uncommitted work",
    ),
    (
        re.compile(r"git\s+clean\s+.*-[a-z]*f"),
        "git clean -f permanently deletes untracked files",
    ),
    (
        re.compile(r"\brm\s+.*-[a-z]*r[a-z]*f[a-z]*\s+/(\s|$)"),
        "rm -rf on filesystem root",
    ),
    (
        re.compile(r"\bdocker\s+(system|volume|image)\s+prune\b"),
        "docker prune can delete volumes/images other projects depend on",
    ),
    (
        re.compile(r"\b(drop\s+database|DROP\s+DATABASE)\b.*\b(prod|production)\b"),
        "dropping a production database",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    for pattern, reason in RULES:
        if pattern.search(command):
            sys.stderr.write(
                f"Blocked by bash_guard.py: {reason}.\n"
                f"Command: {command}\n"
                "If this is genuinely intended, ask the user to run it themselves "
                "or confirm explicitly before retrying a rephrased, narrower command.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
