import React from "react";

interface AppFooterProps {
  className?: string;
}

export function AppFooter({ className = "" }: AppFooterProps) {
  return (
    <footer className={`py-6 text-center text-xs text-[var(--color-muted)] ${className}`}>
      Developed by{" "}
      <span className="text-[var(--color-foreground)] hover:text-blue-500 font-semibold transition-colors">
        Harshit
      </span>
      ❤️
    </footer>
  );
}

