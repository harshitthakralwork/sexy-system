import { ApprovalsView } from "./approvals-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function ApprovalsPage() {
  return <ApprovalsView />;
}
