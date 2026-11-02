import { EmailView } from "./email-view";

// Renders through client-side session and data fetching only.
export const instant = false;

export default function EmailPage() {
  return <EmailView />;
}
