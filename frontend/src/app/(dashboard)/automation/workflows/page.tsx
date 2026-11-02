import { WorkflowsView } from "./workflows-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function WorkflowsPage() {
  return <WorkflowsView />;
}
