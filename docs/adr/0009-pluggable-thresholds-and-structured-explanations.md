# ADR-0009: Pluggable anomaly thresholds and structured, auditable explanations

- **Status:** Proposed — the final round of interface changes before the Week 2 freeze
- **Date:** 2026-09-12
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/interfaces/anomaly_detector.py, core/interfaces/explanation_engine.py, core/threshold_strategies.py, core/tests/test_interfaces.py, every future detector and explanation engine implementation

## Context

- `decision_threshold: float = 0.5` hardcodes a single thresholding rule into
  the frozen `AnomalyDetector` interface. Week 10's harness needs to compare
  Z-test (3σ), Gaussian likelihood, percentile (q95), and IQR (Tukey 1.5×)
  against each other on the *same* detector output to produce a
  false-positive-rate comparison table (docs/formulas.md §2). A single float
  can't represent that choice; without a pluggable strategy each detector
  would end up implementing its own ad hoc thresholding, and the comparison
  stops being apples-to-apples.
- `ExplanationEngine.explain` returns a bare `str`. Nothing stops it from
  asserting things the retrieved corpus doesn't support, and nothing lets the
  UI show which chunks back which sentence. The Week 16 hallucination audit
  currently means reading 20 incidents by hand.
- `explain` was also the only `async` method across the five frozen
  interfaces, while its only production caller (Celery tasks, ADR-0006) is
  sync by default. That asymmetry has no payoff yet and forces the sync call
  site to bridge into an event loop just to get one explanation.

## Decision

- `AnomalyDetector` holds a `threshold_strategy: ThresholdStrategy` instance
  (constructor-injected, defaulting to IQR) instead of a class-level
  `decision_threshold` float. `ThresholdStrategy` is a new frozen interface:
  `fit(train_residuals)` / `is_anomalous(residual)`. Concrete strategies
  (Z-test, Gaussian likelihood, percentile, IQR) live in
  `core/threshold_strategies.py` as ordinary implementations — adding one
  needs no ADR, per the existing rule for detector implementations. IQR is
  the default because it has the lowest observed false-positive rate of the
  four (docs/formulas.md §2). `threshold_strategies.py` is stdlib-only
  (`statistics`/`math`) on purpose: `core` must stay importable without the
  `ml` extras (numpy et al. are the AI role's tooling per `pyproject.toml`),
  and every `AnomalyDetector` needs a strategy default.
- `ExplanationEngine.explain` returns `Explanation(text, citations, engine,
  unsupported)` instead of `str`. `citations` lists only the corpus-chunk ids
  from `context.retrieved_documents` actually cited; `unsupported` lists
  claims in `text` not backed by them. This turns the Week 16 audit into
  `sum(len(e.unsupported) for e in run)` instead of a manual read.
- `explain` becomes synchronous. An LLM-backed implementation that needs an
  async client bridges internally (e.g. `asyncio.run`) rather than pushing
  async through the interface. The "never on the critical path, template is
  the fallback" rule from the original interface docstring is unchanged.

## Consequences

**Good:** the harness can produce the Week 10 threshold comparison table
without per-detector special-casing; the hallucination audit becomes a
metric instead of a manual review; one calling convention (sync) across all
five interfaces instead of four-and-a-half.

**Bad:** every detector implementation now owns a `ThresholdStrategy`
instance instead of reading a literal off `self`; a template engine that
skips populating `unsupported` (e.g. always returns `[]`) silently defeats
the audit instead of erroring, so the Week 16 review still has to spot-check
that engines are actually checking, not just returning an empty list.

**Neutral:** `Explanation` is a plain `dataclass`, not a pydantic model like
the rest of `core/models/domain.py`, because it is produced by the engine and
consumed by the API/UI layer, not itself exchanged across the DB boundary in
this shape — the API layer converts what it needs to persist.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep `decision_threshold`, add a separate `threshold_fn` callable field | A callable can't declare or cache fitted state (mean, std, quartiles) without becoming a class anyway; `ThresholdStrategy` is that class made explicit. |
| Return citations as a second return value instead of a dataclass | The UI needs three things alongside the text (`citations`, `unsupported`, `engine`); a 4-tuple nobody can read by position is worse than a named dataclass. |
| Keep `explain` async, bridge it at the Celery task boundary | Pushes the sync/async bridge onto every current and future caller instead of once, inside the one implementation (the LLM engine) that actually needs it. |

## Revisit when

A second production caller of `ExplanationEngine` needs true concurrency
(e.g. batch-explaining many incidents at once) that a sync call can't
provide — add an async batch method then; don't reopen this one.
