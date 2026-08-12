# Datasets

Versioned, immutable. `v1/` is created in Week 8 and never edited afterwards --
if the generator changes, that produces `v2/`. Every result in the thesis names
the dataset version it was computed on.

Data files themselves are gitignored (see `.gitignore`). What is committed:

- `<version>/manifest.json` — episode count, date range, fault type distribution,
  the exact generator commit SHA
- `<version>/labels.schema.json` — the ground-truth label format
- the generator script that produced it

Anyone should be able to regenerate a dataset from the manifest plus the script.
