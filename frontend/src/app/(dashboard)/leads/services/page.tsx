import { ServiceCatalog } from "./service-catalog";

// The catalog renders through client-side session and data fetching, so this
// segment can never be observed rendering instantly.
export const instant = false;

export default function ServiceCatalogPage() {
  return <ServiceCatalog />;
}
