import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { SampleDataBadge } from "./SampleDataBadge";
import { getTenant } from "../api/client";
import type { TenantInfo } from "../api/types";

const DEFAULT_TENANT: TenantInfo = { name: "Loading…", budgetCapUsd: 0 };
const PENDING_APPROVALS = 1;

export function Layout() {
  const [tenant, setTenant] = useState<TenantInfo>(DEFAULT_TENANT);

  useEffect(() => {
    let cancelled = false;
    getTenant().then((data) => {
      if (!cancelled) setTenant(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text md:flex-row">
      <Sidebar approvalsCount={PENDING_APPROVALS} tenant={tenant} />
      <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
        <div className="mb-4 flex justify-end">
          <SampleDataBadge />
        </div>
        <Outlet />
      </main>
    </div>
  );
}
