import type { IncidentDetail } from "../types";

export const mockIncidentDetail: Record<string, IncidentDetail> = {
  "INC-0042": {
    id: "INC-0042",
    title: "Checkout API latency spike",
    resourceId: "svc-checkout-api",
    provider: "aws",
    severity: "high",
    state: "investigating",
    openedAt: "2026-10-04T13:42:00Z",
    timeline: [
      { id: "t1", timestamp: "2026-10-04T13:42:00Z", label: "Anomaly detected", detail: "p99 latency crossed 3 consecutive breaches" },
      { id: "t2", timestamp: "2026-10-04T13:43:10Z", label: "Incident opened" },
      { id: "t3", timestamp: "2026-10-04T13:44:00Z", label: "Explanation generated" },
      { id: "t4", timestamp: "2026-10-04T13:45:30Z", label: "Monitor vote: 2 of 3 approve" },
      { id: "t5", timestamp: "2026-10-04T13:50:00Z", label: "Action approved and started" },
    ],
    explanation: {
      text:
        "Checkout API response time has been above the normal range for the last three checks in a row. The most likely cause is a backed-up database connection pool following a deploy at 13:40. Restarting the affected instance should clear the backlog.",
      citations: [
        { id: "c1", label: "Deploy log 13:40 UTC", url: "https://example.internal/deploys/4821" },
        { id: "c2", label: "Latency metric: svc-checkout-api p99", url: "https://example.internal/metrics/checkout-p99" },
      ],
      engine: "template",
      unsupported: [],
    },
    votes: [
      { voterId: "monitor-1", choice: "approve", reason: "Matches known connection-pool pattern", castAt: "2026-10-04T13:45:05Z" },
      { voterId: "monitor-2", choice: "approve", reason: null, castAt: "2026-10-04T13:45:20Z" },
      { voterId: "monitor-3", choice: "abstain", reason: "Insufficient history for this resource", castAt: "2026-10-04T13:45:28Z" },
    ],
    decision: {
      id: "dec-9001",
      incidentId: "INC-0042",
      weights: { w_ability: 0.4, w_cost: 0.2, w_latency: 0.25, w_safety: 0.15 },
      formulaVersion: "2026.09.1",
      options: [
        {
          id: "opt-restart",
          name: "Restart instance",
          utility: 0.71,
          chosen: true,
          terms: { cost: 2.5, latency: 45, safety: 0.9, impact: 0.2 },
        },
        {
          id: "opt-scale-out",
          name: "Scale out +2 instances",
          utility: 0.58,
          chosen: false,
          terms: { cost: 11.0, latency: 90, safety: 0.85, impact: 0.3, price_delta: 0.12 },
        },
        {
          id: "opt-failover",
          name: "Failover to secondary region",
          utility: 0.33,
          chosen: false,
          // `risk` deliberately omitted: the detector has no risk model for this
          // action yet. Must render "n/a", never 0.
          terms: { cost: 40.0, latency: 180, safety: 0.6 },
        },
      ],
    },
    budgetCheck: {
      capUsd: 25,
      spentUsd: 2.5,
      remainingUsd: 22.5,
      passed: true,
    },
    auditEntries: [
      { id: "aud-1", timestamp: "2026-10-04T13:43:10Z", actor: "system", action: "incident.opened", hash: "a3f1c9" },
      { id: "aud-2", timestamp: "2026-10-04T13:45:30Z", actor: "system", action: "vote.quorum_reached", hash: "7be214" },
      { id: "aud-3", timestamp: "2026-10-04T13:50:00Z", actor: "system", action: "action.executed:restart_instance", hash: "f09ad2" },
    ],
    canRollBack: true,
  },
};
