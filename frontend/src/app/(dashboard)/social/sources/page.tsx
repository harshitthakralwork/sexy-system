import { SourcesView } from "./sources-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function SourcesPage() {
  return <SourcesView />;
}
