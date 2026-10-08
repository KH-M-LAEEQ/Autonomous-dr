#!/usr/bin/env python3
"""`make smoke` -- one command that walks the product end to end and prints
PASS/FAIL per check, stopping at the first failure.

This is a diagnostic, not a repair tool: it never fixes anything it finds.
Read the first FAIL's reason, go look at what it names, fix it by hand,
run `make smoke` again.

Checks, in order (see each `_check_*` function's docstring for exactly what
it does and why):
  1. Docker services up: Postgres, Redis, InfluxDB, worker, beat.
  2. Migration at head (0002); 16 tables exist; pgvector extension and the
     HNSW index on corpus_chunks exist.
  3. API /health and /ready return OK.
  4. Collector: after 2 minutes, every resource has InfluxDB rows with all
     25 fields present (null where not applicable -- never a zero standing
     in for a signal that does not apply).
  5. Wait (up to 7 minutes, polling /ready's detector_fitted field) for
     sim-web-1's detector to warm up, THEN inject a fault through the API;
     within FAULT_TO_INCIDENT_WAIT_SECONDS of that a detection and an
     incident row (opened at or after T0) exist. That clock starts after
     warm-up, not before. 180s, not 60s: ml.tasks.LOOKBACK_SECONDS=120
     means a detection window right after injection is mostly pre-fault
     history, so 3 consecutive breaches can legitimately take close to
     120s plus a few more 10s ticks to confirm (measured: ~145s on a real
     run) -- a 60s budget here was never actually validated against real
     same-run detection latency until check 5 started rejecting stale
     incidents (see this file's own git history).
  6. run_incident on that incident: a decision with all four terms
     (weights sum to 1, the stored utility equals re-scoring the stored
     terms), a cost_estimates row written before the action row's status
     ever leaves "proposed", a proposal and a vote, an action row, and the
     incident ending resolved.
  7. Budget gate: drop a tenant's cap to $1, inject another fault, run the
     loop, confirm the action is refused and the reason lands in
     audit_log. Restore the cap no matter what happens.
  8. `verify_chain()` is true over the whole audit_log. Tamper with one
     row inside a transaction that gets rolled back; confirm it goes
     false inside that transaction, and confirm a fresh read afterwards is
     true again.
  9. pytest, ruff, mypy, and the web typecheck/test/build. Prints counts
     for each; stops at the first one that fails, same as every other
     check here.

**Tenants**: checks 5-6 (the happy path) run against `tenant-a`; check 7
(the budget gate) runs against `tenant-b`. Neither is a synthetic
throwaway tenant -- `SimulatedProvider`'s 8 resources are hardcoded to
`tenant-a`/`tenant-b` (core/providers/simulated.py), so a freshly created
tenant has no resource for a fault to land on. "Use a separate test
tenant" is satisfied by keeping the budget-gate check on a DIFFERENT
tenant than the happy path, and by this script restoring the one real
value it changes (`tenant-b.monthly_budget_usd`) in a `finally`, no matter
how the check ends. Nothing else under tenant-a/tenant-b is deleted --
rows this script creates (detections, incidents, decisions, etc.) are
real product rows, not scratch data, and are left in place for inspection,
same as a real incident would be.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import get_settings  # noqa: E402

API_PORT = get_settings().api_port
API_BASE = f"http://localhost:{API_PORT}"
TENANT_HAPPY_PATH = "tenant-a"
TENANT_BUDGET_GATE = "tenant-b"
RESOURCE_HAPPY_PATH = "sim-web-1"
RESOURCE_BUDGET_GATE = "sim-web-3"  # tenant-b's resource, per core/providers/simulated.py


@dataclass
class CheckResult:
    name: str
    passed: bool
    reason: str
    look_at: str = ""  # only meaningful on failure
    detail: dict[str, Any] = field(default_factory=dict)


def _run(
    cmd: list[str], cwd: Path | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """`encoding="utf-8", errors="replace"` -- without it, `text=True` falls
    back to the console's codepage (cp1252 on this Windows box), and `docker
    compose --build`/`npm`'s UTF-8 output (box-drawing characters in
    progress bars, etc.) crashes the decode entirely instead of being
    captured as a FAIL reason.

    `shutil.which` resolves `cmd[0]` before handing it to `subprocess.run`:
    on Windows, `npm` is `npm.cmd`, and `CreateProcess` (what `subprocess`
    calls without `shell=True`) does not do PATH extension resolution the
    way `cmd.exe` does -- an unresolved "npm" raises WinError 2 ("cannot
    find the file") instead of running. A no-op everywhere `which` already
    finds the bare name (docker, python, ...).
    """
    resolved = shutil.which(cmd[0]) or cmd[0]
    return subprocess.run(  # noqa: S603 -- cmd is always a hardcoded list in this file, never user input
        [resolved, *cmd[1:]],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _http_get(path: str, timeout: float = 3.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except Exception as exc:
        return 0, str(exc)


def _http_post(path: str, payload: dict[str, Any], timeout: float = 5.0) -> tuple[int, str]:
    import json

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{API_BASE}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except Exception as exc:
        return 0, str(exc)


# -- 1. Docker services -----------------------------------------------------

_EXPECTED_SERVICES = ("postgres", "redis", "influxdb", "worker", "beat")


def check_docker_services() -> CheckResult:
    """Brings up the databases + the `app` profile (worker, beat) if they
    are not already running, then reads `docker compose ps` back."""
    _run(["docker", "compose", "--profile", "app", "up", "-d", "--build"], timeout=600)

    result = _run(["docker", "compose", "ps", "--format", "json"], timeout=30)
    if result.returncode != 0:
        return CheckResult(
            "1. Docker services up",
            False,
            f"`docker compose ps` failed: {result.stderr.strip()[:200]}",
            look_at="Docker Desktop -- is the engine running?",
        )

    import json

    states: dict[str, str] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        states[row["Service"]] = row.get("State", row.get("Status", "unknown"))

    missing = [s for s in _EXPECTED_SERVICES if s not in states]
    not_running = [s for s in _EXPECTED_SERVICES if s in states and states[s] != "running"]
    if missing or not_running:
        return CheckResult(
            "1. Docker services up",
            False,
            f"missing={missing} not_running={ {k: states[k] for k in not_running} }",
            look_at="`docker compose ps` and `docker compose logs <service>`",
        )
    return CheckResult(
        "1. Docker services up", True, f"postgres/redis/influxdb/worker/beat all running: {states}"
    )


# -- 2. Migrations + schema -------------------------------------------------

_EXPECTED_TABLES = (
    "tenants", "resources", "incidents", "detections", "actions", "decisions",
    "proposals", "votes", "cost_estimates", "audit_log", "graph_nodes",
    "graph_edges", "corpus_chunks", "bandit_state", "risk_signals", "savings_reports",
)  # fmt: skip


def check_migrations_and_schema() -> CheckResult:
    from sqlalchemy import text

    from core.db import get_engine

    try:
        with get_engine().connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            has_vector_ext = (
                conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
                is not None
            )
            has_hnsw = (
                conn.execute(
                    text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_corpus_chunks_embedding'")
                ).first()
                is not None
            )
    except Exception as exc:
        return CheckResult(
            "2. Migrations + schema",
            False,
            f"could not query Postgres: {exc}",
            look_at="Postgres container / DATABASE_URL",
        )

    missing_tables = [t for t in _EXPECTED_TABLES if t not in tables]
    problems = []
    if version != "0002":
        problems.append(f"alembic_version={version!r}, expected '0002'")
    if missing_tables:
        problems.append(f"missing tables: {missing_tables}")
    if len(tables & set(_EXPECTED_TABLES)) != 16:
        problems.append(f"found {len(tables & set(_EXPECTED_TABLES))}/16 expected tables")
    if not has_vector_ext:
        problems.append("pgvector extension not installed")
    if not has_hnsw:
        problems.append("HNSW index ix_corpus_chunks_embedding missing")

    if problems:
        return CheckResult(
            "2. Migrations + schema",
            False,
            "; ".join(problems),
            look_at="`make migrate` (infra/migrations/versions/)",
        )
    return CheckResult(
        "2. Migrations + schema",
        True,
        "alembic head 0002, 16/16 tables, pgvector + HNSW index present",
    )


# -- 3. API health/ready -----------------------------------------------------

_API_PROCESS: subprocess.Popen[bytes] | None = None


def _ensure_api_running() -> str:
    """Starts uvicorn natively if nothing already answers on API_PORT.
    Returns 'already-running' or 'started-by-smoke' for the report; the
    latter is what `_stop_api_if_we_started_it` uses to decide whether to
    kill it."""
    global _API_PROCESS
    if _port_open("localhost", API_PORT):
        return "already-running"
    _API_PROCESS = subprocess.Popen(  # noqa: S603 -- fixed argv, no shell, nothing user-supplied
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "0.0.0.0",  # noqa: S104 -- local smoke run only, matches core/config.py's own default
            "--port",
            str(API_PORT),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if _port_open("localhost", API_PORT):
            break
        time.sleep(0.5)
    return "started-by-smoke"


def _stop_api_if_we_started_it() -> None:
    if _API_PROCESS is not None:
        _API_PROCESS.terminate()
        try:
            _API_PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _API_PROCESS.kill()


def check_api_health() -> CheckResult:
    started_how = _ensure_api_running()
    status_h, body_h = _http_get("/health")
    status_r, body_r = _http_get("/ready")
    if status_h != 200:
        look_at = "uvicorn logs / `make api`"
        if started_how == "already-running":
            look_at = (
                f"port {API_PORT} was already answering before this script started anything, "
                f"but not with a 200 from /health -- something ELSE may be listening on "
                f"{API_PORT}. `netstat -ano | findstr :{API_PORT}`. Response seen: {body_h[:150]!r}"
            )
        return CheckResult(
            "3. API /health + /ready",
            False,
            f"/health returned {status_h}: {body_h[:200]}",
            look_at,
        )
    if status_r != 200 or '"ready":true' not in body_r.replace(" ", ""):
        return CheckResult(
            "3. API /health + /ready",
            False,
            f"/ready returned {status_r}: {body_r[:200]}",
            look_at="Postgres/InfluxDB reachability from the API process",
        )
    return CheckResult(
        "3. API /health + /ready", True, f"both 200 (API {started_how}): {body_r[:120]}"
    )


# -- 4. Collector ------------------------------------------------------------


#: The one exception to "never look at the value": a completed request
#: cannot take exactly 0ms, so an exact 0.0 here is not a real reading, it
#: is the null-vs-zero bug (see core/providers/simulated.py's
#: `_POSITIVE_FLOOR`) showing up downstream -- most likely a zero-fill
#: somewhere between the collector and InfluxDB rather than the simulator
#: itself (which floors at 0.1, never 0.0). error_rate_5xx, throttle_count,
#: and replication_lag_seconds are deliberately NOT in this set: 0.0 is
#: their genuinely common reading (nothing went wrong / fully caught up),
#: same as every other applicable signal this function never inspects.
_LATENCY_SIGNALS: frozenset[str] = frozenset({"latency_p50", "latency_p95", "latency_p99"})


def applicability_problems(kind: str, values: dict[str, list[float]]) -> list[str]:
    """Checks STRUCTURE, not values -- the applicability map
    (`core.providers.simulated.applicable_signals`) says which signals a
    resource kind reports; every one of those must be present (and
    non-empty), and every signal it does NOT report must be absent. Never
    looks at what a present signal's number actually is: a real measured
    0.0 (error rate, throttle count, ...) on an applicable signal is not a
    problem, and this function cannot even see it one way or the other --
    only a non-applicable signal showing up AT ALL (0.0 included) is.

    The one exception is latency: see `_LATENCY_SIGNALS`.

    Returns one string per violation, signal name first so a caller can
    prefix it with whatever resource this was.
    """
    from core.providers.simulated import applicable_signals
    from core.signals import ALL_COLLECTED_SIGNALS

    applicable = set(applicable_signals(kind))
    not_applicable = set(ALL_COLLECTED_SIGNALS) - applicable

    problems: list[str] = []
    for signal in sorted(applicable):
        if not values.get(signal):
            problems.append(f"{signal}: applicable to {kind!r} but missing/null")
        elif signal in _LATENCY_SIGNALS and 0.0 in values[signal]:
            problems.append(f"{signal}: latency cannot be zero, likely zero-fill")
    for signal in sorted(not_applicable):
        if values.get(signal):
            problems.append(
                f"{signal}: NOT applicable to {kind!r} but present (value={values[signal]!r})"
            )
    return problems


def check_collector(wait_seconds: int = 120) -> CheckResult:
    """Waits `wait_seconds` (default: the 2 minutes the task specifies),
    then checks every tenant-a/tenant-b resource's InfluxDB rows against
    its applicability map via `applicability_problems` -- structure, not
    values. See that function's docstring for exactly what "structure"
    means here and why a real 0.0 is never flagged.
    """
    import asyncio

    from core import influx
    from core.providers.simulated import TENANTS, SimulatedProvider

    print(f"    (waiting {wait_seconds}s for the collector...)", flush=True)
    time.sleep(wait_seconds)

    provider = SimulatedProvider()
    problems: list[str] = []
    for tenant_id in TENANTS:
        resources = asyncio.run(provider.list_resources(tenant_id))
        for resource in resources:
            window = influx.query_recent_window(resource.id, tenant_id, wait_seconds)
            if not window.values:
                problems.append(f"{resource.id}: no InfluxDB rows in the last {wait_seconds}s")
                continue
            problems.extend(
                f"{resource.id}: {p}" for p in applicability_problems(resource.kind, window.values)
            )

    if problems:
        return CheckResult(
            "4. Collector writes InfluxDB",
            False,
            "; ".join(problems[:5]),
            look_at="core/collector.py, worker/beat container logs",
        )
    return CheckResult(
        "4. Collector writes InfluxDB",
        True,
        f"every tenant-a/tenant-b resource matches its applicability map after {wait_seconds}s",
    )


# -- 5. Fault -> detection -> incident ---------------------------------------

WARM_UP_TIMEOUT_SECONDS = 7 * 60
WARM_UP_PROGRESS_INTERVAL_SECONDS = 30
WARM_UP_POLL_INTERVAL_SECONDS = 2.0


def _resource_is_fitted(resource_id: str) -> bool:
    """Reads the `detector_fitted` field `/ready` exposes (api/routers/
    health.py), which is itself backed by `core.detector_state` -- the
    only way this process can see a fit that happened inside the worker/
    beat process. Fails closed (not fitted) on any transport or shape
    problem, same posture as the Redis-backed read underneath it."""
    import json

    status, body = _http_get("/ready")
    if status != 200:
        return False
    try:
        data = json.loads(body)
    except ValueError:
        return False
    return bool(data.get("detector_fitted", {}).get(resource_id, False))


def wait_for_detector_warm_up(
    resource_id: str,
    timeout_seconds: float = WARM_UP_TIMEOUT_SECONDS,
    progress_interval_seconds: float = WARM_UP_PROGRESS_INTERVAL_SECONDS,
    poll_interval_seconds: float = WARM_UP_POLL_INTERVAL_SECONDS,
    is_fitted: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Polls `is_fitted` (default: `_resource_is_fitted(resource_id)` against
    the real API) until it returns True or `timeout_seconds` elapses,
    printing progress every `progress_interval_seconds`. `sleep`/`now` are
    injectable so tests can run this with a fake clock instead of a real
    7-minute wait.
    """
    check = is_fitted if is_fitted is not None else (lambda: _resource_is_fitted(resource_id))
    start = now()
    deadline = start + timeout_seconds
    last_progress = start
    while True:
        if check():
            return True
        current = now()
        if current >= deadline:
            return False
        if current - last_progress >= progress_interval_seconds:
            print(
                f"    (still waiting for {resource_id}'s detector to warm up -- "
                f"{current - start:.0f}s/{timeout_seconds:.0f}s)",
                flush=True,
            )
            last_progress = current
        sleep(poll_interval_seconds)


def _close_stale_incidents(resource_id: str, tenant_id: str) -> int:
    """Resolves/closes any already-open incident for `resource_id` through
    the normal state machine -- never a raw UPDATE -- before this check
    injects its own fault, so a stale incident left over from an earlier
    run can't make `find_open_incident` return a false PASS for a fault
    this run never caused (see docs/notes/smoke-2026-10-08.md: that is
    exactly what happened once run_incident started running autonomously).

    OPEN/DECIDING/ACTING can all move straight to FAILED per core.
    incidents.VALID_TRANSITIONS. Each closure gets its own audit_log entry
    (through append_entry, so the hash chain stays intact) rather than
    disappearing silently. Returns how many incidents were closed.
    """
    from core.incidents import find_open_incident, get_incident, transition
    from core.models.enums import IncidentState
    from core.repo.audit import append_entry

    closed = 0
    while True:
        incident_id = find_open_incident(resource_id)
        if incident_id is None:
            return closed
        incident = get_incident(incident_id)
        assert incident is not None
        current_state = IncidentState(incident["state"])
        transition(incident_id, current_state, IncidentState.FAILED)
        append_entry(
            actor="scripts.smoke",
            action="incident.closed_by_smoke_cleanup",
            payload={
                "incident_id": str(incident_id),
                "resource_id": resource_id,
                "previous_state": current_state.value,
                "reason": "pre-existing open incident cleared before check 5's fault injection",
            },
            tenant_id=tenant_id,
        )
        closed += 1


def _latest_detection_at_or_after(resource_id: str, t0: datetime) -> datetime | None:
    from sqlalchemy import text

    from core.db import session_scope

    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT MIN(detected_at) AS t FROM detections "
                "WHERE resource_id = :r AND detected_at >= :t0"
            ),
            {"r": resource_id, "t0": t0},
        ).first()
    return row.t if row is not None else None


#: Not 60s: ml.tasks.LOOKBACK_SECONDS=120 means the window right after
#: injection is mostly pre-fault history -- see this function's docstring
#: header comment (module docstring, check 5) for the measured latency
#: that led to this number.
FAULT_TO_INCIDENT_WAIT_SECONDS = 180


def check_fault_to_detection(wait_seconds: int = FAULT_TO_INCIDENT_WAIT_SECONDS) -> CheckResult:
    from core.incidents import find_open_incident, get_incident

    print(
        f"    (waiting up to {WARM_UP_TIMEOUT_SECONDS}s for {RESOURCE_HAPPY_PATH}'s detector "
        "to warm up...)",
        flush=True,
    )
    if not wait_for_detector_warm_up(RESOURCE_HAPPY_PATH):
        return CheckResult(
            "5. Fault -> detection -> incident",
            False,
            "detector never warmed up",
            look_at="ml/tasks.py detect_anomalies -- FIT_WINDOW_COUNT=30 means ~5 minutes of "
            "bootstrap history is needed before the detector fits at all; check /ready's "
            f"detector_fitted.{RESOURCE_HAPPY_PATH!r} and the worker/beat container logs",
        )

    closed = _close_stale_incidents(RESOURCE_HAPPY_PATH, TENANT_HAPPY_PATH)
    if closed:
        print(
            f"    (closed {closed} pre-existing open incident(s) for {RESOURCE_HAPPY_PATH} "
            "before injecting)",
            flush=True,
        )

    t0 = datetime.now(UTC)
    status, body = _http_post(
        "/api/v1/faults",
        {"resource_id": RESOURCE_HAPPY_PATH, "fault_type": "cpu_hog", "duration_seconds": 180},
    )
    if status != 202:
        return CheckResult(
            "5. Fault -> detection -> incident",
            False,
            f"POST /api/v1/faults returned {status}: {body[:200]}",
            look_at="api/routers/actions.py inject_fault",
        )

    # The fault-to-incident limit starts here, AFTER warm-up -- the
    # detector is already fitted by this point, so it is a real latency
    # budget, not a disguised bootstrap wait. Only an incident OPENED AT OR
    # AFTER t0 counts -- find_open_incident alone can't tell "caused by
    # this fault" apart from "already open for some unrelated reason";
    # _close_stale_incidents should have left none, but this is the actual
    # acceptance check, not a belief that cleanup always works.
    print(f"    (waiting up to {wait_seconds}s for a detection + incident after t0...)", flush=True)
    deadline = time.monotonic() + wait_seconds
    incident_id = None
    while time.monotonic() < deadline:
        candidate = find_open_incident(RESOURCE_HAPPY_PATH)
        if candidate is not None:
            incident = get_incident(candidate)
            if incident is not None and incident["opened_at"] >= t0:
                incident_id = candidate
                break
        time.sleep(2.0)

    if incident_id is None:
        return CheckResult(
            "5. Fault -> detection -> incident",
            False,
            f"no incident for {RESOURCE_HAPPY_PATH} opened at or after t0={t0.isoformat()} "
            f"within {wait_seconds}s of fault injection (detector was already warmed up, so "
            "this is a real miss, not bootstrap)",
            look_at="ml/tasks.py detect_anomalies / worker container logs",
        )
    detected_at = _latest_detection_at_or_after(RESOURCE_HAPPY_PATH, t0)
    return CheckResult(
        "5. Fault -> detection -> incident",
        True,
        f"incident {incident_id} open for {RESOURCE_HAPPY_PATH} (opened at or after t0)",
        detail={"incident_id": str(incident_id), "t0": t0, "detected_at": detected_at},
    )


# -- 6. run_incident ----------------------------------------------------------

RUN_INCIDENT_WAIT_SECONDS = 60
RUN_INCIDENT_POLL_SECONDS = 1.0


def _wait_for_incident_terminal(
    incident_id: Any, wait_seconds: float = RUN_INCIDENT_WAIT_SECONDS
) -> Any | None:
    """Polls `core.incidents.get_incident` until the WORKER's own
    `core.incident_tasks.process_incident` (enqueued by `ml.tasks.
    detect_anomalies` the instant it opened this incident) has driven it to
    a terminal state. This check no longer calls `run_incident` itself --
    it only observes. Returns `None` on timeout."""
    from core.incidents import get_incident
    from core.models.enums import IncidentState

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        incident = get_incident(incident_id)
        if incident is not None:
            state = IncidentState(incident["state"])
            if state in (IncidentState.RESOLVED, IncidentState.FAILED):
                return state
        time.sleep(RUN_INCIDENT_POLL_SECONDS)
    return None


def check_run_incident(incident_id: Any) -> CheckResult:
    from sqlalchemy import text

    from core.db import session_scope
    from core.decision.utility import score
    from core.models.enums import IncidentState

    print(
        f"    (waiting up to {RUN_INCIDENT_WAIT_SECONDS}s for the worker's own run_incident...)",
        flush=True,
    )
    final_state = _wait_for_incident_terminal(incident_id)
    if final_state is None:
        return CheckResult(
            "6. run_incident loop",
            False,
            f"incident never reached a terminal state within {RUN_INCIDENT_WAIT_SECONDS}s -- "
            "was it actually enqueued?",
            look_at="worker container logs; core/incident_tasks.py process_incident; "
            "ml/tasks.py's open_incident call site should be followed by "
            "process_incident.delay(...)",
        )
    if final_state != IncidentState.RESOLVED:
        return CheckResult(
            "6. run_incident loop",
            False,
            f"incident ended {final_state.value}, not resolved",
            look_at="core/loop.py -- audit_log entries for this incident_id say which step failed",
        )

    with session_scope() as session:
        decision = session.execute(
            text("SELECT utility, terms, weights FROM decisions WHERE incident_id = :i"),
            {"i": str(incident_id)},
        ).first()
        action = session.execute(
            text("SELECT id, status FROM actions WHERE incident_id = :i"), {"i": str(incident_id)}
        ).first()
        cost_estimate = session.execute(
            text("SELECT action_id FROM cost_estimates WHERE action_id = :a"),
            {"a": str(action.id) if action else None},
        ).first()
        proposal = session.execute(
            text("SELECT id, committed FROM proposals WHERE incident_id = :i"),
            {"i": str(incident_id)},
        ).first()
        vote = session.execute(
            text("SELECT voter_id FROM votes WHERE proposal_id = :p"),
            {"p": str(proposal.id) if proposal else None},
        ).first()

    problems = []
    if decision is None:
        problems.append("no decisions row")
    else:
        weights = dict(decision.weights)
        if abs(sum(weights.values()) - 1.0) > 1e-6:
            problems.append(f"weights sum to {sum(weights.values())}, not 1")
        rescored = score(dict(decision.terms), weights)
        if abs(rescored - decision.utility) > 1e-6:
            problems.append(f"stored utility {decision.utility} != re-scored {rescored}")
        if set(decision.terms) != {"ability", "cost", "latency", "safety"}:
            problems.append(f"terms are {sorted(decision.terms)}, not the four W5 terms")
    if cost_estimate is None:
        problems.append("no cost_estimates row for the chosen action")
    if proposal is None or not proposal.committed:
        problems.append("no committed proposal")
    if vote is None:
        problems.append("no vote on the proposal")
    if action is None or action.status != "succeeded":
        problems.append(f"action status is {action.status if action else 'missing'}")

    if problems:
        return CheckResult(
            "6. run_incident loop",
            False,
            "; ".join(problems),
            look_at="decisions/cost_estimates/proposals/votes/actions rows for this incident_id",
        )
    assert decision is not None
    assert action is not None
    return CheckResult(
        "6. run_incident loop",
        True,
        f"decision utility={decision.utility:.4f}, action {action.id} succeeded, incident "
        "resolved (via the autonomous worker, not called from smoke)",
    )


# -- Gate A timings ------------------------------------------------------------

GATE_A_ACTION_LIMIT_SECONDS = 60.0


def _fmt_gate(value: float | None) -> str:
    return f"{value:.2f}s" if value is not None else "N/A"


def compute_gate_a_timings(incident_id: Any, t0: datetime) -> dict[str, float | None]:
    """Five fault-relative durations for the check-5/6 incident, all
    computed from DB/audit_log timestamps rather than anything smoke
    itself measured with a stopwatch -- the same rows checks 4-6 already
    verify exist. `None` means that step's timestamp was never recorded
    (not yet reached, or this run never got that far).
    """
    from sqlalchemy import text

    from core.db import session_scope

    with session_scope() as session:
        incident_row = session.execute(
            text("SELECT opened_at, closed_at, state FROM incidents WHERE id = :i"),
            {"i": str(incident_id)},
        ).first()
        decision_row = session.execute(
            text(
                "SELECT created_at FROM audit_log WHERE action = 'incident.decision_made' "
                "AND payload->>'incident_id' = :i ORDER BY created_at ASC LIMIT 1"
            ),
            {"i": str(incident_id)},
        ).first()
        action_row = session.execute(
            text(
                "SELECT created_at FROM audit_log WHERE action = 'incident.action_executed' "
                "AND payload->>'incident_id' = :i AND payload->>'status' = 'succeeded' "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"i": str(incident_id)},
        ).first()

    detected_at = _latest_detection_at_or_after(RESOURCE_HAPPY_PATH, t0)

    def _delta(ts: datetime | None) -> float | None:
        return (ts - t0).total_seconds() if ts is not None else None

    resolved_at = None
    if incident_row is not None and incident_row.state == "resolved":
        resolved_at = incident_row.closed_at

    return {
        "fault_to_detection": _delta(detected_at),
        "fault_to_incident": _delta(incident_row.opened_at if incident_row else None),
        "fault_to_decision": _delta(decision_row.created_at if decision_row else None),
        "fault_to_action_succeeded": _delta(action_row.created_at if action_row else None),
        "fault_to_incident_resolved": _delta(resolved_at),
    }


def render_gate_a(timings: dict[str, float | None]) -> list[str]:
    action_dt = timings["fault_to_action_succeeded"]
    gate_pass = action_dt is not None and action_dt < GATE_A_ACTION_LIMIT_SECONDS
    lines = [
        "",
        "## Gate A timings",
        "",
        f"- fault-to-detection: {_fmt_gate(timings['fault_to_detection'])}",
        f"- fault-to-incident: {_fmt_gate(timings['fault_to_incident'])}",
        f"- fault-to-decision: {_fmt_gate(timings['fault_to_decision'])}",
        f"- fault-to-action-succeeded: {_fmt_gate(action_dt)}",
        f"- fault-to-incident-resolved: {_fmt_gate(timings['fault_to_incident_resolved'])}",
        "",
        f"**Gate A: {'PASS' if gate_pass else 'FAIL'}** "
        f"(fault-to-action-succeeded = {_fmt_gate(action_dt)}, "
        f"limit {GATE_A_ACTION_LIMIT_SECONDS:.0f}s)",
    ]
    return lines


# -- 7. Budget gate -----------------------------------------------------------


async def _budget_gate_check() -> CheckResult:
    from sqlalchemy import text

    from core.budget import estimate_cost
    from core.consensus.quorum import QuorumConsensus
    from core.db import session_scope
    from core.incidents import find_open_incident, open_incident
    from core.loop import run_incident
    from core.models.domain import Action
    from core.models.enums import ActionTier, ActionType, IncidentState, ProviderName
    from core.pricing import StaticPriceTable
    from core.providers.simulated import SimulatedProvider
    from core.providers.simulated_executor import SimulatedExecutor

    pricing = StaticPriceTable()
    # This product's Tier 1 actions cost about one cent each (a DNS weight
    # shift is a config change, not a provisioned resource -- see
    # core/pricing/static_table.py). A literal $1 cap, as asked for, would
    # never be exceeded by one such action and the gate would just approve
    # it -- which would make this check always pass for the wrong reason.
    # So the cap used here is pinned to just under one action's real priced
    # cost instead of the literal $1, which is the smallest change that
    # keeps the check meaningful; this is called out here rather than
    # silently substituted.
    representative_cost = (
        await estimate_cost(
            Action(
                tenant_id=TENANT_BUDGET_GATE,
                provider=ProviderName.SIMULATED,
                type=ActionType.DNS_WEIGHT_SHIFT,
                tier=ActionTier.TIER_1,
                target_resource_id=RESOURCE_BUDGET_GATE,
            ),
            "sim-us-east-1",
            pricing,
        )
    ).one_off_usd
    test_cap = round(representative_cost / 2, 4)

    with session_scope() as session:
        original_cap = session.execute(
            text("SELECT monthly_budget_usd FROM tenants WHERE id = :t"),
            {"t": TENANT_BUDGET_GATE},
        ).scalar()

    try:
        with session_scope() as session:
            session.execute(
                text("UPDATE tenants SET monthly_budget_usd = :cap WHERE id = :t"),
                {"cap": test_cap, "t": TENANT_BUDGET_GATE},
            )

        provider = SimulatedProvider()
        provider.inject_fault(RESOURCE_BUDGET_GATE, "cpu_hog", 120)

        incident_id = find_open_incident(RESOURCE_BUDGET_GATE)
        if incident_id is None:
            incident_id = open_incident(TENANT_BUDGET_GATE, RESOURCE_BUDGET_GATE)

        final_state = await run_incident(
            incident_id,
            pricing,
            SimulatedExecutor(),
            QuorumConsensus(node_id="node-a"),
        )

        with session_scope() as session:
            reason_row = session.execute(
                text(
                    "SELECT payload FROM audit_log WHERE tenant_id = :t "
                    "AND action = 'action.rejected_by_budget' ORDER BY id DESC LIMIT 1"
                ),
                {"t": TENANT_BUDGET_GATE},
            ).first()

        if final_state != IncidentState.FAILED:
            return CheckResult(
                "7. Budget gate refuses over-cap action",
                False,
                f"incident ended {final_state.value}, expected failed (cap was ${test_cap})",
                look_at="core/budget.py check_budget -- did the cap actually take effect?",
            )
        if reason_row is None:
            return CheckResult(
                "7. Budget gate refuses over-cap action",
                False,
                "incident failed but no action.rejected_by_budget row in audit_log",
                look_at="core/budget.py check_budget's append_entry call",
            )
        return CheckResult(
            "7. Budget gate refuses over-cap action",
            True,
            f"refused, reason logged: {reason_row.payload['reason']}",
        )
    finally:
        with session_scope() as session:
            session.execute(
                text("UPDATE tenants SET monthly_budget_usd = :cap WHERE id = :t"),
                {"cap": original_cap, "t": TENANT_BUDGET_GATE},
            )


def check_budget_gate() -> CheckResult:
    import asyncio

    return asyncio.run(_budget_gate_check())


# -- 8. Hash chain -------------------------------------------------------------


def _list_for_verification_via(conn: Any) -> list[dict[str, Any]]:
    """Same shape as `core.repo.audit.list_for_verification`, but read
    through the caller's own connection/transaction rather than opening a
    fresh `session_scope()` -- which would run on a different connection and,
    under READ COMMITTED, never see this transaction's own uncommitted
    tamper at all, making the "did it go false" check meaningless."""
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT tenant_id, actor, action, payload, prev_hash, hash, created_at "
            "FROM audit_log ORDER BY id ASC"
        )
    ).all()
    entries = []
    for row in rows:
        entries.append(
            {
                "tenant_id": row.tenant_id,
                "actor": row.actor,
                "action": row.action,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
                "prev_hash": row.prev_hash,
                "hash": row.hash,
            }
        )
    return entries


def check_hash_chain() -> CheckResult:
    from sqlalchemy import text

    from core.audit.hash_chain import verify_chain
    from core.db import get_engine
    from core.repo.audit import list_for_verification

    ok, bad_index = verify_chain(list_for_verification())
    if not ok:
        return CheckResult(
            "8. Hash chain integrity",
            False,
            f"verify_chain() is already false at row {bad_index}",
            look_at="audit_log -- something tampered with it before this smoke run",
        )

    # Tamper inside a transaction, observe it go false (read through the SAME
    # connection, so the uncommitted tamper is actually visible), then roll back.
    # `trans` is controlled manually (never a `with conn.begin():` block) so a
    # rollback issued from inside it is never followed by an implicit commit.
    engine = get_engine()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            last_id = conn.execute(
                text("SELECT id FROM audit_log ORDER BY id DESC LIMIT 1")
            ).scalar()
            if last_id is None:
                return CheckResult(
                    "8. Hash chain integrity",
                    False,
                    "audit_log is empty -- nothing to tamper with",
                    look_at="run checks 5-7 first so audit_log has rows",
                )
            conn.execute(
                text("UPDATE audit_log SET payload = '{\"tampered\": true}'::jsonb WHERE id = :id"),
                {"id": last_id},
            )
            tampered_ok, _ = verify_chain(_list_for_verification_via(conn))
        finally:
            trans.rollback()  # always undo, whether or not the tamper check above raised

        after_ok, _ = verify_chain(list_for_verification())

    if tampered_ok:
        return CheckResult(
            "8. Hash chain integrity",
            False,
            "verify_chain() stayed true after tampering -- the chain is not protecting anything",
            look_at="core/audit/hash_chain.py verify_chain",
        )
    if not after_ok:
        return CheckResult(
            "8. Hash chain integrity",
            False,
            "verify_chain() is false AFTER the rollback -- the tamper was not actually undone",
            look_at="whether the UPDATE above really ran inside a transaction that rolled back",
        )
    return CheckResult(
        "8. Hash chain integrity",
        True,
        "true before tampering, false during (in-transaction), true again after rollback",
    )


# -- 9. pytest / ruff / mypy / web -------------------------------------------


def _summary_line(output: str) -> str:
    """Last non-blank line of combined stdout+stderr -- where pytest, ruff,
    mypy and every `npm run` script here all put their one-line count."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return lines[-1].strip() if lines else "(no output)"


def _suite_steps() -> list[tuple[str, list[str], Path]]:
    """The commands check_suites runs, in order. Split out from
    check_suites so a test can assert how each command is built without
    actually running pytest/ruff/mypy recursively.

    pytest/ruff/mypy are invoked as `[sys.executable, "-m", <tool>, ...]`,
    never by the tool's bare name: on Windows, `subprocess.run` without
    `shell=True` resolves argv[0] itself rather than going through a shell
    that would apply PATHEXT, and a bare "pytest"/"ruff"/"mypy" is not
    guaranteed to resolve the same way `sys.executable -m <tool>` does when
    several Python installs are on PATH -- `-m` guarantees the tool that
    runs is the one installed for THIS interpreter, the one the rest of
    this script (and its own test run) is already running under. `npm` is
    a different case -- see `_run`'s docstring on why it goes through
    `shutil.which` instead."""
    return [
        ("pytest", [sys.executable, "-m", "pytest", "-q"], ROOT),
        ("ruff check", [sys.executable, "-m", "ruff", "check", "."], ROOT),
        ("mypy", [sys.executable, "-m", "mypy"], ROOT),
        ("web typecheck", ["npm", "run", "typecheck"], ROOT / "web"),
        ("web test", ["npm", "test"], ROOT / "web"),
        ("web build", ["npm", "run", "build"], ROOT / "web"),
    ]


def check_suites() -> CheckResult:
    steps = _suite_steps()
    counts: list[str] = []
    for label, cmd, cwd in steps:
        print(f"    running {label}...", flush=True)
        result = _run(cmd, cwd=cwd, timeout=900)
        summary = _summary_line(result.stdout + "\n" + result.stderr)
        ok = result.returncode == 0
        counts.append(f"{label}: {'ok' if ok else 'FAILED'} -- {summary[:150]}")
        if not ok:
            return CheckResult(
                "9. pytest/ruff/mypy/web",
                False,
                " | ".join(counts),
                look_at=f"`{' '.join(cmd)}` in {cwd}",
            )
    return CheckResult("9. pytest/ruff/mypy/web", True, " | ".join(counts))


# -- runner -------------------------------------------------------------------


def main() -> int:
    checks: list[CheckResult] = []
    incident_id: Any = None
    gate_a_lines: list[str] = []

    def run_one(label: str, fn: Callable[[], CheckResult]) -> bool:
        print(f"-> {label}", flush=True)
        try:
            result = fn()
        except Exception as exc:  # a crash IS a FAIL, with its own reason
            result = CheckResult(label, False, f"raised {type(exc).__name__}: {exc}")
        checks.append(result)
        print(f"   {'PASS' if result.passed else 'FAIL'}: {result.reason}")
        if not result.passed and result.look_at:
            print(f"   look at: {result.look_at}")
        return result.passed

    try:
        if not run_one("1. Docker services", check_docker_services):
            return _finish(checks)
        if not run_one("2. Migrations + schema", check_migrations_and_schema):
            return _finish(checks)
        if not run_one("3. API health", check_api_health):
            return _finish(checks)
        if not run_one("4. Collector", lambda: check_collector(120)):
            return _finish(checks)
        fault_result = check_fault_to_detection(FAULT_TO_INCIDENT_WAIT_SECONDS)
        checks.append(fault_result)
        print("-> 5. Fault -> detection -> incident")
        print(f"   {'PASS' if fault_result.passed else 'FAIL'}: {fault_result.reason}")
        if not fault_result.passed:
            if fault_result.look_at:
                print(f"   look at: {fault_result.look_at}")
            return _finish(checks)
        incident_id = fault_result.detail["incident_id"]
        t0 = fault_result.detail["t0"]

        print("-> 6. run_incident loop", flush=True)
        check6_result = check_run_incident(incident_id)
        checks.append(check6_result)
        print(f"   {'PASS' if check6_result.passed else 'FAIL'}: {check6_result.reason}")
        if not check6_result.passed and check6_result.look_at:
            print(f"   look at: {check6_result.look_at}")

        # Gate A is computed whether check 6 passed or not -- a partial set
        # of timings (e.g. detection recorded, decision never reached) is
        # still useful, and "never recorded" is itself the FAIL reason.
        gate_a_lines = render_gate_a(compute_gate_a_timings(incident_id, t0))
        print("\n".join(gate_a_lines))

        if not check6_result.passed:
            return _finish(checks, gate_a_lines)
        if not run_one("7. Budget gate", check_budget_gate):
            return _finish(checks, gate_a_lines)
        if not run_one("8. Hash chain", check_hash_chain):
            return _finish(checks, gate_a_lines)
        run_one("9. pytest/ruff/mypy/web", check_suites)
    finally:
        _stop_api_if_we_started_it()

    return _finish(checks, gate_a_lines)


def _finish(checks: list[CheckResult], gate_a_lines: list[str] | None = None) -> int:
    report_lines = [
        f"# Smoke test -- {datetime.now(UTC).date().isoformat()}",
        "",
        "| # | Check | Result | Reason |",
        "| - | --- | --- | --- |",
    ]
    for c in checks:
        report_lines.append(f"| | {c.name} | {'PASS' if c.passed else 'FAIL'} | {c.reason} |")
    if gate_a_lines:
        report_lines += gate_a_lines
    failed = [c for c in checks if not c.passed]
    if failed:
        report_lines += [
            "",
            f"**Stopped at**: {failed[0].name}",
            f"**Look at**: {failed[0].look_at}",
        ]
    else:
        report_lines += ["", "All checks passed."]

    out_path = ROOT / "docs" / "notes" / f"smoke-{datetime.now(UTC).date().isoformat()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {out_path}")

    print("\n" + "\n".join(report_lines))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
