import type { ReactNode } from "react";

export interface DataTableColumn<Row> {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  align?: "left" | "right";
}

/** A plain, accessible table. Numbers render monospaced via the "tabular" class. */
export function DataTable<Row extends { id: string }>({
  columns,
  rows,
  caption,
}: {
  columns: DataTableColumn<Row>[];
  rows: Row[];
  caption?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`eyebrow px-3 py-2 ${col.align === "right" ? "text-right" : "text-left"}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border last:border-0">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`tabular px-3 py-2 ${col.align === "right" ? "text-right" : "text-left"}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
