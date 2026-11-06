import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "liquid-glass-panel rounded-2xl p-6 text-[var(--color-foreground)]",
        className
      )}
      {...props}
    />
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="title-4 uppercase tracking-wider text-[var(--color-muted)]">{children}</h3>;
}

export function CardValue({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-2xl font-semibold tracking-tight text-[var(--color-foreground)] font-sans">{children}</p>;
}

export function CardFootnote({ children }: { children: ReactNode }) {
  return <p className="mt-2 caption-2 text-[var(--color-muted)]">{children}</p>;
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
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--color-border-highlight)] bg-[var(--color-surface)]/70 p-10 text-center">
      <p className="title-4 text-[var(--color-foreground)]">{title}</p>
      <p className="mt-2 max-w-md caption-2 text-[var(--color-muted)]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
