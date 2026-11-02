import { TracksView } from "./tracks-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function TracksPage() {
  return <TracksView />;
}
