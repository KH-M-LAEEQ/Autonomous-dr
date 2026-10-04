import type { ApprovalRequest } from "../types";

export const mockApproval: ApprovalRequest = {
  id: "APR-1182",
  incidentId: "INC-0042",
  proposedAction: "Fail over svc-checkout-api to the secondary region (us-west-2)",
  costUsd: 40.0,
  budgetLeftUsd: 22.5,
  etaSeconds: 180,
  undoWindowSeconds: 900,
  checksPassed: [
    "Dry run completed with no errors",
    "Secondary region capacity confirmed",
    "Budget check passed",
    "No conflicting action in progress",
  ],
  dryRunPlan: [
    { id: "step-1", description: "Drain connections from primary instance", status: "would-succeed" },
    { id: "step-2", description: "Promote secondary region replica", status: "would-succeed" },
    { id: "step-3", description: "Update DNS routing weight", status: "would-succeed" },
    { id: "step-4", description: "Verify health checks on new primary", status: "planned" },
  ],
  countdownSeconds: 900,
  fallbackTier: 2,
  fallbackDescription:
    "If nobody answers before the countdown ends, this request falls back to a Tier 2 action (scale out in place) instead of running automatically.",
  status: "pending",
};
