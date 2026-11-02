import { BusinessProfile } from "./business-profile";

// The profile loads through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function BusinessProfilePage() {
  return <BusinessProfile />;
}
