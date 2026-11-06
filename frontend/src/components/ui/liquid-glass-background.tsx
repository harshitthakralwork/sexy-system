"use client";

export function LiquidGlassBackground() {
  return (
    <div aria-hidden className="astra-atmosphere pointer-events-none fixed inset-0 -z-30 select-none">
      <span className="astra-atmosphere__orb astra-atmosphere__orb--sky" />
      <span className="astra-atmosphere__orb astra-atmosphere__orb--blue" />
      <span className="astra-atmosphere__orb astra-atmosphere__orb--violet" />
      <span className="astra-atmosphere__grid" />
    </div>
  );
}
