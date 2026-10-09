import type { CostData } from "../types";

export const mockCost: CostData = {
  spendUsd: 2.5,
  capUsd: 25,
  estimates: [
    { id: "est-1", label: "Restart instance (svc-checkout-api)", estimatedUsd: 2.5, actualUsd: 2.5 },
    { id: "est-2", label: "Scale out +2 instances", estimatedUsd: 11.0, actualUsd: null },
    { id: "est-3", label: "Failover to secondary region", estimatedUsd: 40.0, actualUsd: null },
    { id: "est-4", label: "Image resize worker restart", estimatedUsd: 0.4, actualUsd: 0.6 },
  ],
  priceComparison: [
    { provider: "aws", resource: "m6i.large, on-demand", priceUsd: 0.096 },
    { provider: "gcp", resource: "n2-standard-2, on-demand", priceUsd: 0.097 },
    { provider: "azure", resource: "D2s v5, on-demand", priceUsd: null },
  ],
  unusedResources: [
    { id: "unused-1", name: "snap-0a1b2c3d", provider: "aws", monthlyCostUsd: 4.2, idleSince: "2026-08-12T00:00:00Z" },
    { id: "unused-2", name: "disk-stale-logs-02", provider: "gcp", monthlyCostUsd: 2.8, idleSince: "2026-09-01T00:00:00Z" },
    { id: "unused-3", name: "ip-reserved-unassigned", provider: "azure", monthlyCostUsd: 3.6, idleSince: "2026-07-20T00:00:00Z" },
  ],
};
