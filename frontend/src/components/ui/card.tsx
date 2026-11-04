import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[24px] border border-white/10 bg-[#2D2B30] p-5 shadow-sm transition-all hover:border-white/15",
        className
      )}
      {...props}
    />
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">{children}</h3>;
}

export function CardValue({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-2xl font-bold tracking-tight text-white font-sans">{children}</p>;
}

export function CardFootnote({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-xs text-[var(--color-muted)] font-medium">{children}</p>;
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
    <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-white/15 bg-white/[0.02] p-10 text-center">
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="mt-1.5 max-w-md text-xs text-[var(--color-muted)]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
