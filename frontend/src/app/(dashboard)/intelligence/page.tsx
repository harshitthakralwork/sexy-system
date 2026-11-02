import { OverviewView } from "./overview-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function IntelligencePage() {
  return <OverviewView />;
}
