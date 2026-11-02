import { DashboardView } from "@/components/dashboard/dashboard-view";

// The dashboard layout withholds children until the session check resolves
// client-side, so this segment can never be observed rendering instantly.
export const instant = false;

export default function DashboardPage() {
  return <DashboardView />;
}
