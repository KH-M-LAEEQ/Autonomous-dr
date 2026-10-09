import { useState } from "react";
import { NavLink } from "react-router-dom";
import type { TenantInfo } from "../api/types";

const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/incidents/INC-0042", label: "Incidents" },
  { to: "/topology", label: "Topology" },
  { to: "/approvals/APR-1182", label: "Approvals", badgeKey: "approvals" as const },
  { to: "/risk", label: "Regional risk" },
  { to: "/cost", label: "Cost and waste" },
  { to: "/savings", label: "Savings report" },
];

function NavLinks({
  approvalsCount,
  onNavigate,
}: {
  approvalsCount: number;
  onNavigate?: () => void;
}) {
  return (
    <ul className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex min-h-11 items-center justify-between rounded-md px-3 py-2 text-sm font-medium text-white/90 ${
                isActive ? "bg-sidebar-active text-white" : "hover:bg-sidebar-active/60"
              }`
            }
          >
            <span>{item.label}</span>
            {item.badgeKey === "approvals" && approvalsCount > 0 && (
              <span className="tabular rounded-full bg-accent px-2 py-0.5 text-xs text-white">
                {approvalsCount}
              </span>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

export function Sidebar({
  approvalsCount,
  tenant,
}: {
  approvalsCount: number;
  tenant: TenantInfo;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Phone width: a top bar with a menu button instead of a fixed sidebar. */}
      <header className="flex min-h-14 items-center justify-between bg-sidebar px-4 py-2 text-white md:hidden">
        <span className="text-sm font-semibold">AutonomousDR</span>
        <button
          type="button"
          onClick={() => setMobileOpen((open) => !open)}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-md border border-white/20"
        >
          <span className="sr-only">{mobileOpen ? "Close menu" : "Open menu"}</span>
          <span aria-hidden="true">{mobileOpen ? "✕" : "☰"}</span>
        </button>
      </header>
      {mobileOpen && (
        <nav id="mobile-nav" className="bg-sidebar px-4 pb-4 text-white md:hidden">
          <NavLinks approvalsCount={approvalsCount} onNavigate={() => setMobileOpen(false)} />
        </nav>
      )}

      <aside className="hidden w-[232px] shrink-0 flex-col bg-sidebar px-3 py-5 text-white md:flex">
        <div className="px-2 pb-6">
          <p className="text-sm font-semibold">AutonomousDR</p>
          <p className="eyebrow text-white/50">Control plane</p>
        </div>
        <nav className="flex-1">
          <NavLinks approvalsCount={approvalsCount} />
        </nav>
        <footer className="mt-6 border-t border-white/10 px-2 pt-4 text-xs text-white/60">
          <p className="font-medium text-white/80">{tenant.name}</p>
          <p className="tabular mt-1">Budget cap ${tenant.budgetCapUsd.toFixed(2)}</p>
        </footer>
      </aside>
    </>
  );
}
