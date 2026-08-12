#!/usr/bin/env python3
"""Block obvious cloud credentials before they reach the remote.

Week 7 of the plan asks for this hook. It exists from Week 1 instead, because the
cheapest moment to stop a leaked key is before the first one is ever created.

Not a security product -- a seatbelt. Rotate any key that gets past it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "AWS secret access key": re.compile(r"aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "GCP service account JSON": re.compile(r'"type"\s*:\s*"service_account"'),
    "Azure client secret": re.compile(r"client_secret\s*[:=]\s*['\"][^'\"]{20,}"),
    "Groq / OpenAI style key": re.compile(r"\b(?:gsk|sk)_[A-Za-z0-9]{20,}\b"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Bearer token literal": re.compile(
        r"Authorization\s*[:=]\s*['\"]?Bearer\s+[A-Za-z0-9._\-]{20,}"
    ),
}

ALLOWLIST = {"scripts/check_no_secrets.py", ".env.example"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ipynb", ".lock", ".parquet"}


def scan(path: Path) -> list[str]:
    if path.as_posix() in ALLOWLIST or path.suffix in SKIP_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [
        f"{path}: looks like a {label}"
        for label, pattern in PATTERNS.items()
        if pattern.search(text)
    ]


def main(argv: list[str]) -> int:
    findings = [f for arg in argv for f in scan(Path(arg))]
    if not findings:
        return 0
    print("\nBlocked commit -- possible credential in the diff:\n")
    for finding in findings:
        print(f"  {finding}")
    print(
        "\nMove it to .env (gitignored). If this is a false positive, add the path to\n"
        "ALLOWLIST in scripts/check_no_secrets.py in the same commit.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
