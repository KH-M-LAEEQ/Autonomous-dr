# LSTM forecast-residual detector -- design (PB-14)

> **Fixed before training, fixed before v6 results are seen.** Every setting
> below is locked at the point this file is committed. If a setting needs to
> change, that is a new commit with a stated reason, not a silent edit -- the
> whole point of writing this first is that nobody can tune these against the
> numbers they produce.

## 1. Input

Same window features as `iforest`: `ml/detectors/window_features.py`'s
`WindowVectorizer` (mean/std/last per `DETECTOR_SIGNALS` signal present in
training, `use_time_of_day=False`, absent signal filled with its training
mean -- unmodified, the same copy `iforest.py` and the PyOD family already
share).

On top of that vector, every one of its features is scaled by that feature's
own **training median and IQR**, the same robust scaling `ThresholdDetector`
applies to raw signals (`ml/detectors/threshold.py`'s `_percentile`, reused
here, not reimplemented): `(value - median) / iqr`, with the same zero-IQR
fallback (fall back to the median's own magnitude, or `1.0` if that is also
zero). This is a second, separate scaling step from `WindowVectorizer`'s own
training-mean fill for absent signals -- that fill rule is unchanged; this
scaling is new, and applies to every feature the vectorizer produces.

## 2. Model

Forecast, not reconstruction: predict window *t*'s scaled feature vector from
the 6 scaled feature vectors immediately before it (windows *t-6 .. t-1*).

- `nn.LSTM(input_size=D, hidden_size=32, num_layers=1, batch_first=True)`,
  `D` = the vectorizer's output width (`3 * len(signals)`, no time-of-day).
- Final hidden state -> `nn.Linear(32, D)` -> predicted vector for window *t*.

## 3. Training

- Optimizer: Adam, learning rate `0.001`.
- Batch size: 256.
- At most 20 epochs.
- Early stopping on `X_val` loss, patience 3 (the first epoch with no new
  best `X_val` loss starts the count; 3 such epochs in a row stops training
  and restores the best-epoch weights).
- `torch.manual_seed(0)` before building the model, so two `fit()` calls on
  identical data produce identical weights.
- Training examples are built by sliding a length-6 window over the
  chronological sequence of scaled vectors, independently within `X` and
  within `X_val` -- `X_val` is not prefixed with `X`'s tail, so the first 6
  windows of `X_val` cannot form a training example. `docs/formulas.md`
  reserves the val slice for exactly this early-stopping role, but
  `ml/harness/evaluate.py`'s `_score_resource` currently calls
  `detector.fit(train_windows)` with no second argument -- `X_val` is `None`
  on every call the harness makes today. **Caveat, not a bug to fix here**:
  when `X_val` is `None` or too short to form at least one example, `fit`
  skips early stopping and trains for the full 20 epochs. Wiring the
  harness's unused val slice through to `fit` is future work, out of scope
  for PB-14 (`ml/harness/evaluate.py` is explicitly off-limits this ticket).
  `evaluate.py`'s own module docstring still says "patience 5" from an
  earlier plan; PB-14's instructions fix patience at 3, which is what this
  design and the implementation use -- that earlier number is stale, not
  reconciled here since it lives in a file this ticket must not edit.

## 4. Score

Mean squared error between the predicted and actual scaled feature vector
for window *t*. Higher MSE = more anomalous, same direction as every other
detector's `score`.

## 5. Alarm

Identical rule to `iforest`: fit the Tukey IQR fence
(`Q3 + 1.5*(Q3-Q1)`) over training scores, require
`CONSECUTIVE_BREACHES_REQUIRED` (3) consecutive breaches to call it an
anomaly. Both constants are imported from `ml/detectors/threshold.py`, not
redefined.

## 6. The first 6 windows of a resource

A window needs 6 *prior* windows in the same scoring call to be scored at
all. The first 6 windows handed to `score_batch` (or the first 6 calls to
`score` on a freshly-fit or freshly-reset-of-history instance -- history is
never reset by `reset()`, only hysteresis is, matching every other detector)
have no such history and are scored `0.0` / not anomalous by construction,
not by falling through the IQR fence. This is stated in `lstm.py`'s
docstring, not just here.

## Outcome (v6, seed 42)

F1 0.511 against threshold's 0.833 -- a 0.322 gap, nowhere near the 0.05
margin the 5-seed robustness check required, so that check did not run.
False alarms: 420 in normal-phase windows, 667 in recovery, both well above
threshold's and iforest's counts.

Early stopping never fired on any of the 8 v6 resources -- all trained the
full 20 epochs. A per-epoch loss trace on two of them (`sim-web-1`,
`sim-db-1`) shows why: validation loss was still falling at epoch 20 for
both, so patience-3 never got a chance to trigger. Looks like under-training
against the 20-epoch cap, not a broken branch -- a dedicated unit test now
confirms patience-3 does fire once validation loss actually stalls.

Limitation of the fixed design, recorded, not a reason to change it: every
setting above was fixed before these results and stays fixed after them.
