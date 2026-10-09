"""Full schema: the remaining 15 tables (16 with `tenants` from 0001).

Hand-authored on purpose, including the tables that stay empty until month four
(graph_*, corpus_chunks, bandit_state, risk_signals, savings_reports). Adding a
table later is cheap; discovering in January that an early table needed a column
it never had is not. After the Week 2 freeze, schema changes need an ADR.

This merges two independently-written drafts of this same revision (one from
this branch, one from the formula-contract patch). Where they disagreed, the
tie-break was: keep whatever `core/repo/*.py` and `core/incidents.py` already
run real queries against, since those are shipped and tested; otherwise prefer
the richer/more specific design. Three deliberate exceptions to "every column
from both", called out where they happen below:
  * `incidents.trigger_detection_id` has no FK (the patch's choice) -- `detections`
    is created after `incidents`, and a two-way FK buys nothing but insert-order
    sensitivity. `opened_at` keeps ITS OWN `server_default=now()` regardless,
    because `core.incidents.open_incident`'s INSERT never supplies it.
  * `graph_nodes`/`graph_edges` use the patch's `snapshot_id`/`service` design
    wholesale, dropping this branch's `snapshot_at`/`weight` draft -- nothing
    reads or writes either table yet, and the patch's shape is what Week 13
    actually needs (ADR reference: `docs/metrics.md` predates both).
  * `audit_log` keeps THIS branch's `actor`/`action`/`hash` columns, not the
    patch's `event_type`/`row_hash` -- `core/repo/audit.py` (already shipped)
    hashes exactly `{tenant_id, actor, action, payload, created_at}`, and
    renaming the columns out from under it breaks the hash chain, not just the
    SQL.

Rev. 2 changes folded in:
  * `decisions` exists. Week 31's ablation study queries historical decisions and
    their term breakdowns, which is impossible if they are never persisted.
  * `detections.incident_id` / `detections.node_id` -- the latter per Week 17's
    heterogeneous-detectors-per-node design (ADR-0012; this ADR was renumbered
    from 0009 during the merge -- see docs/adr/README.md -- because 0009 was
    already taken by the pluggable-thresholds ADR on this branch).
  * `votes.detection_id` links each vote to the detection that produced it (ADR-0012).
  * `risk_signals.source_type` / `source_url` carry provenance (ADR-0010).
  * `corpus_chunks.tenant_id` nullable (NULL = global corpus), `source_url`,
    `chunk_index`, and an HNSW index on `embedding`.
  * `graph_nodes.snapshot_id` / `graph_edges.snapshot_id` version the topology.

Conventions
  * Every tenant-scoped table has `tenant_id` and an index leading with it. Tenant
    isolation is enforced INSIDE each query (WHERE tenant_id = :id), never by
    filtering results afterwards (NFR-S1).
  * Enum-like columns are TEXT + CHECK, not Postgres ENUM types: adding a member
    is a one-line constraint change, not an ALTER TYPE dance.
  * `corpus_chunks.tenant_id IS NULL` means the global corpus; non-null is that
    tenant's own incident history.
  * Embedding dimension is 384 (all-MiniLM-L6-v2). Changing it means re-embedding
    the corpus, not editing a column.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _tenant_fk(nullable: bool = False) -> sa.Column:
    return sa.Column("tenant_id", sa.Text(), sa.ForeignKey("tenants.id"), nullable=nullable)


def _now(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.func.now(),
    )


def upgrade() -> None:
    # --- resources -----------------------------------------------------------
    op.create_table(
        "resources",
        sa.Column("id", sa.Text(), primary_key=True),
        _tenant_fk(),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _now("created_at"),
        # core/repo/resources.py's upsert sets this explicitly on every write
        # (insert and ON CONFLICT UPDATE) -- the collector's only writer.
        _now("updated_at"),
    )
    op.create_index("ix_resources_tenant_id", "resources", ["tenant_id"])
    op.create_index("ix_resources_tenant_region", "resources", ["tenant_id", "region"])

    # --- incidents -------------------------------------------------------------
    # Created before `detections` so `detections.incident_id` can reference it.
    # `trigger_detection_id` deliberately has NO FK -- see module docstring.
    op.create_table(
        "incidents",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("resource_id", sa.Text(), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="open"),
        # core/incidents.py's INSERT never supplies this column -- it relies
        # entirely on this server default.
        _now("opened_at"),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("trigger_detection_id", pg.UUID(as_uuid=True)),
        # Written by the off-critical-path Celery task (Week 16).
        sa.Column("explanation", sa.Text()),
        sa.Column("explanation_source", sa.Text()),  # 'llm' | 'template'
        sa.CheckConstraint(
            "state IN ('open','deciding','acting','resolved','failed')", name="ck_incidents_state"
        ),
    )
    op.create_index("ix_incidents_tenant_state", "incidents", ["tenant_id", "state"])
    op.create_index("ix_incidents_tenant_opened", "incidents", ["tenant_id", "opened_at"])
    op.create_index("ix_incidents_resource_id", "incidents", ["resource_id"])

    # --- detections ------------------------------------------------------------
    op.create_table(
        "detections",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("incident_id", pg.UUID(as_uuid=True), sa.ForeignKey("incidents.id")),
        sa.Column("resource_id", sa.Text(), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("node_id", sa.Text()),  # which monitor node (Week 17); NULL before then
        sa.Column("detector", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False),
        sa.Column("model_version", sa.Text()),  # which model produced it (W11 registry)
        sa.Column("explanation", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _now("detected_at"),
    )
    op.create_index("ix_detections_tenant_id", "detections", ["tenant_id"])
    op.create_index("ix_detections_resource_id", "detections", ["resource_id"])
    op.create_index("ix_detections_incident_id", "detections", ["incident_id"])

    # --- actions (folds in ExecutionResult's fields -- see core/models/domain.py) --
    op.create_table(
        "actions",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("incident_id", pg.UUID(as_uuid=True), sa.ForeignKey("incidents.id")),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("target_resource_id", sa.Text(), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("params", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("provider_ref", sa.Text()),
        sa.Column("rollback_token", sa.Text()),
        sa.Column("actual_cost_usd", sa.Numeric(12, 4)),
        sa.Column("error", sa.Text()),
        _now("created_at"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("tier IN ('tier_1','tier_2','tier_3')", name="ck_actions_tier"),
        sa.CheckConstraint(
            "status IN ('proposed','approved','rejected_by_budget','rejected_by_consensus',"
            "'awaiting_human','executing','succeeded','failed','rolled_back')",
            name="ck_actions_status",
        ),
    )
    op.create_index("ix_actions_tenant_status", "actions", ["tenant_id", "status"])
    op.create_index("ix_actions_incident_id", "actions", ["incident_id"])

    # --- decisions (new in Rev. 2) ----------------------------------------------
    op.create_table(
        "decisions",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "incident_id", pg.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("chosen_action_id", pg.UUID(as_uuid=True), sa.ForeignKey("actions.id")),
        sa.Column("utility", sa.Float(), nullable=False),
        # Keys present only once their week has landed; absent is not zero.
        sa.Column("terms", pg.JSONB(), nullable=False),
        sa.Column("weights", pg.JSONB(), nullable=False),
        sa.Column("formula_version", sa.Text(), nullable=False),
        sa.Column("rejected", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rationale", sa.Text()),
        _now("created_at"),
    )
    op.create_index("ix_decisions_tenant_incident", "decisions", ["tenant_id", "incident_id"])
    op.create_index("ix_decisions_formula_version", "decisions", ["formula_version"])

    # --- proposals / votes (folds in ConsensusResult's fields onto proposals) --
    op.create_table(
        "proposals",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "incident_id", pg.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("action_id", pg.UUID(as_uuid=True), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("proposer_id", sa.Text(), nullable=False),
        sa.Column("digest", sa.Text()),  # SHA-256 over the canonical action; PBFT needs it
        _now("created_at"),
        sa.Column("committed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("strategy", sa.Text()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_proposals_incident_id", "proposals", ["incident_id"])

    op.create_table(
        "votes",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "proposal_id", pg.UUID(as_uuid=True), sa.ForeignKey("proposals.id"), nullable=False
        ),
        sa.Column("voter_id", sa.Text(), nullable=False),
        sa.Column("choice", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        # The detection this vote rests on (ADR-0012). Nullable: single-node
        # consensus in Weeks 5-16 has no per-node detection to point at.
        sa.Column("detection_id", pg.UUID(as_uuid=True), sa.ForeignKey("detections.id")),
        _now("cast_at"),
        sa.CheckConstraint("choice IN ('approve','reject','abstain')", name="ck_votes_choice"),
        sa.UniqueConstraint("proposal_id", "voter_id", name="uq_votes_one_per_voter"),
    )

    # --- cost_estimates ----------------------------------------------------------
    op.create_table(
        "cost_estimates",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("action_id", pg.UUID(as_uuid=True), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="USD"),
        sa.Column("one_off_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("hourly_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("projected_monthly_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.Text(), nullable=False, server_default="static_table"),
        sa.Column("breakdown", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _now("created_at"),
        # CostEstimate is 1:1 with an action per core/models/domain.py.
        sa.UniqueConstraint("action_id", name="uq_cost_estimates_action"),
    )
    op.create_index("ix_cost_estimates_tenant_id", "cost_estimates", ["tenant_id"])

    # --- audit_log (hash-chained) -----------------------------------------------
    # BIGSERIAL, not UUID: chain order must be unambiguous and monotonic.
    # Column names/shape match core/repo/audit.py exactly -- see module docstring.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _tenant_fk(nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prev_hash", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False, unique=True),
        _now("created_at"),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_tenant_created", "audit_log", ["tenant_id", "created_at"])

    # --- dependency graph (versioned snapshots, Week 13) ------------------------
    op.create_table(
        "graph_nodes",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), sa.ForeignKey("resources.id")),
        sa.Column("attrs", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _now("captured_at"),
        sa.UniqueConstraint("snapshot_id", "service", name="uq_graph_nodes_snapshot_service"),
    )
    op.create_index("ix_graph_nodes_tenant_snapshot", "graph_nodes", ["tenant_id", "snapshot_id"])

    op.create_table(
        "graph_edges",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("src_service", sa.Text(), nullable=False),
        sa.Column("dst_service", sa.Text(), nullable=False),
        sa.Column("call_rate", sa.Float()),
        sa.Column("attrs", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "snapshot_id", "src_service", "dst_service", name="uq_graph_edges_pair"
        ),
    )
    op.create_index("ix_graph_edges_tenant_snapshot", "graph_edges", ["tenant_id", "snapshot_id"])

    # --- corpus_chunks (RAG, Week 15) -------------------------------------------
    op.create_table(
        "corpus_chunks",
        _uuid_pk(),
        _tenant_fk(nullable=True),  # NULL = global corpus
        sa.Column("source", sa.Text(), nullable=False),  # e.g. 'aws-pes-2025-10', 'audit_log'
        sa.Column("source_url", sa.Text()),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _now("created_at"),
    )
    op.execute(
        "CREATE INDEX ix_corpus_chunks_embedding ON corpus_chunks "
        "USING hnsw (embedding vector_l2_ops)"
    )
    op.create_index("ix_corpus_chunks_tenant_id", "corpus_chunks", ["tenant_id"])

    # --- bandit_state (Thompson Sampling, Week 25) ------------------------------
    op.create_table(
        "bandit_state",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("arm_key", sa.Text(), nullable=False),  # a weight configuration
        sa.Column("alpha", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("beta", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pulls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weights", pg.JSONB(), nullable=False),
        _now("updated_at"),
        sa.UniqueConstraint("tenant_id", "arm_key", name="uq_bandit_tenant_arm"),
    )

    # --- risk_signals (Week 22; provenance added in Rev. 2) ---------------------
    # Mostly global (a provider status post is the same fact for everyone), but
    # tenant_id stays nullable rather than absent, matching corpus_chunks' pattern,
    # in case a future tenant-specific feed needs scoping.
    op.create_table(
        "risk_signals",
        _uuid_pk(),
        _tenant_fk(nullable=True),
        sa.Column("provider", sa.Text()),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),  # every signal is traceable
        sa.Column("severity", sa.Float(), nullable=False, server_default="0"),  # 0..1
        sa.Column("summary", sa.Text()),
        sa.Column("raw", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        _now("ingested_at"),
        sa.CheckConstraint(
            "source_type IN ('provider_status','geopolitical')", name="ck_risk_signals_source_type"
        ),
        sa.CheckConstraint("severity >= 0 AND severity <= 1", name="ck_risk_signals_severity"),
    )
    op.create_index("ix_risk_signals_region_time", "risk_signals", ["region", "observed_at"])

    # --- savings_reports (Week 23) ----------------------------------------------
    op.create_table(
        "savings_reports",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("downtime_cost_avoided_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("action_cost_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("system_overhead_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_savings_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "assumptions", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        _now("generated_at"),
        sa.UniqueConstraint("tenant_id", "period_start", "period_end", name="uq_savings_period"),
    )


def downgrade() -> None:
    # Reverse dependency order.
    for table in (
        "savings_reports",
        "risk_signals",
        "bandit_state",
        "corpus_chunks",
        "graph_edges",
        "graph_nodes",
        "audit_log",
        "cost_estimates",
        "votes",
        "proposals",
        "decisions",
        "actions",
        "detections",
        "incidents",
        "resources",
    ):
        op.drop_table(table)
