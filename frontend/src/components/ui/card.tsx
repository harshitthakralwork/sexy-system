import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[26px] border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.38),0_18px_45px_rgba(45,48,43,0.12)] backdrop-blur-2xl transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-highlight)]",
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
  return <p className="mt-2 text-2xl font-bold tracking-tight text-[var(--color-foreground)] font-sans">{children}</p>;
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
    <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-[var(--color-border-highlight)] bg-[var(--color-surface)]/45 p-10 text-center">
      <p className="text-sm font-semibold text-[var(--color-foreground)]">{title}</p>
      <p className="mt-1.5 max-w-md text-xs text-[var(--color-muted)]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
