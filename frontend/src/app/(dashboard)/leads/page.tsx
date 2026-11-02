import { LeadsList } from "./leads-list";

// The page renders through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function LeadsPage() {
  return <LeadsList />;
}
