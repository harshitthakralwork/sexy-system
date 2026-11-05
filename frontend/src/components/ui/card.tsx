import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "liquid-glass-panel rounded-[26px] p-5 text-[var(--color-foreground)] transition-all",
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
  return <p className="mt-2 text-2xl font-extrabold tracking-tight text-[var(--color-foreground)] font-sans">{children}</p>;
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
    <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-slate-300/40 dark:border-white/20 bg-slate-900/5 dark:bg-white/[0.03] p-10 text-center backdrop-blur-md">
      <p className="text-sm font-semibold text-[var(--color-foreground)]">{title}</p>
      <p className="mt-1.5 max-w-md text-xs text-[var(--color-muted)]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
