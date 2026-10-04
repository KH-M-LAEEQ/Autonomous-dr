import type { OverviewData } from "../types";

export const mockOverview: OverviewData = {
  kpis: [
    { id: "open-incidents", label: "Open incidents", value: 3 },
    { id: "avg-recovery", label: "Avg. recovery time", value: 47, unit: "s", trend: "down" },
    { id: "approvals-waiting", label: "Approvals waiting", value: 1 },
    { id: "savings-mtd", label: "Savings this month", value: 1420, unit: "$" },
  ],
  recoveryLatency: [
    { timestamp: "2026-10-04T08:00:00Z", latencySeconds: 52 },
    { timestamp: "2026-10-04T09:00:00Z", latencySeconds: 61 },
    { timestamp: "2026-10-04T10:00:00Z", latencySeconds: 45 },
    { timestamp: "2026-10-04T11:00:00Z", latencySeconds: 58 },
    { timestamp: "2026-10-04T12:00:00Z", latencySeconds: null },
    { timestamp: "2026-10-04T13:00:00Z", latencySeconds: 39 },
    { timestamp: "2026-10-04T14:00:00Z", latencySeconds: 47 },
  ],
  incidents: [
    {
      id: "INC-0042",
      title: "Checkout API latency spike",
      resourceId: "svc-checkout-api",
      provider: "aws",
      severity: "high",
      state: "investigating",
      openedAt: "2026-10-04T13:42:00Z",
    },
    {
      id: "INC-0041",
      title: "Order queue consumer lag",
      resourceId: "svc-order-queue",
      provider: "gcp",
      severity: "medium",
      state: "open",
      openedAt: "2026-10-04T11:05:00Z",
    },
    {
      id: "INC-0039",
      title: "Image resize worker OOM",
      resourceId: "svc-image-resize",
      provider: "azure",
      severity: "low",
      state: "resolved",
      openedAt: "2026-10-03T22:10:00Z",
    },
  ],
  cloudStatus: [
    { provider: "aws", label: "AWS", status: "degraded" },
    { provider: "gcp", label: "Google Cloud", status: "healthy" },
    { provider: "azure", label: "Azure", status: "healthy" },
  ],
  activity: [
    { id: "act-1", timestamp: "2026-10-04T13:44:00Z", actor: "system", message: "Detected anomaly on svc-checkout-api" },
    { id: "act-2", timestamp: "2026-10-04T13:45:00Z", actor: "system", message: "Opened INC-0042" },
    { id: "act-3", timestamp: "2026-10-04T13:46:00Z", actor: "monitor-2", message: "Cast vote: approve" },
    { id: "act-4", timestamp: "2026-10-04T13:50:00Z", actor: "ops.laeeq", message: "Approved Tier 3 action APR-1182" },
  ],
};
