"""Episode generator -- the data factory for the simulator practice run.

Produces a versioned, immutable dataset under `ml/datasets/<version>/`:

    windows.jsonl        one rolling MetricWindow per resource per tick
    labels.jsonl         one ground-truth row per injected fault episode
    labels.schema.json   the label format, per ml/datasets/README.md
    manifest.json        seed, metric-list version, date, episode count

The loop is: `--normal-minutes` of clean telemetry, one fault injected through
the real `core.faults` API, the fault's exact start/end/type/target appended
to labels.jsonl, the fault cleared, `--recover-minutes` of settling, then the
next episode. Which shape runs each episode is NOT drawn independently at
random -- `_build_shape_schedule` round-robins through `--shapes`, reshuffled
once per virtual day (`_episodes_per_virtual_day`), so every shape recurs
steadily across the whole timeline rather than clustering wherever
independent sampling happened to land (which it did for v4's `--seed 42`
run: `stop` got 1 of its 7 episodes in the first third of the timeline and
3 each in the other two; `small_step` got 3, then 1, then 6 of its 10 --
exactly the kind of uneven spread that makes a 70/15/15 chronological split
hand some shapes to test and starve others). `target` is still drawn
independently per episode via `rng.choice`.

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
    "required": ["episode", "shape", "fault_type", "target", "affected", "start", "end"],
    "additionalProperties": False,
    "properties": {
        "episode": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "unique per label row across the dataset -- what the harness keys "
                "detection delay on. An `intermittent` episode emits one row per ON "
                "burst, so these do not map 1:1 onto scheduled_episode."
            ),
        },
        "scheduled_episode": {
            "type": "integer",
            "minimum": 0,
            "description": "index of the generator's episode loop that produced this row",
        },
        "shape": {
            "type": "string",
            "description": "how the fault was driven over time",
        },
        "burst": {
            "type": "integer",
            "minimum": 0,
            "description": "0 for single-span shapes; the ON-burst index for intermittent",
        },
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


#: Episode shapes. The first five drive a single constant fault and are
#: trivially detectable -- `stop`/`pause`/`region_down` zero every signal. The
#: last three exist because "the detector caught a total outage" says nothing
#: about a detector, and the v3 practice run produced a degenerate delay
#: distribution (every episode caught at exactly the hysteresis floor) for
#: precisely that reason.
CLASSIC_SHAPES: tuple[str, ...] = ("cpu_hog", "latency", "stop", "pause", "region_down")
SUBTLE_SHAPES: tuple[str, ...] = ("gradual_ramp", "small_step", "intermittent")
ALL_SHAPES: tuple[str, ...] = (*CLASSIC_SHAPES, *SUBTLE_SHAPES)

Span = tuple[datetime, datetime]
# A shape runner advances the clock by n ticks and returns windows written.
PhaseRunner = Any


def _typical_fault_seconds(shape: str, args: argparse.Namespace) -> float:
    """How long one episode of `shape` typically occupies the clock, used only
    to size a "virtual day" for `_build_shape_schedule` -- not the actual
    duration drawn at generation time (classic shapes still randomise within
    `[fault_seconds_min, fault_seconds_max]`)."""
    if shape == "intermittent":
        return float(args.intermittent_minutes * 60)
    if shape == "gradual_ramp":
        return float(args.ramp_minutes * 60)
    if shape == "small_step":
        return float(args.small_step_seconds)
    return float(args.fault_seconds_min + args.fault_seconds_max) / 2.0


def _episodes_per_virtual_day(args: argparse.Namespace) -> int:
    """How many episodes fit in 24h of virtual clock, given the configured
    normal/recover phases and the average duration across the shapes in play.
    Sizes the round-robin chunk in `_build_shape_schedule`."""
    avg_fault_seconds = sum(_typical_fault_seconds(s, args) for s in args.shapes) / len(args.shapes)
    episode_seconds: float = (
        float(args.normal_minutes) * 60 + float(args.recover_minutes) * 60 + avg_fault_seconds
    )
    return max(1, round(86_400 / episode_seconds))


def _build_shape_schedule(
    rng: random.Random, shapes: list[str], n_episodes: int, episodes_per_day: int
) -> list[str]:
    """Round-robin through `shapes`, reshuffled once per virtual day, so every
    shape recurs steadily across the whole timeline instead of clustering
    wherever independent per-episode sampling happened to land -- the
    confound `--seed 42 --episodes 300` previously could and did produce.

    Each day's chunk is `shapes` repeated just enough to cover the chunk
    length, then shuffled -- a round-robin rotation at the day granularity,
    randomised in order within it. The final chunk is whatever is left over
    (<= `episodes_per_day`), built the same way.
    """
    schedule: list[str] = []
    chunk_size = max(1, episodes_per_day)
    while len(schedule) < n_episodes:
        size = min(chunk_size, n_episodes - len(schedule))
        pool = (list(shapes) * (size // len(shapes) + 1))[:size]
        rng.shuffle(pool)
        schedule.extend(pool)
    return schedule


def _phase_runner(
    provider: SimulatedProvider,
    resources: list[Resource],
    clock: _VirtualClock,
    history: dict[str, dict[str, list[float]]],
    windows_out: IO[str],
    args: argparse.Namespace,
) -> PhaseRunner:
    """Binds the long `_phase` argument list once per episode."""

    async def run(ticks: int) -> int:
        return await _phase(
            ticks,
            provider,
            resources,
            clock,
            history,
            windows_out,
            args.step_seconds,
            args.window_samples,
        )

    run.clock = clock  # type: ignore[attr-defined]
    return run


async def _run_constant(
    provider: SimulatedProvider,
    target: Resource,
    fault_type: str,
    run: PhaseRunner,
    seconds: int,
    args: argparse.Namespace,
) -> tuple[Span, int]:
    """One fault, held at constant severity for the whole span."""
    clock: _VirtualClock = run.clock
    ticks = max(1, seconds // args.step_seconds)
    provider.inject_fault(target.id, fault_type, _FAULT_TTL_SECONDS)
    start = clock.value
    written = await run(ticks)
    end = clock.value
    faults.clear_fault(target.id)
    return (start, end), written


async def _run_ramp(
    provider: SimulatedProvider,
    target: Resource,
    run: PhaseRunner,
    args: argparse.Namespace,
) -> tuple[Span, int]:
    """CPU climbs from baseline to cpu_hog severity across `--ramp-minutes`.

    The fault is re-injected every tick with a rising `intensity`, which is how
    a gradual fault advances through the one-string Redis fault API. The early
    ticks sit inside normal noise on purpose: a detector that only trips on
    extremes should be LATE here, which is the whole point of the shape.
    """
    clock: _VirtualClock = run.clock
    ticks = max(1, int(args.ramp_minutes * 60) // args.step_seconds)
    start = clock.value
    written = 0
    for tick in range(ticks):
        provider.inject_fault(
            target.id,
            "cpu_ramp",
            _FAULT_TTL_SECONDS,
            intensity=(tick + 1) / ticks,
        )
        written += await run(1)
    end = clock.value
    faults.clear_fault(target.id)
    return (start, end), written


async def _run_intermittent(
    provider: SimulatedProvider,
    target: Resource,
    run: PhaseRunner,
    args: argparse.Namespace,
) -> tuple[list[Span], int]:
    """`--intermittent-on` on, `--intermittent-off` off, for
    `--intermittent-minutes`.

    Each ON burst is its own label row, so the OFF gaps are correctly labelled
    normal -- marking the whole window faulty would score a detector's correct
    silence during a gap as a miss. Bursts are short relative to the detector's
    3-breach hysteresis, which is deliberate: a burst shorter than 3 collector
    steps is structurally undetectable, and that bound is worth measuring
    rather than assuming.
    """
    clock: _VirtualClock = run.clock
    on_ticks = max(1, int(args.intermittent_on * 60) // args.step_seconds)
    off_ticks = max(1, int(args.intermittent_off * 60) // args.step_seconds)
    cycle_minutes = args.intermittent_on + args.intermittent_off
    cycles = max(1, int(args.intermittent_minutes // cycle_minutes))

    spans: list[Span] = []
    written = 0
    for cycle in range(cycles):
        provider.inject_fault(target.id, "cpu_hog", _FAULT_TTL_SECONDS)
        start = clock.value
        written += await run(on_ticks)
        spans.append((start, clock.value))
        faults.clear_fault(target.id)
        if cycle < cycles - 1:
            written += await run(off_ticks)
    return spans, written


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
    label_id = 0
    first_tick = clock.value

    episodes_per_day = _episodes_per_virtual_day(args)
    shape_schedule = _build_shape_schedule(rng, args.shapes, args.episodes, episodes_per_day)

    original_datetime = simulated_module.datetime
    simulated_module.datetime = _ClockDatetime(clock)  # type: ignore[assignment, misc]
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

                shape = shape_schedule[episode]
                target = rng.choice(resources)
                run = _phase_runner(
                    provider, resources, clock, history, windows_out, args
                )

                if shape == "intermittent":
                    bursts, written = await _run_intermittent(
                        provider, target, run, args
                    )
                    window_count += written
                    spans = bursts
                    fault_type = "cpu_hog"  # the primitive each burst injects
                elif shape == "gradual_ramp":
                    span, written = await _run_ramp(provider, target, run, args)
                    window_count += written
                    spans = [span]
                    fault_type = "cpu_ramp"
                elif shape == "small_step":
                    span, written = await _run_constant(
                        provider, target, "cpu_step_small", run, args.small_step_seconds, args
                    )
                    window_count += written
                    spans = [span]
                    fault_type = "cpu_step_small"
                else:  # a classic single-shot fault, named directly by `shape`
                    fault_type = shape
                    seconds = rng.randrange(
                        args.fault_seconds_min,
                        args.fault_seconds_max + 1,
                        args.step_seconds,
                    )
                    span, written = await _run_constant(
                        provider, target, fault_type, run, seconds, args
                    )
                    window_count += written
                    spans = [span]

                affected = _affected_by(fault_type, target, resources)
                for burst_index, (start, end) in enumerate(spans):
                    labels.append(
                        {
                            # Unique across the whole dataset: the harness keys
                            # detection delay on this, and `intermittent` emits
                            # one row per ON burst (see _run_intermittent).
                            "episode": label_id,
                            "scheduled_episode": episode,
                            "shape": shape,
                            "burst": burst_index,
                            "fault_type": fault_type,
                            "target": target.id,
                            "tenant_id": target.tenant_id,
                            "region": target.region,
                            "affected": affected,
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "duration_seconds": int((end - start).total_seconds()),
                        }
                    )
                    label_id += 1

                total_s = sum(int((e - s).total_seconds()) for s, e in spans)
                print(
                    f"episode {episode:>3}: {shape:<13} on {target.id:<12} "
                    f"{len(spans)} span(s), {total_s:>5}s faulty"
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
        simulated_module.datetime = original_datetime  # type: ignore[assignment, misc]
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
        # `episode_count` is label rows, which is what the harness scores.
        # `scheduled_episode_count` is generator loop iterations; they differ
        # because an intermittent episode emits one row per ON burst.
        "episode_count": len(labels),
        "scheduled_episode_count": args.episodes,
        "window_count": window_count,
        "shapes_used": sorted(args.shapes),
        "shape_distribution": dict(
            sorted(Counter(str(row["shape"]) for row in labels).items())
        ),
        "shape_schedule": {
            "ramp_minutes": args.ramp_minutes,
            "small_step_seconds": args.small_step_seconds,
            "intermittent_on_minutes": args.intermittent_on,
            "intermittent_off_minutes": args.intermittent_off,
            "intermittent_total_minutes": args.intermittent_minutes,
            "policy": "round_robin_shuffled_per_virtual_day",
            "episodes_per_virtual_day": episodes_per_day,
        },
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
    parser.add_argument(
        "--shapes",
        nargs="+",
        default=list(ALL_SHAPES),
        choices=list(ALL_SHAPES),
        help="episode shapes to draw from (default: all)",
    )
    parser.add_argument("--ramp-minutes", type=float, default=10.0, help="gradual_ramp duration")
    parser.add_argument(
        "--small-step-seconds", type=int, default=300, help="small_step duration"
    )
    parser.add_argument("--intermittent-on", type=float, default=1.0, help="minutes on")
    parser.add_argument("--intermittent-off", type=float, default=1.0, help="minutes off")
    parser.add_argument(
        "--intermittent-minutes", type=float, default=10.0, help="total intermittent span"
    )
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
