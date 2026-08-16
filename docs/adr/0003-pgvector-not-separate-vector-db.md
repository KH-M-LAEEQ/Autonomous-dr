# ADR-0003: pgvector, not a separate vector database

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

Week 15 builds retrieval over a corpus of ~150 public post-mortems plus each tenant's
own incident history. That needs embedding storage and similarity search.

The obvious alternatives are a dedicated vector database (Pinecone, Weaviate, Qdrant) or
the `pgvector` extension in the Postgres instance we already run.

The deciding constraint is not performance. It is **tenant isolation**. Week 15 requires
that tenant A can never retrieve tenant B's rows, and that this is enforced inside the
retrieval query rather than by filtering results afterwards. Week 29 has to prove it,
and it is the question the committee is most likely to ask.

## Decision

`pgvector` in the existing Postgres. Embeddings live in `corpus_chunks` alongside
everything else.

Retrieval is a single SQL statement with `WHERE tenant_id = :id` in the same query as
the similarity search. Never post-filtered.

## Consequences

**Isolation is a SQL predicate, not application logic.** The strongest form of the
guarantee, and the easiest to test — the Week 15 isolation test asserts against the
query, not against a code path that could be bypassed.

**No extra service.** One fewer container, one fewer credential, one fewer thing to
explain in the deployment guide.

**Global and per-tenant stores in one table.** Public post-mortems and tenant history
differ by a column, not by a system.

**Scale ceiling accepted.** pgvector on a few thousand chunks is comfortable. At
millions it would not be. Our corpus is ~150 documents and one tenant's history — orders
of magnitude below the point where a dedicated store would win.
