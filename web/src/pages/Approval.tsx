import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { Badge } from "../components/Badge";
import { Countdown } from "../components/Countdown";
import { getApproval } from "../api/client";
import type { ApprovalRequest, DryRunStep } from "../api/types";
import { formatUsd } from "../lib/format";

const STEP_LABEL: Record<DryRunStep["status"], string> = {
  planned: "Planned",
  "would-succeed": "Would succeed",
  "would-fail": "Would fail",
};

export function Approval() {
  const { id } = useParams<{ id: string }>();
  const [approval, setApproval] = useState<ApprovalRequest | null | undefined>(undefined);
  const [decision, setDecision] = useState<"approved" | "rejected" | null>(null);

  useEffect(() => {
    let cancelled = false;
    setApproval(undefined);
    setDecision(null);
    if (!id) return;
    getApproval(id).then((result) => {
      if (!cancelled) setApproval(result);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (approval === undefined) {
    return <p className="text-sm text-muted">Loading approval request…</p>;
  }
  if (approval === null) {
    return <p className="text-sm text-muted">No data for approval {id}.</p>;
  }

  const minutes = Math.floor(approval.undoWindowSeconds / 60);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <span className="tabular text-sm text-muted">{approval.id}</span>
        <h1 className="mt-1 text-xl font-semibold">Approval needed — Tier 3</h1>
        <p className="mt-1 text-sm text-muted">
          Tier 3 actions never run without a human approval.
        </p>
      </header>

      <Card title="Proposed action">
        <p className="text-sm">{approval.proposedAction}</p>
        <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="eyebrow">Cost</dt>
            <dd className="tabular mt-1 text-lg font-semibold">{formatUsd(approval.costUsd)}</dd>
          </div>
          <div>
            <dt className="eyebrow">Budget left</dt>
            <dd className="tabular mt-1 text-lg font-semibold">{formatUsd(approval.budgetLeftUsd)}</dd>
          </div>
          <div>
            <dt className="eyebrow">ETA</dt>
            <dd className="tabular mt-1 text-lg font-semibold">{approval.etaSeconds}s</dd>
          </div>
          <div>
            <dt className="eyebrow">Undo window</dt>
            <dd className="tabular mt-1 text-lg font-semibold">{minutes} min</dd>
          </div>
        </dl>
      </Card>

      <Card title="Checks passed">
        <ul className="flex flex-col gap-1.5">
          {approval.checksPassed.map((check) => (
            <li key={check} className="flex items-center gap-2 text-sm">
              <Badge tone="ok" label="Passed" />
              <span>{check}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Dry-run plan">
        <ol className="flex flex-col gap-2">
          {approval.dryRunPlan.map((step, index) => (
            <li key={step.id} className="flex items-center justify-between gap-3 text-sm">
              <span>
                <span className="tabular text-muted">{index + 1}. </span>
                {step.description}
              </span>
              <Badge
                tone={step.status === "would-fail" ? "danger" : step.status === "would-succeed" ? "ok" : "neutral"}
                label={STEP_LABEL[step.status]}
              />
            </li>
          ))}
        </ol>
      </Card>

      <Card title="Respond before the countdown ends">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Countdown totalSeconds={approval.countdownSeconds} />
          {decision ? (
            <Badge
              tone={decision === "approved" ? "ok" : "danger"}
              label={decision === "approved" ? "Approved" : "Rejected"}
            />
          ) : (
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setDecision("approved")}
                className="min-h-11 rounded-md bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 focus-visible:outline-2"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => setDecision("rejected")}
                className="min-h-11 rounded-md border border-border bg-card px-5 py-2 text-sm font-medium text-danger hover:bg-danger/10 focus-visible:outline-2"
              >
                Reject
              </button>
            </div>
          )}
        </div>
        <p className="mt-4 text-xs text-muted">{approval.fallbackDescription}</p>
      </Card>
    </div>
  );
}
