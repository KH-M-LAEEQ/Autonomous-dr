# Week 2 · Sequence diagrams — review

Source: [`week2-sequence-diagrams-review.pdf`](./week2-sequence-diagrams-review.pdf).

Three critical paths, drawn against the five frozen interfaces in
`core/interfaces/` and the 16-table schema. The point of drawing them is to find
interface gaps **before Friday**, while a signature can still change without an
ADR and three signatures.

## Read this before the meeting

Three things in these diagrams are decisions, not descriptions. They need
confirming, not just reviewing:

- **Consensus votes on "is this a real anomaly", not "is this the right
  action".** Those are different systems. Diagram 2 assumes the first.
- **The decision engine runs after quorum, not before.** So nodes agree
  something is wrong, then one engine picks the response.
- **Explanation is fully off the critical path.** The action executes and the
  incident resolves before the LLM is ever called.

## Six gaps found by drawing these

| # | Gap | Owner | Deadline |
| --- | --- | --- | --- |
| 1 | `AnomalyDetector.score() -> float` vs GNN per-node output | BACKEND | before freeze |
| 2 | `ExplanationEngine.explain() -> str` cannot carry citations | BACKEND | before freeze |
| 3 | Phi has no home — not a term, not on an interface | AI | before freeze |
| 4 | Proposer selection under quorum undefined | BACKEND | Week 17 |
| 5 | Duplicate proposals for one event | BACKEND | Week 17 |
| 6 | `symptom_query` construction undefined | AI | Week 15 |

Items 1–3 change signatures and must be settled this week. 4–6 are behaviour,
not signatures, and can wait.

## 1a · Detection → quorum

First half of the main loop. Split in two for legibility — Gate A in Week 6 is
1a and 1b together, end to end, in under 60 seconds.

## 1b · Decision → action

Picks up where 1a ends, once quorum has been reached. This is where the
utility function and the budget gate live.

### Diagrams 1a / 1b — open questions

- **Where does Phi come from?** It is not in `Decision.terms` — it is a
  property of a candidate. At Week 5 the collector has no per-node history, so
  it is stubbed at `1.0`. That stub needs a home in code, not in folklore.
- **Consensus runs before the decision.** Nodes vote on whether the anomaly is
  real, then one decision engine picks the action. The alternative — voting on
  the chosen action — is a materially different system. Confirm which one we
  are building.
- **Tier 3 has no human-approval branch here.** Deliberate: it lands in Week
  17 along with the full action catalogue.
- **The budget gate writes before it refuses.** A refused action still
  produces a `cost_estimates` row and an audit entry, so refusals are
  auditable rather than silent.

## 2 · Consensus vote

Three nodes, three **different** detectors (ADR-0009). Two of three must
agree. Independence lives in the scoring method, not the data source — all
three read the same telemetry.

### Diagram 2 — open questions

- **Who proposes?** Drawn as node-a because it detected first. PBFT has a
  designated primary with view change; quorum has no primary at all.
  First-to-detect, round-robin, or a separate coordinator — undecided.
- **Two nodes may detect independently.** That is two proposals for one
  underlying event, and therefore two incidents unless we deduplicate by time
  window.
- **A dead node votes nothing.** Timeout must count as absent, never as
  DISAGREE. Otherwise one dead node blocks all recovery — which fails the
  Week 17 "done when".
- **Week 24 replaces this diagram.** Four nodes, three PBFT phases, 2f+1
  thresholds (see `docs/formulas.md` §3). The interface is identical; only the
  box changes.

Scores shown (0.91 / 0.74 / 0.22) are illustrative — they are the case where
the threshold and Isolation Forest nodes agree and the LSTM node dissents.
Week 17 requires at least one logged case of genuine disagreement, so this is
the shape we need to see in the logs.

## 3 · RAG explanation

Off the critical path. The action has **already executed** before this
starts — killing the LLM API does not stop recovery.

### Diagram 3 — open questions

- **What exactly is `symptom_query`?** The thing being embedded is not
  defined anywhere. Candidates: the raw metric deviation, a templated
  sentence, or the detector's `explain()` output. This determines retrieval
  quality and therefore Week 15's evaluation.
- **Citation verification has no home in the interfaces.**
  `ExplanationEngine.explain(context) -> str` returns a plain string, so
  structured citations have nowhere to live. This is gap #2.
- **A new tenant has an empty personal store.** Global corpus only until they
  have had incidents. Belongs in the limitations chapter.
- **The corpus is static from Week 15.** No re-embedding path if the
  embedding model changes. Acceptable for now; worth noting.

The tenant filter sits inside the retrieval query, never applied to results
afterwards. That is what ADR-0003 buys us by choosing pgvector over a separate
vector database, and it is what the Week 15 isolation test asserts against.
