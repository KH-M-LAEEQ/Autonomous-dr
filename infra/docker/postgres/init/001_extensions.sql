-- Runs once, on first container start, before any Alembic migration.
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector, for corpus_chunks (Week 15)
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- digest() for the hash-chained audit_log (Week 4)
