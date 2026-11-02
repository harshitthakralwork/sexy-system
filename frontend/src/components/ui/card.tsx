import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-border bg-[var(--color-surface)] p-4", className)}
      {...props}
    />
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-medium text-[var(--color-muted)]">{children}</h3>;
}

export function CardValue({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-xl font-semibold tracking-tight">{children}</p>;
}

export function CardFootnote({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-xs text-[var(--color-muted)]">{children}</p>;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border p-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-md text-xs text-[var(--color-muted)]">{description}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
