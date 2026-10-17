"""LSTMDetector -- the forecast-residual detector. Design fixed, before any
training, in `docs/notes/lstm-design.md`; this module is that design,
implemented, not a place to retune it.

Forecasts window *t*'s feature vector from the 6 windows immediately before
it and scores on the forecast's mean squared error -- a spike the model has
never seen is hard to predict, so its own arrival is what trips the alarm,
the same "learn normal, flag the departure" shape as `iforest`.

**The first 6 windows of a resource have no history.** A forecast needs 6
prior vectors; the first 6 windows of `score_batch`'s input (or the first 6
calls to `score` since the last `fit`) cannot form one and are scored `0.0`,
never anomalous, by construction -- not because they happen to fall under
the IQR fence. `reset()` only clears hysteresis (matching every other
detector's `reset()`), never this rolling history, so a mid-resource episode
boundary does not reopen the "first 6 windows" gap.
"""

from __future__ import annotations

from typing import Any

import torch
from torch import nn

from core.interfaces.anomaly_detector import AnomalyDetector
from core.models.domain import MetricWindow
from ml.detectors import register
from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED, IQR_MULTIPLIER, _percentile
from ml.detectors.window_features import WindowVectorizer

HISTORY_LENGTH = 6
HIDDEN_SIZE = 32
LEARNING_RATE = 0.001
BATCH_SIZE = 256
MAX_EPOCHS = 20
EARLY_STOP_PATIENCE = 3
TORCH_SEED = 0


class _ForecastNet(nn.Module):
    """1 LSTM layer, 32 hidden units, then a linear layer back to feature
    width -- the whole model, per `docs/notes/lstm-design.md` section 2."""

    def __init__(self, input_size: int) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=HIDDEN_SIZE, batch_first=True)
        self.linear = nn.Linear(HIDDEN_SIZE, input_size)

    def forward(self, sequence: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(sequence)
        output: torch.Tensor = self.linear(hidden[-1])
        return output


def _sliding_sequences(vectors: list[list[float]]) -> tuple[torch.Tensor, torch.Tensor] | None:
    """(inputs, targets) built by sliding a length-`HISTORY_LENGTH` window
    over `vectors`, in order: `inputs[i]` is `vectors[i : i+HISTORY_LENGTH]`,
    `targets[i]` is the vector right after it. `None` if `vectors` is too
    short to form even one example."""
    if len(vectors) <= HISTORY_LENGTH:
        return None
    inputs = [vectors[i - HISTORY_LENGTH : i] for i in range(HISTORY_LENGTH, len(vectors))]
    targets = [vectors[i] for i in range(HISTORY_LENGTH, len(vectors))]
    return torch.tensor(inputs, dtype=torch.float32), torch.tensor(targets, dtype=torch.float32)


@register("lstm")
class LSTMDetector(AnomalyDetector):
    """Forecast-residual detector over `WindowVectorizer`'s per-signal
    mean/std/last features, each additionally scaled by its own training
    median and IQR (`docs/notes/lstm-design.md` section 1).

    One instance per monitor node, per the `AnomalyDetector` contract -- the
    rolling history, consecutive-breach counter, and last-score state behind
    `explain` are all per-instance; a shared instance would corrupt every one
    of them across nodes.
    """

    name = "lstm"
    requires_training = True
    # Declared here so the attribute exists before `fit` under either version
    # of the interface, same as `ThresholdDetector`/`IsolationForestDetector`.
    decision_threshold: float = 0.5

    def __init__(self, consecutive_breaches_required: int = CONSECUTIVE_BREACHES_REQUIRED) -> None:
        self._vectorizer = WindowVectorizer(use_time_of_day=False)
        self._median: list[float] = []
        self._spread: list[float] = []
        self._model: _ForecastNet | None = None
        self._history: list[list[float]] = []
        self._consecutive_breaches = 0
        self._required = consecutive_breaches_required
        self._last_explain: dict[str, Any] = {}
        self._fitted = False
        #: Duck-typed, like `reset()`: how many epochs the last `fit()` call
        #: actually ran before early stopping (or `MAX_EPOCHS`, if it never
        #: triggered). Not part of the frozen `AnomalyDetector` interface.
        self.epochs_trained = 0

    # -- features -----------------------------------------------------------

    def _scaled_vector(self, window: MetricWindow) -> list[float]:
        """`WindowVectorizer`'s raw vector, then `(value - median) / spread`
        per feature -- the extra robust-scaling step `docs/notes/
        lstm-design.md` section 1 adds on top of the shared `iforest`
        features."""
        raw = self._vectorizer.vector(window)
        return [
            (value - median) / spread
            for value, median, spread in zip(raw, self._median, self._spread, strict=True)
        ]

    def _mse_batch(self, inputs: torch.Tensor, targets: torch.Tensor) -> list[float]:
        assert self._model is not None
        self._model.eval()
        with torch.no_grad():
            predictions = self._model(inputs)
            errors = ((predictions - targets) ** 2).mean(dim=1)
        return [float(v) for v in errors.tolist()]

    # -- AnomalyDetector ------------------------------------------------------

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        """Fit the vectorizer, the per-feature median/IQR scale, and the
        forecaster -- in that order, all on `X` (plus `X_val` for early
        stopping only; never for the scale or the vectorizer, or the
        comparison against `X_val` would leak into what "normal" means).

        `X_val` early-stops training (`EARLY_STOP_PATIENCE` epochs with no
        new best `X_val` loss) when it is long enough to form at least one
        training example; otherwise training runs the full `MAX_EPOCHS` with
        no early stopping. See `docs/notes/lstm-design.md` section 3 for why
        that is the common case today, not a bug.
        """
        if len(X) <= HISTORY_LENGTH:
            raise ValueError(f"need more than {HISTORY_LENGTH} training windows, got {len(X)}")

        self._vectorizer.fit(X)
        raw_vectors = [self._vectorizer.vector(w) for w in X]
        dim = len(raw_vectors[0])

        self._median = []
        self._spread = []
        for column in range(dim):
            values = [v[column] for v in raw_vectors]
            q1, median, q3 = (
                _percentile(values, 25),
                _percentile(values, 50),
                _percentile(values, 75),
            )
            self._median.append(median)
            iqr = q3 - q1
            if iqr > 0:
                self._spread.append(iqr)
            else:
                # Constant in training. Fall back to its own magnitude, same
                # rule as `ThresholdDetector.fit`.
                magnitude = abs(median)
                self._spread.append(magnitude if magnitude > 0 else 1.0)

        train_vectors = [self._scaled_vector(w) for w in X]
        train_data = _sliding_sequences(train_vectors)
        if train_data is None:
            raise ValueError(f"need more than {HISTORY_LENGTH} training windows, got {len(X)}")
        train_inputs, train_targets = train_data

        val_vectors = [self._scaled_vector(w) for w in X_val] if X_val else []
        val_data = _sliding_sequences(val_vectors)

        torch.manual_seed(TORCH_SEED)
        self._model = _ForecastNet(dim)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=LEARNING_RATE)
        loss_fn = nn.MSELoss()
        shuffle_generator = torch.Generator().manual_seed(TORCH_SEED)

        best_val_loss = float("inf")
        best_state = {k: v.clone() for k, v in self._model.state_dict().items()}
        epochs_without_improvement = 0
        n = train_inputs.shape[0]

        for epoch in range(MAX_EPOCHS):
            self._model.train()
            permutation = torch.randperm(n, generator=shuffle_generator)
            for start in range(0, n, BATCH_SIZE):
                batch_idx = permutation[start : start + BATCH_SIZE]
                optimizer.zero_grad()
                predictions = self._model(train_inputs[batch_idx])
                loss = loss_fn(predictions, train_targets[batch_idx])
                loss.backward()
                optimizer.step()
            self.epochs_trained = epoch + 1

            if val_data is None:
                continue
            val_inputs, val_targets = val_data
            val_loss = self._mse_batch(val_inputs, val_targets)
            mean_val_loss = sum(val_loss) / len(val_loss)
            if mean_val_loss < best_val_loss:
                best_val_loss = mean_val_loss
                best_state = {k: v.clone() for k, v in self._model.state_dict().items()}
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= EARLY_STOP_PATIENCE:
                    break

        if val_data is not None:
            self._model.load_state_dict(best_state)
        self._model.eval()

        train_scores = self._mse_batch(train_inputs, train_targets)
        q1, q3 = _percentile(train_scores, 25), _percentile(train_scores, 75)
        self.decision_threshold = q3 + IQR_MULTIPLIER * (q3 - q1)

        self._history = []
        self._consecutive_breaches = 0
        self._last_explain = {}
        self._fitted = True

    def _build_explain(self, value: float) -> dict[str, Any]:
        return {"score": value, "threshold": self.decision_threshold}

    def score(self, window: MetricWindow) -> float:
        """Forecasts from the last `HISTORY_LENGTH` windows seen by this
        instance since `fit` (or since the start, if fewer than that many
        have been seen yet -- see the module docstring)."""
        if not self._fitted:
            raise RuntimeError("fit() must be called before score()")
        vector = self._scaled_vector(window)
        if len(self._history) < HISTORY_LENGTH:
            value = 0.0
        else:
            inputs = torch.tensor([self._history[-HISTORY_LENGTH:]], dtype=torch.float32)
            targets = torch.tensor([vector], dtype=torch.float32)
            value = self._mse_batch(inputs, targets)[0]
        self._history.append(vector)
        if len(self._history) > HISTORY_LENGTH:
            del self._history[0]
        self._last_explain = self._build_explain(value)
        return value

    def score_batch(self, windows: list[MetricWindow]) -> list[float]:
        """Vectorised `score()`: one forecast call over every window in
        `windows` that has 6 predecessors *within this same list*, instead of
        one call per window. Self-contained per call -- it does not read or
        write the rolling history `score()` keeps, so calling this does not
        disturb a sequence of `score()` calls interleaved with it, and two
        calls given the same windows always agree.

        `windows` is one resource's windows, chronologically ordered, the
        same convention `IsolationForestDetector.score_batch` relies on.
        """
        if not self._fitted:
            raise RuntimeError("fit() must be called before score_batch()")
        if not windows:
            return []
        vectors = [self._scaled_vector(w) for w in windows]
        scores = [0.0] * len(vectors)
        sequences = _sliding_sequences(vectors)
        if sequences is not None:
            inputs, targets = sequences
            errors = self._mse_batch(inputs, targets)
            for offset, error in enumerate(errors):
                scores[HISTORY_LENGTH + offset] = error
        self._last_explain = self._build_explain(scores[-1])
        return scores

    def is_breach(self, score: float) -> bool:
        """Hysteresis only, given an already-computed score -- `score_batch`'s
        companion, identical in shape to `IsolationForestDetector.is_breach`."""
        breach = score > self.decision_threshold
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= self._required

    def is_anomaly(self, window: MetricWindow) -> bool:
        """Overrides the default for hysteresis, same reason as
        `IsolationForestDetector.is_anomaly`."""
        return self.is_breach(self.score(window))

    def explain(self) -> dict[str, Any]:
        return {
            "detector": self.name,
            "consecutive_breaches": self._consecutive_breaches,
            "breaches_required": self._required,
            **self._last_explain,
        }

    def reset(self) -> None:
        """Clear hysteresis state only -- never the rolling forecast history.
        Duck-typed, like `IsolationForestDetector.reset`: the Week 10 harness
        calls this between fault episodes so a breach streak cannot carry
        into the next episode's count (see that method's docstring). The
        forecast history is not hysteresis: the model has no notion of
        episode boundaries, and clearing it here would reopen the "first 6
        windows have no history" gap in the middle of a resource's test
        slice for no reason connected to what `reset()` exists to fix.
        """
        self._consecutive_breaches = 0
        self._last_explain = {}
