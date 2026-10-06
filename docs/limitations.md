# Known limitations

## The threshold detector fits once and never refits

`ml/tasks.py`'s `_check_resource` fits each resource's `ThresholdDetector`
exactly once, after `FIT_WINDOW_COUNT` (30) bootstrap windows of history,
and never refits it afterwards. This is deliberate -- a later fault can't
drag the baseline up to absorb itself -- but it means:

- A fault injected during the ~5-minute bootstrap window corrupts that
  resource's baseline permanently; the detector never gets a second chance
  to fit on clean data.
- Legitimate drift in normal behavior over time (e.g. a slow traffic
  increase) is never absorbed into the baseline -- it will eventually look
  like a permanent anomaly.
- A resource that starts being polled for the first time always has this
  same cold-start window, with no guard against a fault happening to land
  inside it.

See `ml/tasks.py`'s module docstring for the rationale.
