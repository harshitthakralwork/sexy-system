import { SocialDashboard } from "./social-dashboard";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function SocialPage() {
  return <SocialDashboard />;
}
