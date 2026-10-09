import type { ReactNode } from "react";

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-border bg-card p-4 ${className}`}
      aria-labelledby={title ? `card-${title.replace(/\s+/g, "-").toLowerCase()}` : undefined}
    >
      {title && (
        <h2
          id={`card-${title.replace(/\s+/g, "-").toLowerCase()}`}
          className="eyebrow mb-3"
        >
          {title}
        </h2>
      )}
      {children}
    </section>
  );
}
