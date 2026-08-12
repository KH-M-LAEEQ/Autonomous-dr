# ADR-0003: pgvector, not a separate vector database

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** corpus_chunks, the RAG pipeline (Week 15)

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- Corpus target is ~150 documents. That is thousands of chunks, not millions.
- Tenant isolation must be enforced inside the retrieval query (`WHERE tenant_id = :id`), never post-filtered — a second datastore makes that a second isolation boundary to prove.
- A fourth service is a fourth thing to install on three laptops and in CI.

## Decision

Embeddings are stored in Postgres using the pgvector extension, in the
`corpus_chunks` table, alongside the tenant rows they must be filtered by. No
Pinecone, Qdrant, Chroma or Weaviate.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

Corpus exceeds roughly a million chunks or retrieval latency exceeds the
end-to-end budget measured in Week 28.
