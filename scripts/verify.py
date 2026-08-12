#!/usr/bin/env python3
"""Prove this clone is set up correctly.

    make verify        (or:  ./.venv/bin/python scripts/verify.py)

This is the Week 1 "Done when" turned into a script. Run it on all three laptops.
Nobody's setup is done until this prints PASS on their machine, and "it works on
mine" stops being a valid sentence.

Every failure line ends with the exact command that fixes it. Add a check here the
first time a teammate loses an afternoon to an environment problem — that is how
this file earns its keep.
"""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


@dataclass
class Result:
    ok: bool
    detail: str
    fix: str = ""
    warn_only: bool = False


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def check_python() -> Result:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 12)
    return Result(ok, f"{major}.{minor}", "install Python 3.12+ and rerun `make setup`")


def check_env_file() -> Result:
    exists = (ROOT / ".env").exists()
    return Result(exists, "present" if exists else "missing", "cp .env.example .env")


def check_python_deps() -> Result:
    missing: list[str] = []
    for module in ("fastapi", "sqlalchemy", "celery", "redis", "influxdb_client", "alembic"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return Result(False, f"missing {', '.join(missing)}", 'pip install -e ".[dev]"')
    return Result(True, "installed")


def check_port(name: str, port: int, fix: str) -> Result:
    ok = port_open("127.0.0.1", port)
    return Result(ok, f"127.0.0.1:{port} {'open' if ok else 'closed'}", fix)


def check_postgres() -> Result:
    try:
        from sqlalchemy import text

        from core.db import get_engine

        with get_engine().connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
            has_vector = conn.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
            migrated = conn.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()
    except Exception as exc:  # any failure here means the database is not usable
        return Result(False, str(exc).splitlines()[0][:70], "make up")

    if not has_vector:
        return Result(False, "pgvector extension absent", "make nuke && make up")
    if not migrated:
        return Result(False, f"pg {version}, no migrations applied", "make migrate")
    return Result(True, f"pg {version}, pgvector on, migrated")


def check_redis() -> Result:
    try:
        import redis

        from core.config import get_settings

        client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        client.ping()
    except Exception as exc:
        return Result(False, str(exc).splitlines()[0][:70], "make up")
    return Result(True, "PING answered")


def check_influx() -> Result:
    try:
        import httpx

        from core.config import get_settings

        response = httpx.get(f"{get_settings().influx_url}/ping", timeout=3)
        ok = response.status_code in (200, 204)
    except Exception as exc:
        return Result(False, str(exc).splitlines()[0][:70], "make up")
    return Result(ok, "ping answered" if ok else "unexpected status", "make up")


def check_web_deps() -> Result:
    exists = (ROOT / "web" / "node_modules").is_dir()
    return Result(exists, "installed" if exists else "missing", "cd web && npm install")


def check_api() -> Result:
    """Warn only: the API is a separate process you start yourself."""
    ok = port_open("127.0.0.1", 8000)
    return Result(ok, "responding" if ok else "not running", "make api", warn_only=True)


CHECKS: list[tuple[str, object]] = [
    ("python version", check_python),
    (".env file", check_env_file),
    ("python deps", check_python_deps),
    ("postgres port", lambda: check_port("postgres", 5432, "make up")),
    ("redis port", lambda: check_port("redis", 6379, "make up")),
    ("influxdb port", lambda: check_port("influxdb", 8086, "make up")),
    ("postgres query", check_postgres),
    ("redis command", check_redis),
    ("influxdb ping", check_influx),
    ("web deps", check_web_deps),
    ("api process", check_api),
]


def main() -> int:
    print(f"\n{DIM}AutonomousDR setup check — {ROOT}{RESET}\n")
    failures: list[tuple[str, Result]] = []
    warnings: list[tuple[str, Result]] = []

    for name, check in CHECKS:
        result: Result = check()  # type: ignore[operator]
        if result.ok:
            mark, colour = "PASS", GREEN
        elif result.warn_only:
            mark, colour = "SKIP", YELLOW
            warnings.append((name, result))
        else:
            mark, colour = "FAIL", RED
            failures.append((name, result))
        print(f"  {colour}{mark}{RESET}  {name:<16} {DIM}{result.detail}{RESET}")

    print()
    if failures:
        print(f"{RED}Not ready.{RESET} Fix in this order:\n")
        for name, result in failures:
            print(f"  {name:<16} -> {result.fix}")
        print()
        return 1

    if warnings:
        for name, result in warnings:
            print(f"{YELLOW}Optional:{RESET} {name} — start it with `{result.fix}`")
        print()

    print(f"{GREEN}Ready.{RESET} Databases, migrations and dependencies all check out.")
    print(f"{DIM}Next: `make api`, `make web`, then open http://localhost:5173{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
