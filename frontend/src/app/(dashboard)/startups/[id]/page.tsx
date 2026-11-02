import { StartupProfile } from "./startup-profile";

// The profile loads through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function StartupProfilePage() {
  return <StartupProfile />;
}
