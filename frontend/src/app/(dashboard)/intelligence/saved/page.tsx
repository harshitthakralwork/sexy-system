import { SavedView } from "../saved-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function SavedPage() {
  return <SavedView />;
}
