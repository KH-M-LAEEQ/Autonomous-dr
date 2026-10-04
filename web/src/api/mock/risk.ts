import type { RegionalRiskData } from "../types";

export const mockRegionalRisk: RegionalRiskData = {
  weightPolicy: { min: 0.0, max: 0.3, default: 0.1, current: 0.1 },
  regions: [
    {
      id: "us-east-1",
      name: "US East (N. Virginia)",
      provider: "aws",
      score: 0.22,
      breakdown: {
        incidentDensity: 0.3,
        advisorySeverity: 0.2,
        geopoliticalFlag: 0.1,
        weights: { incidentDensity: 0.3, advisorySeverity: 0.4, geopoliticalFlag: 0.3 },
      },
      signals: [
        { id: "sig-1", label: "3 advisories in the last 7 days", source: { label: "AWS Health Dashboard", url: "https://example.internal/aws-health" }, observedAt: "2026-10-03T00:00:00Z" },
      ],
    },
    {
      id: "eu-west-1",
      name: "EU West (Ireland)",
      provider: "aws",
      score: 0.48,
      breakdown: {
        incidentDensity: 0.5,
        advisorySeverity: 0.5,
        geopoliticalFlag: 0.4,
        weights: { incidentDensity: 0.3, advisorySeverity: 0.4, geopoliticalFlag: 0.3 },
      },
      signals: [
        { id: "sig-2", label: "Regional power advisory", source: { label: "Provider status page", url: "https://example.internal/status/eu-west-1" }, observedAt: "2026-10-02T00:00:00Z" },
        { id: "sig-3", label: "Elevated geopolitical tension flag", source: { label: "OSINT feed", url: "https://example.internal/osint/eu-west-1" }, observedAt: "2026-10-01T00:00:00Z" },
      ],
    },
    {
      id: "ap-southeast-1",
      name: "Asia Pacific (Singapore)",
      provider: "gcp",
      score: 0.74,
      breakdown: {
        incidentDensity: 0.7,
        advisorySeverity: 0.8,
        geopoliticalFlag: 0.7,
        weights: { incidentDensity: 0.3, advisorySeverity: 0.4, geopoliticalFlag: 0.3 },
      },
      signals: [
        { id: "sig-4", label: "Submarine cable maintenance window", source: { label: "Provider status page", url: "https://example.internal/status/ap-southeast-1" }, observedAt: "2026-10-04T00:00:00Z" },
        { id: "sig-5", label: "High severity advisory open", source: { label: "GCP Status", url: "https://example.internal/gcp-status" }, observedAt: "2026-10-04T00:00:00Z" },
      ],
    },
    {
      id: "centralus",
      name: "Central US",
      provider: "azure",
      score: 0.15,
      breakdown: {
        incidentDensity: 0.1,
        advisorySeverity: 0.1,
        geopoliticalFlag: 0.2,
        weights: { incidentDensity: 0.3, advisorySeverity: 0.4, geopoliticalFlag: 0.3 },
      },
      signals: [],
    },
  ],
};
