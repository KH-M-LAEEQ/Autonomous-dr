/**
 * Shapes the mock layer returns today and the real FastAPI backend will return
 * later. This file is the contract both sides agree to — swap `api/client.ts`
 * from mock to real without touching any page or component.
 */

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

export type Severity = "low" | "medium" | "high" | "critical";

export type CloudProvider = "aws" | "azure" | "gcp";

export interface SourceLink {
  label: string;
  url: string;
}

export interface Citation {
  id: string;
  label: string;
  url?: string;
}

/** `Explanation`, per ADR-0009: structured, auditable, never a bare string. */
export interface Explanation {
  text: string;
  citations: Citation[];
  engine: "llm" | "template";
  unsupported: string[];
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export interface KpiSummary {
  id: string;
  label: string;
  value: number | null;
  unit?: string;
  trend?: "up" | "down" | "flat";
}

export interface RecoveryLatencyPoint {
  timestamp: string;
  latencySeconds: number | null;
}

export const RECOVERY_LATENCY_TARGET_SECONDS = 60;

export interface IncidentSummary {
  id: string;
  title: string;
  resourceId: string;
  provider: CloudProvider;
  severity: Severity;
  state: "open" | "investigating" | "resolved";
  openedAt: string;
}

export interface CloudStatusEntry {
  provider: CloudProvider;
  label: string;
  status: "healthy" | "degraded" | "down";
}

export interface ActivityLogEntry {
  id: string;
  timestamp: string;
  actor: string;
  message: string;
}

export interface OverviewData {
  kpis: KpiSummary[];
  recoveryLatency: RecoveryLatencyPoint[];
  incidents: IncidentSummary[];
  cloudStatus: CloudStatusEntry[];
  activity: ActivityLogEntry[];
}

// ---------------------------------------------------------------------------
// Incident detail
// ---------------------------------------------------------------------------

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  detail?: string;
}

export type VoteChoice = "approve" | "reject" | "abstain";

export interface Vote {
  voterId: string;
  choice: VoteChoice;
  reason: string | null;
  castAt: string;
}

/** Quorum rule: 2 of 3 monitor votes must approve (ADR-0004). */
export const QUORUM_REQUIRED = 2;
export const QUORUM_TOTAL = 3;

/**
 * Term keys a scored option's utility may be built from. The backend omits a
 * key when that term genuinely has no value for the option — never sends 0
 * as a stand-in. U = w_ability*Phi - w_cost*cost - w_latency*latency + w_safety*safety.
 */
export type TermKey =
  | "cost"
  | "latency"
  | "safety"
  | "impact"
  | "price_delta"
  | "risk";

export interface ScoredOption {
  id: string;
  name: string;
  utility: number;
  /** Missing key = "n/a" (no such term for this option). Present key, value 0, is a real zero. */
  terms: Partial<Record<TermKey, number>>;
  chosen: boolean;
}

export interface Decision {
  id: string;
  incidentId: string;
  weights: Record<string, number>;
  formulaVersion: string;
  options: ScoredOption[];
}

export interface BudgetCheck {
  capUsd: number;
  spentUsd: number;
  remainingUsd: number;
  passed: boolean;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  hash: string;
}

export interface IncidentDetail {
  id: string;
  title: string;
  resourceId: string;
  provider: CloudProvider;
  severity: Severity;
  state: "open" | "investigating" | "resolved";
  openedAt: string;
  timeline: TimelineEvent[];
  explanation: Explanation;
  votes: Vote[];
  decision: Decision;
  budgetCheck: BudgetCheck;
  auditEntries: AuditEntry[];
  canRollBack: boolean;
}

// ---------------------------------------------------------------------------
// Topology
// ---------------------------------------------------------------------------

export interface TopologyService {
  id: string;
  name: string;
  provider: CloudProvider;
  status: "healthy" | "degraded" | "failed";
}

export interface TopologyEdge {
  from: string;
  to: string;
}

export interface BlastRadius {
  affected: number;
  total: number;
}

export interface PredictedRisk {
  serviceId: string;
  probability: number;
}

export interface TopologyData {
  services: TopologyService[];
  edges: TopologyEdge[];
  failedServiceId: string;
  blastRadius: BlastRadius;
  predictedNextAtRisk: PredictedRisk;
}

// ---------------------------------------------------------------------------
// Approval (Tier 3)
// ---------------------------------------------------------------------------

export interface DryRunStep {
  id: string;
  description: string;
  status: "planned" | "would-succeed" | "would-fail";
}

export interface ApprovalRequest {
  id: string;
  incidentId: string;
  proposedAction: string;
  costUsd: number;
  budgetLeftUsd: number;
  etaSeconds: number;
  undoWindowSeconds: number;
  checksPassed: string[];
  dryRunPlan: DryRunStep[];
  countdownSeconds: number;
  fallbackTier: 2;
  fallbackDescription: string;
  status: "pending" | "approved" | "rejected" | "fell-back";
}

// ---------------------------------------------------------------------------
// Regional risk
// ---------------------------------------------------------------------------

export type RiskLevel = "low" | "elevated" | "high";

export const RISK_LEVEL_THRESHOLDS = {
  elevated: 0.33,
  high: 0.66,
} as const;

export function riskLevelFor(score: number): RiskLevel {
  if (score >= RISK_LEVEL_THRESHOLDS.high) return "high";
  if (score >= RISK_LEVEL_THRESHOLDS.elevated) return "elevated";
  return "low";
}

export interface RiskBreakdown {
  incidentDensity: number;
  advisorySeverity: number;
  geopoliticalFlag: number;
  weights: {
    incidentDensity: number;
    advisorySeverity: number;
    geopoliticalFlag: number;
  };
}

export interface RiskSignal {
  id: string;
  label: string;
  source: SourceLink;
  observedAt: string;
}

export interface RegionRisk {
  id: string;
  name: string;
  provider: CloudProvider;
  score: number;
  breakdown: RiskBreakdown;
  signals: RiskSignal[];
}

/** Tenant policy limit on the geopolitical weight term (ADR-0010, draft). */
export interface RiskWeightPolicy {
  min: number;
  max: number;
  default: number;
  current: number;
}

export interface RegionalRiskData {
  regions: RegionRisk[];
  weightPolicy: RiskWeightPolicy;
}

// ---------------------------------------------------------------------------
// Cost and waste
// ---------------------------------------------------------------------------

export const COST_CAP_USD = 25;

export interface CostEstimateRow {
  id: string;
  label: string;
  estimatedUsd: number | null;
  actualUsd: number | null;
}

export interface PriceComparisonRow {
  provider: CloudProvider;
  resource: string;
  priceUsd: number | null;
}

export interface UnusedResource {
  id: string;
  name: string;
  provider: CloudProvider;
  monthlyCostUsd: number;
  idleSince: string;
}

export interface CostData {
  spendUsd: number;
  capUsd: number;
  estimates: CostEstimateRow[];
  priceComparison: PriceComparisonRow[];
  unusedResources: UnusedResource[];
}

// ---------------------------------------------------------------------------
// Savings report
// ---------------------------------------------------------------------------

export interface SavingsEntry {
  incidentId: string;
  downtimeAvoidedUsd: number;
  actionCostUsd: number;
  overheadUsd: number;
  netSavingUsd: number;
}

export interface SensitivityPoint {
  minutes: 10 | 20 | 30;
  netSavingUsd: number;
}

export interface SavingsData {
  entries: SavingsEntry[];
  assumptions: string[];
  sensitivity: SensitivityPoint[];
}

export function netSaving(
  downtimeAvoidedUsd: number,
  actionCostUsd: number,
  overheadUsd: number,
): number {
  return downtimeAvoidedUsd - actionCostUsd - overheadUsd;
}

// ---------------------------------------------------------------------------
// App shell
// ---------------------------------------------------------------------------

export interface TenantInfo {
  name: string;
  budgetCapUsd: number;
}
