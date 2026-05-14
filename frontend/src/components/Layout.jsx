import { useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Users, Truck, Briefcase, HardHat, ShieldAlert, Boxes,
  ShoppingCart, FileText, Wallet, ClipboardList, Wrench, Car, FolderArchive,
  CheckSquare, BarChart3, LogOut, Menu, Search, Bell, ChevronLeft, ChevronRight,
  User2, Construction
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";

const NAV_GROUPS = [
  {
    label: "Command",
    items: [
      { to: "/app", icon: LayoutDashboard, label: "Executive Dashboard", end: true, testid: "nav-dashboard" },
      { to: "/app/approvals", icon: CheckSquare, label: "Approvals", testid: "nav-approvals" },
      { to: "/app/reports", icon: BarChart3, label: "Reports", testid: "nav-reports" },
    ],
  },
  {
    label: "Operations",
    items: [
      { to: "/app/projects", icon: Briefcase, label: "Projects", testid: "nav-projects" },
      { to: "/app/safety", icon: ShieldAlert, label: "Safety", testid: "nav-safety" },
      { to: "/app/assets", icon: Wrench, label: "Assets", testid: "nav-assets" },
      { to: "/app/logistics", icon: Car, label: "Logistics", testid: "nav-logistics" },
    ],
  },
  {
    label: "Commerce",
    items: [
      { to: "/app/clients", icon: Users, label: "Clients", testid: "nav-clients" },
      { to: "/app/vendors", icon: Truck, label: "Vendors", testid: "nav-vendors" },
      { to: "/app/quotations", icon: FileText, label: "Sales & Quotations", testid: "nav-quotations" },
      { to: "/app/purchase-orders", icon: ShoppingCart, label: "Purchase Orders", testid: "nav-purchase" },
      { to: "/app/inventory", icon: Boxes, label: "Inventory & Stores", testid: "nav-inventory" },
    ],
  },
  {
    label: "People & Finance",
    items: [
      { to: "/app/employees", icon: HardHat, label: "Employees (HRMS)", testid: "nav-employees" },
      { to: "/app/attendance", icon: ClipboardList, label: "Attendance", testid: "nav-attendance" },
      { to: "/app/payroll", icon: Wallet, label: "Payroll", testid: "nav-payroll" },
      { to: "/app/accounts", icon: FileText, label: "Accounts & Finance", testid: "nav-accounts" },
      { to: "/app/documents", icon: FolderArchive, label: "Documents", testid: "nav-documents" },
    ],
  },
];

function SidebarBody({ collapsed, onItemClick }) {
  return (
    <nav className="flex flex-col gap-6 py-6">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          {!collapsed && (
            <div className="px-5 mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-sidebar-foreground/40">
              {group.label}
            </div>
          )}
          <div className="flex flex-col gap-0.5 px-2">
            {group.items.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.end}
                onClick={onItemClick}
                data-testid={it.testid}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center gap-3 px-3 py-2 rounded-sm text-sm transition-colors duration-150",
                    "text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground",
                    isActive && "bg-primary/10 text-primary border-l-2 border-primary -ml-[2px] pl-[14px]"
                  )
                }
                title={collapsed ? it.label : undefined}
              >
                <it.icon className="h-4 w-4 shrink-0" strokeWidth={2} />
                {!collapsed && <span className="truncate">{it.label}</span>}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const initials = (user?.name || user?.email || "U")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const breadcrumb = location.pathname.split("/").filter(Boolean).slice(1).join(" / ") || "executive";

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden lg:flex sticky top-0 h-screen flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-[width] duration-200",
          collapsed ? "w-16" : "w-64"
        )}
        data-testid="desktop-sidebar"
      >
        <div className="flex items-center justify-between px-4 h-16 border-b border-sidebar-border">
          <Brand compact={collapsed} />
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-sidebar-foreground/60 hover:text-primary"
            data-testid="sidebar-collapse-btn"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <SidebarBody collapsed={collapsed} />
        </div>
        {!collapsed && (
          <div className="px-4 py-3 border-t border-sidebar-border flex items-center gap-2 text-xs text-sidebar-foreground/50">
            <Construction className="h-3.5 w-3.5" />
            <span>v1.0 · Industrial Build</span>
          </div>
        )}
      </aside>

      {/* Mobile sheet */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-0 bg-sidebar text-sidebar-foreground border-sidebar-border">
          <div className="flex items-center px-4 h-16 border-b border-sidebar-border">
            <Brand />
          </div>
          <div className="overflow-y-auto h-[calc(100vh-64px)]">
            <SidebarBody collapsed={false} onItemClick={() => setMobileOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-30 h-16 flex items-center gap-3 px-4 lg:px-6 bg-background/80 backdrop-blur-md border-b border-border">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
            <Menu className="h-5 w-5" />
          </Button>
          <div className="hidden md:flex items-center gap-2 text-xs uppercase tracking-[0.15em] text-muted-foreground">
            <span>Module</span>
            <span className="text-primary">/</span>
            <span className="text-foreground font-semibold">{breadcrumb}</span>
          </div>
          <div className="hidden md:flex items-center gap-2 ml-4 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search projects, clients, POs…"
                className="pl-9 h-9 rounded-sm border-border bg-muted/40"
                data-testid="global-search"
              />
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="icon" className="relative h-9 w-9 rounded-sm border border-border" data-testid="notifications-btn">
              <Bell className="h-4 w-4" />
              <span className="absolute top-1 right-1 h-1.5 w-1.5 bg-primary rounded-full" />
            </Button>
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 pl-1 pr-3 h-9 border border-border rounded-sm hover:border-primary/60 transition-colors" data-testid="user-menu-btn">
                  <Avatar className="h-7 w-7 rounded-sm">
                    <AvatarFallback className="rounded-sm bg-primary text-primary-foreground text-xs font-bold">{initials}</AvatarFallback>
                  </Avatar>
                  <div className="hidden md:block text-left leading-tight">
                    <div className="text-xs font-semibold">{user?.name}</div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{user?.role?.replaceAll("_", " ")}</div>
                  </div>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 rounded-sm">
                <DropdownMenuLabel className="text-xs">
                  <div className="font-semibold">{user?.name}</div>
                  <div className="text-muted-foreground">{user?.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/app/profile")} data-testid="menu-profile">
                  <User2 className="h-4 w-4 mr-2" /> Profile & Roles
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onLogout} data-testid="menu-logout" className="text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
