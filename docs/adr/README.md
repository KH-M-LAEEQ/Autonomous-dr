# Architecture Decision Records

One file per decision, numbered, never deleted. A superseded ADR gets
`Status: Superseded by ADR-00XX` and stays in the repo — the reasoning is the
artefact, and the viva committee will ask about the decisions you reversed.

**Write an ADR when:**

- a frozen interface in `core/interfaces/` or a type in `core/models/` must change
- the database schema changes shape (not: a new column on a table you own)
- a library or service is added to the stack
- scope is cut at a decision gate

**Rules**

1. Number sequentially, four digits, kebab-case title.
2. All three roles approve in writing in the PR. Frozen means frozen.
3. Ship the ADR in the same PR as the code that implements it.
4. Copy `0000-template.md`. Do not invent a new format.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-provider-abstraction.md) | Provider abstraction behind one interface | Proposed |
| [0002](0002-postgres-influx-split.md) | Postgres for state, InfluxDB for telemetry | Proposed |
| [0003](0003-pgvector-over-vector-db.md) | pgvector, not a separate vector database | Proposed |
| [0004](0004-quorum-before-pbft.md) | Quorum first, PBFT as a pluggable strategy | Proposed |
| [0005](0005-rag-not-fine-tuning.md) | RAG over fine-tuning for explanations | Proposed |
| [0006](0006-celery-for-async.md) | Celery for asynchronous and scheduled work | Proposed |
| [0007](0007-simulator-first-testing.md) | Simulator-first development and testing | Proposed |
| [0008](0008-time-based-evaluation-splits.md) | Time-based evaluation splits, never shuffled | Proposed |
| [0009](0009-pluggable-thresholds-and-structured-explanations.md) | Pluggable anomaly thresholds and structured, auditable explanations | Proposed |
| [0010](0010-geopolitical-risk-policy-bounded.md) | Geopolitical risk is policy-bounded, not an autonomous trigger | Proposed |
| [0011](0011-utility-formula-contract.md) | One fixed contract for the utility formula | Proposed |
| [0012](0012-heterogeneous-detectors-per-node.md) | Heterogeneous detectors per monitor node | Proposed |
