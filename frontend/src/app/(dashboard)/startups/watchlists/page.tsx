import { WatchlistsView } from "./watchlists-view";

// The watchlists render through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function WatchlistsPage() {
  return <WatchlistsView />;
}
