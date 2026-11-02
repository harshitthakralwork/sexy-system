import { IntelligenceView } from "@/components/intelligence/intelligence-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function DemandPage() {
  return <IntelligenceView trackType="demand" />;
}
