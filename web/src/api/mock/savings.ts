import type { SavingsData } from "../types";
import { netSaving } from "../types";

const row = (incidentId: string, downtimeAvoidedUsd: number, actionCostUsd: number, overheadUsd: number) => ({
  incidentId,
  downtimeAvoidedUsd,
  actionCostUsd,
  overheadUsd,
  netSavingUsd: netSaving(downtimeAvoidedUsd, actionCostUsd, overheadUsd),
});

export const mockSavings: SavingsData = {
  entries: [
    row("INC-0042", 1800, 2.5, 5),
    row("INC-0041", 650, 11, 5),
    row("INC-0039", 220, 0.6, 5),
  ],
  assumptions: [
    "Downtime cost avoided is estimated at $600/minute for checkout-critical services.",
    "Action cost is the actual or estimated cloud spend for the chosen action, from the cost gate.",
    "Overhead is a flat $5 per incident for monitoring and audit logging.",
    "Savings assume the incident would have run for its full historical median duration without intervention.",
  ],
  sensitivity: [
    { minutes: 10, netSavingUsd: netSaving(6000, 2.5, 5) },
    { minutes: 20, netSavingUsd: netSaving(12000, 2.5, 5) },
    { minutes: 30, netSavingUsd: netSaving(18000, 2.5, 5) },
  ],
};
