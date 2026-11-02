import { SearchView } from "./search-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function SearchPage() {
  return <SearchView />;
}
