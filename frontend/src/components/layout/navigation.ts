import { BarChart3, Bell, Compass, Globe, LayoutDashboard, ListChecks, MapPinned, Radar, Search, Settings, Shield, Target, type LucideIcon } from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /**
   * False renders the entry as unavailable instead of linking to an empty page.
   * DESIGN.md section 3.2: unfinished modules must not look operational.
   */
  available: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const navigation: NavSection[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, available: true },
      { label: "Analytics", href: "/analytics", icon: BarChart3, available: true },
    ],
  },
  {
    title: "Find prospects",
    items: [
      { label: "Local business finder", href: "/leads/map", icon: MapPinned, available: true },
      { label: "Verified web prospects", href: "/prospecting", icon: Compass, available: true },
      { label: "Lead results", href: "/leads/raw", icon: ListChecks, available: true },
      { label: "Business discovery", href: "/leads/discover", icon: Compass, available: true },
    ],
  },
  {
    title: "Demand research",
    items: [
      { label: "Social research", href: "/social", icon: Globe, available: true },
      { label: "Demand signals", href: "/intelligence/demand", icon: Target, available: true },
      { label: "Discovery tracks", href: "/intelligence/tracks", icon: Radar, available: true },
      { label: "Post explorer", href: "/intelligence/posts", icon: Search, available: true },
    ],
  },
  {
    title: "Workspace",
    items: [
      { label: "Source health", href: "/sources", icon: Shield, available: true },
      { label: "Alerts", href: "/notifications", icon: Bell, available: true },
      { label: "Settings", href: "/settings", icon: Settings, available: true },
    ],
  },
];
