import { AnalyticsView } from "./analytics-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function AnalyticsPage() {
  return <AnalyticsView />;
}
