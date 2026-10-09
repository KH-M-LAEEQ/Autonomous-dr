import type { TopologyData } from "../types";

export const mockTopology: TopologyData = {
  services: [
    { id: "svc-edge", name: "Edge gateway", provider: "aws", status: "healthy" },
    { id: "svc-checkout-api", name: "Checkout API", provider: "aws", status: "failed" },
    { id: "svc-order-queue", name: "Order queue", provider: "gcp", status: "degraded" },
    { id: "svc-payments", name: "Payments service", provider: "aws", status: "healthy" },
    { id: "svc-inventory", name: "Inventory service", provider: "azure", status: "healthy" },
    { id: "svc-notifications", name: "Notifications", provider: "gcp", status: "healthy" },
  ],
  edges: [
    { from: "svc-edge", to: "svc-checkout-api" },
    { from: "svc-checkout-api", to: "svc-order-queue" },
    { from: "svc-checkout-api", to: "svc-payments" },
    { from: "svc-order-queue", to: "svc-inventory" },
    { from: "svc-order-queue", to: "svc-notifications" },
  ],
  failedServiceId: "svc-checkout-api",
  blastRadius: { affected: 3, total: 6 },
  predictedNextAtRisk: { serviceId: "svc-order-queue", probability: 0.42 },
};
