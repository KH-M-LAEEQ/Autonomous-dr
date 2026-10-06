"""Episode generator -- the data factory for the simulator practice run.

Produces a versioned, immutable dataset under `ml/datasets/<version>/`:

    windows.jsonl        one rolling MetricWindow per resource per tick
    labels.jsonl         one ground-truth row per injected fault episode
    labels.schema.json   the label format, per ml/datasets/README.md
    manifest.json        seed, metric-list version, date, episode count

The loop is: `--normal-minutes` of clean telemetry, one random fault injected
through the real `core.faults` API, the fault's exact start/end/type/target
appended to labels.jsonl, the fault cleared, `--recover-minutes` of settling,
then the next episode.

Three things about how this runs that matter when you read the numbers:

**Virtual clock, not real sleeping.** Ten simulated minutes per episode would
make a 20-episode run take over three hours of wall clock. Instead a virtual
clock advances `--step-seconds` per tick and `core.providers.simulated`'s
`datetime` is pointed at it for the duration of the run. That is a local patch
in this file -- `core/providers/simulated.py` is not modified -- and it is what
makes the generated data carry a real daily seasonality curve instead of all
samples landing in the same wall-clock minute.

**Fault windows are closed by `clear_fault`, not by the Redis TTL.** The TTL in
`faults.set_fault` expires in real seconds, which means nothing to a virtual
clock, so faults are set with a long TTL and ended explicitly at the exact
virtual tick the episode says they end. The label is therefore authoritative.

**`region_down` affects more than its target.** A region-wide fault injected
against one resource takes down every resource in that region, across tenants
(`SimulatedProvider._region_fault`). Each label records both the `target` it was
injected against and the full `affected` list, so a scorer can label every
genuinely-degraded resource rather than counting the collateral ones as false
positives.

Only the five fault types `SimulatedProvider` actually implements are used
(`cpu_hog`, `latency`, `stop`, `pause`, `region_down`). There is no
`memory_leak` or `network_loss` in the simulator, and this script does not
invent one -- an injected fault and its label always refer to the same thing.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Any

from core import faults
from core.models.domain import Resource
from core.providers import simulated as simulated_module
from core.providers.simulated import FAULT_TYPES, SimulatedProvider
from core.signals import ALL_COLLECTED_SIGNALS, CANONICAL_SIGNALS, RESERVE_SIGNALS

# Long enough that the TTL never fires mid-episode; `clear_fault` ends the
# window instead. See the module docstring.
_FAULT_TTL_SECONDS = 86_400

_DATA_FILES = ("windows.jsonl", "labels.jsonl", "manifest.json", "labels.schema.json")

_LABEL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Fault episode ground truth",
    "description": (
        "One row per injected fault. `start`/`end` are the exact virtual-clock "
        "bounds of the fault window. A window overlapping [start, end) for a "
        "resource listed in `affected` is anomalous; everything else is normal."
    ),
    "type": "object",
    "required": ["episode", "fault_type", "target", "affected", "start", "end"],
    "additionalProperties": False,
    "properties": {
        "episode": {"type": "integer", "minimum": 0},
        "fault_type": {"type": "string", "enum": list(FAULT_TYPES)},
        "target": {"type": "string", "description": "resource the fault was injected against"},
        "tenant_id": {"type": "string"},
        "region": {"type": "string"},
        "affected": {
            "type": "array",
            "items": {"type": "string"},
            "description": "every resource degraded by this fault, including `target`",
        },
        "start": {"type": "string", "format": "date-time"},
        "end": {"type": "string", "format": "date-time"},
        "duration_seconds": {"type": "integer", "minimum": 1},
    },
}


class _VirtualClock:
    """The run's only source of time. Advances in `step_seconds` jumps."""

    def __init__(self, start: datetime) -> None:
        self.value = start

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class _ClockDatetime:
    """Stands in for `datetime` inside `core.providers.simulated` so its
    seasonality curve and `observed_at` follow the virtual clock.

    Only `.now()` is used by that module; `simulated.py` has
    `from __future__ import annotations`, so its `datetime` annotations are
    strings and never evaluated against this stub.
    """

    def __init__(self, clock: _VirtualClock) -> None:
        self._clock = clock

    def now(self, tz: Any = None) -> datetime:
        return self._clock.value


def _install_memory_fault_store() -> None:
    """Replace `core.faults`' Redis calls with an in-process dict.

    Same technique as core/tests/test_simulated_provider.py. Opt-in via
    `--fault-store memory`; there is no silent fallback, because a run that
    quietly injected no faults would produce an all-normal dataset whose
    labels claim otherwise.
    """
    store: dict[str, str] = {}

    def set_fault(resource_id: str, fault_type: str, duration_seconds: int) -> None:
        store[resource_id] = fault_type

    def get_fault(resource_id: str) -> str | None:
        return store.get(resource_id)

    def clear_fault(resource_id: str) -> None:
        store.pop(resource_id, None)

    faults.set_fault = set_fault  # type: ignore[assignment]
    faults.get_fault = get_fault  # type: ignore[assignment]
    faults.clear_fault = clear_fault  # type: ignore[assignment]


def _check_redis_reachable() -> None:
    """Fail fast with an actionable message rather than mid-run."""
    probe = "__make_episodes_probe__"
    try:
        faults.set_fault(probe, "cpu_hog", 5)
        faults.clear_fault(probe)
    except Exception as exc:
        sys.exit(
            f"redis is not reachable ({type(exc).__name__}), so the real fault API "
            f"cannot be used.\nStart it with `make up`, or re-run with "
            f"`--fault-store memory` to inject faults in-process instead."
        )


def _metric_list_version() -> dict[str, Any]:
    """Identifies the exact signal list this dataset was built against, so a
    later change to `core/signals.py` is detectable rather than silent."""
    joined = ",".join(ALL_COLLECTED_SIGNALS)
    return {
        "source": "core.signals.ALL_COLLECTED_SIGNALS",
        "spec": "docs/metric-schema.md",
        "canonical_count": len(CANONICAL_SIGNALS),
        "reserve_count": len(RESERVE_SIGNALS),
        "count": len(ALL_COLLECTED_SIGNALS),
        "sha256": hashlib.sha256(joined.encode()).hexdigest()[:16],
    }


def _generator_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 -- git from PATH; fixed argv, no shell
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


async def _all_resources(provider: SimulatedProvider) -> list[Resource]:
    """Every resource across both simulator tenants, in a stable order."""
    seen: dict[str, Resource] = {}
    for tenant in simulated_module.TENANTS:
        for resource in await provider.list_resources(tenant):
            seen[resource.id] = resource
    return [seen[rid] for rid in sorted(seen)]


def _affected_by(fault_type: str, target: Resource, resources: list[Resource]) -> list[str]:
    """`region_down` degrades its whole region across tenants; everything else
    is confined to the resource it was injected against."""
    if fault_type == "region_down":
        return sorted(r.id for r in resources if r.region == target.region)
    return [target.id]


async def _tick(
    provider: SimulatedProvider,
    resources: list[Resource],
    clock: _VirtualClock,
    history: dict[str, dict[str, list[float]]],
    windows_out: IO[str],
    step_seconds: int,
    window_samples: int,
) -> int:
    """One collector cycle: sample every resource, emit a window per resource
    whose history is full. Returns the number of windows written."""
    written = 0
    for resource in resources:
        report = await provider.get_health(resource.id)
        if not report.signals:
            continue
        # Only the signals this resource actually reports. A signal that does
        # not apply to its kind is absent from `report.signals` and stays
        # absent here -- absent is null, and null is never 0.0
        # (core/signals.py). So a worker's windows simply have no
        # `request_rate` key, rather than a column of fake zeroes.
        series_by_signal = history.setdefault(resource.id, {})
        for signal in ALL_COLLECTED_SIGNALS:
            value = report.signals.get(signal)
            if value is None:
                continue
            series = series_by_signal.setdefault(signal, [])
            series.append(round(float(value), 4))
            if len(series) > window_samples:
                del series[0]

        if not series_by_signal:
            continue
        if min(len(s) for s in series_by_signal.values()) < window_samples:
            continue

        end = clock.value
        start = end - timedelta(seconds=step_seconds * (window_samples - 1))
        windows_out.write(
            json.dumps(
                {
                    "resource_id": resource.id,
                    "tenant_id": resource.tenant_id,
                    "region": resource.region,
                    "kind": resource.kind,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "step_seconds": step_seconds,
                    "values": {s: list(v) for s, v in series_by_signal.items()},
                }
            )
            + "\n"
        )
        written += 1
    return written


async def _phase(
    ticks: int,
    provider: SimulatedProvider,
    resources: list[Resource],
    clock: _VirtualClock,
    history: dict[str, dict[str, list[float]]],
    windows_out: IO[str],
    step_seconds: int,
    window_samples: int,
) -> int:
    written = 0
    for _ in range(ticks):
        written += await _tick(
            provider, resources, clock, history, windows_out, step_seconds, window_samples
        )
        clock.advance(step_seconds)
    return written


async def generate(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    """Run every episode and write windows.jsonl + labels.jsonl. Returns the
    manifest body."""
    rng = random.Random(args.seed)  # noqa: S311 -- simulation reproducibility, not crypto
    # core.providers.simulated draws from the global `random` module, so the
    # global seed is what makes the telemetry itself reproducible.
    random.seed(args.seed)

    clock = _VirtualClock(datetime.fromisoformat(args.start).astimezone(UTC))
    provider = SimulatedProvider()
    resources = await _all_resources(provider)

    normal_ticks = max(1, round(args.normal_minutes * 60 / args.step_seconds))
    recover_ticks = max(1, round(args.recover_minutes * 60 / args.step_seconds))

    history: dict[str, dict[str, list[float]]] = {}
    labels: list[dict[str, Any]] = []
    window_count = 0
    first_tick = clock.value

    original_datetime = simulated_module.datetime
    simulated_module.datetime = _ClockDatetime(clock)  # type: ignore[assignment]
    try:
        with (out_dir / "windows.jsonl").open("w", encoding="utf-8", newline="\n") as windows_out:
            for episode in range(args.episodes):
                window_count += await _phase(
                    normal_ticks,
                    provider,
                    resources,
                    clock,
                    history,
                    windows_out,
                    args.step_seconds,
                    args.window_samples,
                )

                fault_type = rng.choice(FAULT_TYPES)
                target = rng.choice(resources)
                fault_seconds = rng.randrange(
                    args.fault_seconds_min,
                    args.fault_seconds_max + 1,
                    args.step_seconds,
                )
                fault_ticks = max(1, fault_seconds // args.step_seconds)

                provider.inject_fault(target.id, fault_type, _FAULT_TTL_SECONDS)
                fault_start = clock.value
                window_count += await _phase(
                    fault_ticks,
                    provider,
                    resources,
                    clock,
                    history,
                    windows_out,
                    args.step_seconds,
                    args.window_samples,
                )
                fault_end = clock.value
                faults.clear_fault(target.id)

                labels.append(
                    {
                        "episode": episode,
                        "fault_type": fault_type,
                        "target": target.id,
                        "tenant_id": target.tenant_id,
                        "region": target.region,
                        "affected": _affected_by(fault_type, target, resources),
                        "start": fault_start.isoformat(),
                        "end": fault_end.isoformat(),
                        "duration_seconds": fault_ticks * args.step_seconds,
                    }
                )
                print(
                    f"episode {episode:>3}: {fault_type:<11} on {target.id:<12} "
                    f"for {fault_ticks * args.step_seconds:>4}s"
                )

                window_count += await _phase(
                    recover_ticks,
                    provider,
                    resources,
                    clock,
                    history,
                    windows_out,
                    args.step_seconds,
                    args.window_samples,
                )
    finally:
        simulated_module.datetime = original_datetime  # type: ignore[assignment]
        for resource in resources:
            faults.clear_fault(resource.id)

    with (out_dir / "labels.jsonl").open("w", encoding="utf-8", newline="\n") as labels_out:
        for row in labels:
            labels_out.write(json.dumps(row) + "\n")

    return {
        "version": args.version,
        "seed": args.seed,
        "metric_list_version": _metric_list_version(),
        "created": datetime.now(UTC).date().isoformat(),
        "episode_count": len(labels),
        "window_count": window_count,
        "generator": "ml/datasets/make_episodes.py",
        "generator_commit": _generator_commit(),
        "fault_store": args.fault_store,
        "virtual_clock": {
            "start": first_tick.isoformat(),
            "end": clock.value.isoformat(),
            "step_seconds": args.step_seconds,
        },
        "window_samples": args.window_samples,
        "schedule": {
            "normal_minutes": args.normal_minutes,
            "fault_seconds_min": args.fault_seconds_min,
            "fault_seconds_max": args.fault_seconds_max,
            "recover_minutes": args.recover_minutes,
        },
        "fault_type_distribution": dict(
            sorted(Counter(row["fault_type"] for row in labels).items())
        ),
        "resources": [r.id for r in resources],
        "notes": [
            "Simulator data. Practice only -- not thesis material.",
            "Fault windows are bounded by clear_fault, not by the Redis TTL.",
            "region_down labels list every affected resource, not just the target.",
            "Telemetry is reproducible from `seed` alone, given the same metric list.",
        ],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a labelled fault-episode dataset from SimulatedProvider."
    )
    parser.add_argument("--seed", type=int, default=0, help="reproducibility seed (default: 0)")
    parser.add_argument("--episodes", type=int, default=20, help="fault episodes (default: 20)")
    parser.add_argument("--version", default="v1", help="dataset version dir (default: v1)")
    parser.add_argument(
        "--out-root", type=Path, default=Path("ml/datasets"), help="dataset root directory"
    )
    parser.add_argument("--normal-minutes", type=float, default=10.0)
    parser.add_argument("--fault-seconds-min", type=int, default=60)
    parser.add_argument("--fault-seconds-max", type=int, default=180)
    parser.add_argument("--recover-minutes", type=float, default=2.0)
    parser.add_argument("--step-seconds", type=int, default=10, help="collector interval")
    parser.add_argument(
        "--window-samples", type=int, default=12, help="samples per MetricWindow (12 = 120s)"
    )
    parser.add_argument(
        "--fault-store",
        choices=("redis", "memory"),
        default="redis",
        help="redis uses the real core.faults API (needs `make up`); "
        "memory injects in-process (default: redis)",
    )
    parser.add_argument(
        "--start",
        default="2026-01-01T00:00:00+00:00",
        help="virtual clock start, ISO 8601 (fixed by default so runs are reproducible)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    out_dir = args.out_root / args.version
    existing = [name for name in _DATA_FILES if (out_dir / name).exists()]
    if existing:
        sys.exit(
            f"{out_dir} already contains {', '.join(existing)}.\n"
            f"Dataset versions are immutable (ml/datasets/README.md) -- "
            f"generate a new one with `--version v2` instead of overwriting this."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.fault_store == "memory":
        _install_memory_fault_store()
    else:
        _check_redis_reachable()

    manifest = asyncio.run(generate(args, out_dir))

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "labels.schema.json").write_text(
        json.dumps(_LABEL_SCHEMA, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(
        f"\nwrote {manifest['window_count']} windows and "
        f"{manifest['episode_count']} episodes to {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
