import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "refraction-glass-card rounded-[26px] border border-white/15 bg-[rgba(14,18,30,0.52)] p-5 text-white shadow-2xl backdrop-blur-2xl transition-all hover:border-white/25",
        className
      )}
      {...props}
    />
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50">{children}</h3>;
}

export function CardValue({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-2xl font-bold tracking-tight text-white font-sans">{children}</p>;
}

export function CardFootnote({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-xs text-white/60 font-medium">{children}</p>;
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
    <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-white/20 bg-white/[0.03] p-10 text-center backdrop-blur-md">
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="mt-1.5 max-w-md text-xs text-white/60">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
