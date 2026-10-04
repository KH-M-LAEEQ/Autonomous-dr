import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { Badge, type BadgeTone } from "../components/Badge";
import { DataTable, type DataTableColumn } from "../components/DataTable";
import { getIncident } from "../api/client";
import type { IncidentDetail, ScoredOption, TermKey } from "../api/types";
import { QUORUM_REQUIRED, QUORUM_TOTAL } from "../api/types";
import { formatDateTime, formatTerm, formatUsd } from "../lib/format";

const SEVERITY_TONE: Record<string, BadgeTone> = {
  critical: "danger",
  high: "danger",
  medium: "warn",
  low: "ok",
};

const VOTE_TONE: Record<string, BadgeTone> = {
  approve: "ok",
  reject: "danger",
  abstain: "neutral",
};

const TERM_LABELS: Record<TermKey, string> = {
  cost: "Cost ($)",
  latency: "Latency (s)",
  safety: "Safety",
  impact: "Impact",
  price_delta: "Price delta",
  risk: "Risk",
};

function allTermKeys(options: ScoredOption[]): TermKey[] {
  const seen = new Set<TermKey>();
  for (const option of options) {
    for (const key of Object.keys(option.terms) as TermKey[]) {
      seen.add(key);
    }
  }
  return Array.from(seen);
}

export function Incident() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<IncidentDetail | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    setIncident(undefined);
    if (!id) return;
    getIncident(id).then((result) => {
      if (!cancelled) setIncident(result);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (incident === undefined) {
    return <p className="text-sm text-muted">Loading incident…</p>;
  }
  if (incident === null) {
    return <p className="text-sm text-muted">No data for incident {id}.</p>;
  }

  const termKeys = allTermKeys(incident.decision.options);
  const approvals = incident.votes.filter((vote) => vote.choice === "approve").length;
  const quorumReached = approvals >= QUORUM_REQUIRED;

  const optionColumns: DataTableColumn<ScoredOption>[] = [
    { key: "name", header: "Option", render: (row) => (row.chosen ? `${row.name} (chosen)` : row.name) },
    ...termKeys.map<DataTableColumn<ScoredOption>>((key) => ({
      key,
      header: TERM_LABELS[key],
      align: "right",
      render: (row) => formatTerm(row.terms, key),
    })),
    { key: "utility", header: "Utility", align: "right", render: (row) => row.utility.toFixed(2) },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="flex flex-wrap items-center gap-3">
          <span className="tabular text-sm text-muted">{incident.id}</span>
          <Badge tone={SEVERITY_TONE[incident.severity] ?? "neutral"} label={incident.severity} />
          <Badge tone="neutral" label={incident.state} />
        </div>
        <h1 className="mt-1 text-xl font-semibold">{incident.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {incident.resourceId} · {incident.provider.toUpperCase()} · opened {formatDateTime(incident.openedAt)}
        </p>
      </header>

      <Card title="Timeline">
        <ol className="flex flex-col gap-3">
          {incident.timeline.map((event) => (
            <li key={event.id} className="flex gap-3 text-sm">
              <span className="tabular w-20 shrink-0 text-xs text-muted">
                {formatDateTime(event.timestamp)}
              </span>
              <div>
                <p className="font-medium">{event.label}</p>
                {event.detail && <p className="text-xs text-muted">{event.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <Card title="What happened, in plain language">
        <p className="text-sm leading-relaxed">{incident.explanation.text}</p>
        {incident.explanation.citations.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1">
            {incident.explanation.citations.map((citation) => (
              <li key={citation.id} className="text-xs">
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline underline-offset-2"
                >
                  {citation.label}
                </a>
              </li>
            ))}
          </ul>
        )}
        {incident.explanation.unsupported.length > 0 && (
          <p className="mt-3 text-xs text-warn">
            <span aria-hidden="true">▲</span> Some statements above are not backed by a source:{" "}
            {incident.explanation.unsupported.join("; ")}
          </p>
        )}
      </Card>

      <Card title={`Monitor votes — ${approvals} of ${QUORUM_TOTAL} approve (needs ${QUORUM_REQUIRED})`}>
        <div className="flex items-center gap-3 mb-3">
          <Badge
            tone={quorumReached ? "ok" : "warn"}
            label={quorumReached ? "Quorum reached" : "Quorum not reached"}
          />
        </div>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {incident.votes.map((vote) => (
            <li key={vote.voterId} className="rounded-md border border-border p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{vote.voterId}</span>
                <Badge tone={VOTE_TONE[vote.choice] ?? "neutral"} label={vote.choice} />
              </div>
              {vote.reason && <p className="mt-1 text-xs text-muted">{vote.reason}</p>}
            </li>
          ))}
        </ul>
      </Card>

      <Card title={`Scored options — formula ${incident.decision.formulaVersion}`}>
        <p className="mb-3 text-xs text-muted">
          Weights:{" "}
          {Object.entries(incident.decision.weights)
            .map(([key, value]) => `${key}=${value}`)
            .join(", ")}
          . A column showing "n/a" means that term does not apply to this option — it is not zero.
        </p>
        <DataTable columns={optionColumns} rows={incident.decision.options} caption="Scored recovery options" />
      </Card>

      <Card title="Budget check">
        <div className="flex flex-wrap items-center gap-4">
          <Badge
            tone={incident.budgetCheck.passed ? "ok" : "danger"}
            label={incident.budgetCheck.passed ? "Passed" : "Failed"}
          />
          <p className="tabular text-sm">
            Spent {formatUsd(incident.budgetCheck.spentUsd)} of cap {formatUsd(incident.budgetCheck.capUsd)} ·
            remaining {formatUsd(incident.budgetCheck.remainingUsd)}
          </p>
        </div>
      </Card>

      <Card title="Audit trail">
        <ul className="flex flex-col gap-2">
          {incident.auditEntries.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-baseline gap-2 text-xs">
              <span className="tabular text-muted">{formatDateTime(entry.timestamp)}</span>
              <span className="font-medium">{entry.actor}</span>
              <span>{entry.action}</span>
              <span className="tabular text-muted">#{entry.hash}</span>
            </li>
          ))}
        </ul>
      </Card>

      <div>
        <button
          type="button"
          disabled={!incident.canRollBack}
          className="min-h-11 rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-danger hover:bg-danger/10 focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Roll back
        </button>
      </div>
    </div>
  );
}
