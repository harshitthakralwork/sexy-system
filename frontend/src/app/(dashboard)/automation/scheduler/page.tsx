import { SchedulesView } from "./schedules-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function SchedulerPage() {
  return <SchedulesView />;
}
