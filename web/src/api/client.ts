import type {
  ApprovalRequest,
  CostData,
  IncidentDetail,
  OverviewData,
  RegionalRiskData,
  SavingsData,
  TenantInfo,
  TopologyData,
} from "./types";
import { mockOverview } from "./mock/overview";
import { mockIncidentDetail } from "./mock/incidents";
import { mockTopology } from "./mock/topology";
import { mockApproval } from "./mock/approval";
import { mockRegionalRisk } from "./mock/risk";
import { mockCost } from "./mock/cost";
import { mockSavings } from "./mock/savings";
import { mockTenant } from "./mock/tenant";

/**
 * `VITE_USE_MOCK=false` once the backend exists; everything below then does a
 * same-origin `fetch` instead (see vite.config.ts proxy). No page imports the
 * mock data directly — only this file does, so the switch is one place.
 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getOverview(): Promise<OverviewData> {
  if (USE_MOCK) return mockOverview;
  return getJson<OverviewData>("/api/v1/overview");
}

export async function getIncident(id: string): Promise<IncidentDetail | null> {
  if (USE_MOCK) return mockIncidentDetail[id] ?? null;
  return getJson<IncidentDetail>(`/api/v1/incidents/${id}`);
}

export async function getTopology(): Promise<TopologyData> {
  if (USE_MOCK) return mockTopology;
  return getJson<TopologyData>("/api/v1/topology");
}

export async function getApproval(id: string): Promise<ApprovalRequest | null> {
  if (USE_MOCK) return mockApproval.id === id ? mockApproval : null;
  return getJson<ApprovalRequest>(`/api/v1/approvals/${id}`);
}

export async function getRegionalRisk(): Promise<RegionalRiskData> {
  if (USE_MOCK) return mockRegionalRisk;
  return getJson<RegionalRiskData>("/api/v1/risk/regions");
}

export async function getCost(): Promise<CostData> {
  if (USE_MOCK) return mockCost;
  return getJson<CostData>("/api/v1/cost");
}

export async function getSavings(): Promise<SavingsData> {
  if (USE_MOCK) return mockSavings;
  return getJson<SavingsData>("/api/v1/savings");
}

export async function getTenant(): Promise<TenantInfo> {
  if (USE_MOCK) return mockTenant;
  return getJson<TenantInfo>("/api/v1/tenant");
}
