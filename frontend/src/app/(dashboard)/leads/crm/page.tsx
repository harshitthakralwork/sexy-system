import { CrmBoard } from "./crm-board";

// The board renders through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function CrmBoardPage() {
  return <CrmBoard />;
}
