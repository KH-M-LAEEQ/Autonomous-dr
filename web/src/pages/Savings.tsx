import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "../components/Card";
import { DataTable, type DataTableColumn } from "../components/DataTable";
import { getSavings } from "../api/client";
import type { SavingsData, SavingsEntry } from "../api/types";
import { formatUsd } from "../lib/format";

const entryColumns: DataTableColumn<SavingsEntry & { id: string }>[] = [
  { key: "incident", header: "Incident", render: (row) => row.incidentId },
  { key: "avoided", header: "Downtime avoided", align: "right", render: (row) => formatUsd(row.downtimeAvoidedUsd) },
  { key: "action", header: "Action cost", align: "right", render: (row) => formatUsd(row.actionCostUsd) },
  { key: "overhead", header: "Overhead", align: "right", render: (row) => formatUsd(row.overheadUsd) },
  { key: "net", header: "Net saving", align: "right", render: (row) => formatUsd(row.netSavingUsd) },
];

export function Savings() {
  const [data, setData] = useState<SavingsData | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSavings().then((result) => {
      if (!cancelled) setData(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return <p className="text-sm text-muted">Loading savings report…</p>;
  }

  const totalNet = data.entries.reduce((sum, entry) => sum + entry.netSavingUsd, 0);
  const chartData = data.sensitivity.map((point) => ({
    label: `${point.minutes} min`,
    netSaving: point.netSavingUsd,
  }));

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Savings report</h1>
        <p className="mt-1 text-sm text-muted">
          Net saving = downtime avoided − action cost − overhead.
        </p>
      </header>

      <Card title="Total net saving">
        <p className="tabular text-2xl font-semibold">{formatUsd(totalNet)}</p>
      </Card>

      <Card title="Per-incident breakdown">
        <DataTable
          columns={entryColumns}
          rows={data.entries.map((entry) => ({ ...entry, id: entry.incidentId }))}
          caption="Net saving per incident"
        />
      </Card>

      <Card title="Sensitivity — if downtime had lasted longer">
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#DAD9D1" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#5C675F" />
              <YAxis tick={{ fontSize: 11 }} stroke="#5C675F" />
              <Tooltip
                formatter={(value) => [
                  formatUsd(typeof value === "number" ? value : null),
                  "Net saving",
                ]}
              />
              <Bar dataKey="netSaving" fill="#0B5D5A" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card title="Assumptions">
        <ul className="flex flex-col gap-1.5 text-sm">
          {data.assumptions.map((assumption) => (
            <li key={assumption} className="flex gap-2">
              <span aria-hidden="true">·</span>
              <span>{assumption}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
