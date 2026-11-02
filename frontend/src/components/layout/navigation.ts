import {
  BarChart3,
  Bookmark,
  Briefcase,
  Building2,
  CalendarClock,
  CheckSquare,
  Compass,
  FileText,
  FolderKanban,
  Globe,
  LayoutDashboard,
  ListChecks,
  MapPinned,
  Mail,
  Bell,
  Radar,
  Search,
  Settings,
  Shield,
  Sparkles,
  Target,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

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
      { label: "Reports", href: "/analytics#saved-reports", icon: FileText, available: true },
      { label: "Global Search", href: "/search", icon: Search, available: true },
    ],
  },
  {
    title: "Leads Intelligence",
    items: [
      { label: "Leads Dashboard", href: "/leads", icon: Radar, available: true },
      { label: "Discover Businesses", href: "/leads/discover", icon: Compass, available: false },
      { label: "Map Explorer", href: "/leads/map", icon: MapPinned, available: true },
      { label: "Raw Results", href: "/leads/raw", icon: ListChecks, available: false },
      { label: "Qualified Leads", href: "/leads/qualified", icon: CheckSquare, available: false },
      { label: "CRM Pipeline", href: "/leads/crm", icon: FolderKanban, available: true },
      { label: "Service Catalog", href: "/leads/services", icon: Briefcase, available: true },
    ],
  },
  {
    title: "Startup Intelligence",
    items: [
      { label: "Startup Dashboard", href: "/startups", icon: Sparkles, available: true },
      { label: "Discover Startups", href: "/startups/discover", icon: Compass, available: false },
      { label: "Watchlists", href: "/startups/watchlists", icon: Users, available: true },
    ],
  },
  {
    title: "Social Intelligence",
    items: [
      { label: "Social Research", href: "/social", icon: Globe, available: true },
    ],
  },
  {
    title: "Social & Demand Intelligence",
    items: [
      { label: "Intelligence Overview", href: "/intelligence", icon: LayoutDashboard, available: true },
      { label: "Demand Intelligence", href: "/intelligence/demand", icon: Target, available: true },
      { label: "Business Intelligence", href: "/intelligence/business", icon: Building2, available: true },
      { label: "Discovery Tracks", href: "/intelligence/tracks", icon: Radar, available: true },
      { label: "Saved Items", href: "/intelligence/saved", icon: Bookmark, available: true },
      { label: "Sources", href: "/social/sources", icon: Globe, available: true },
    ],
  },
  {
    title: "Automation",
    items: [
      { label: "Workflow Builder", href: "/automation/workflows", icon: Workflow, available: true },
      { label: "Scheduler", href: "/automation/scheduler", icon: CalendarClock, available: true },
      { label: "Approval Queue", href: "/automation/approvals", icon: CheckSquare, available: true },
      { label: "Email Outreach", href: "/email", icon: Mail, available: true },
    ],
  },
  {
    title: "Infrastructure",
    items: [
      { label: "Source Manager", href: "/sources", icon: Shield, available: false },
      { label: "Settings", href: "/settings", icon: Settings, available: false },
      { label: "Notifications", href: "/notifications", icon: Bell, available: false },
    ],
  },
];
