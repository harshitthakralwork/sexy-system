import { StartupsDashboard } from "./startups-dashboard";

// The dashboard renders through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function StartupsPage() {
  return <StartupsDashboard />;
}
