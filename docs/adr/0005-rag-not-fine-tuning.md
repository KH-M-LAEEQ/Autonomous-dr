# ADR-0005: RAG, not fine-tuning

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

Week 16 requires a plain-English justification for every action, grounded in real
operational knowledge rather than invented by a language model.

The two options are fine-tuning an open model on incident data, or retrieval-augmented
generation over a curated corpus.

Fine-tuning needs training pairs of the form (incident → correct remediation). **No such
corpus exists and one cannot be constructed.** There are only a few hundred public
post-mortems in total, and they are narrative documents, not labelled pairs. Fine-tuning
on that volume would produce a model that performs worse than retrieval at the same task
while consuming roughly 150 hours and the entire GPU budget.

## Decision

RAG. A corpus of AWS Post-Event Summaries, Azure PIRs, GCP incident reports, Cloudflare
and GitHub post-mortems, provider reliability docs and our own runbooks — target 150+
documents — chunked, embedded, and stored in `corpus_chunks` (see ADR-0003).

`LLMExplanationEngine` uses a hosted model (Llama 3 via Groq free tier) with a prompt
assembling current state, the decision and its term breakdown, and retrieved documents.
The model is constrained to cite only the provided sources.

## Consequences

**~150 hours and the GPU budget go elsewhere** — to the GNN, the evaluation harness and
the ablation study.

**Citations are traceable.** Every claim in an explanation points at a retrieved
document, shown in the UI. A fine-tuned model's output is unattributable.

**The corpus updates without retraining.** A new post-mortem is a new row.

**Explanation quality is bounded by retrieval quality.** Hence the Week 15 retrieval eval
— 20 hand-written symptom queries, measuring whether the right post-mortem lands in the
top 3 — and the Week 16 hallucination check on 20 incidents, reported honestly.

**This is the correct engineering choice, not the humble one.** State it that way in the
defence; it is a deliberate exclusion with a reason, not a gap.
