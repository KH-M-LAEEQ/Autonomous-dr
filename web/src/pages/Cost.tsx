import { Card } from "../components/Card";
import { DataTable, type DataTableColumn } from "../components/DataTable";
import { AsyncStatus } from "../components/AsyncStatus";
import { getCost } from "../api/client";
import type { CostEstimateRow, PriceComparisonRow, UnusedResource } from "../api/types";
import { formatDateTime, formatUsd } from "../lib/format";
import { useAsyncData } from "../lib/useAsyncData";

const estimateColumns: DataTableColumn<CostEstimateRow>[] = [
  { key: "label", header: "Action", render: (row) => row.label },
  { key: "estimated", header: "Estimated", align: "right", render: (row) => formatUsd(row.estimatedUsd) },
  { key: "actual", header: "Actual", align: "right", render: (row) => formatUsd(row.actualUsd) },
];

const priceColumns: DataTableColumn<PriceComparisonRow & { id: string }>[] = [
  { key: "provider", header: "Provider", render: (row) => row.provider.toUpperCase() },
  { key: "resource", header: "Resource", render: (row) => row.resource },
  { key: "price", header: "Price / hr", align: "right", render: (row) => formatUsd(row.priceUsd) },
];

const unusedColumns: DataTableColumn<UnusedResource>[] = [
  { key: "name", header: "Resource", render: (row) => row.name },
  { key: "provider", header: "Provider", render: (row) => row.provider.toUpperCase() },
  { key: "cost", header: "Monthly cost", align: "right", render: (row) => formatUsd(row.monthlyCostUsd) },
  { key: "idle", header: "Idle since", render: (row) => formatDateTime(row.idleSince) },
];

export function Cost() {
  const state = useAsyncData(getCost);

  if (state.status !== "success") {
    return <AsyncStatus state={state} loadingLabel="Loading cost and waste…" />;
  }
  const data = state.data;

  const spendPercent = Math.min(100, Math.round((data.spendUsd / data.capUsd) * 100));

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Cost and waste</h1>
        <p className="mt-1 text-sm text-muted">What recovery actions have cost so far, and what is being wasted.</p>
      </header>

      <Card title="Spend vs. cap">
        <p className="tabular text-2xl font-semibold">
          {formatUsd(data.spendUsd)} of {formatUsd(data.capUsd)}
        </p>
        <div
          role="progressbar"
          aria-valuenow={spendPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Spend against cap"
          className="mt-3 h-2 w-full overflow-hidden rounded-full bg-border"
        >
          <div className="h-full rounded-full bg-accent" style={{ width: `${spendPercent}%` }} />
        </div>
      </Card>

      <Card title="Estimate vs. actual">
        <DataTable
          columns={estimateColumns}
          rows={data.estimates}
          caption="Estimated versus actual cost per action"
        />
      </Card>

      <Card title="Price comparison across providers">
        <DataTable
          columns={priceColumns}
          rows={data.priceComparison.map((row, index) => ({ ...row, id: `price-${index}` }))}
          caption="On-demand price comparison"
        />
      </Card>

      <Card title="Unused resources">
        <DataTable columns={unusedColumns} rows={data.unusedResources} caption="Idle resources costing money" />
      </Card>
    </div>
  );
}
