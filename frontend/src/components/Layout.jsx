import { useState, useMemo } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  LogOut, Menu, Search, ChevronLeft, ChevronRight, User2, Construction,
  LayoutGrid, Mail, ChevronDown, PanelLeftClose, PanelLeftOpen, Eye, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import MyApprovalsInbox from "@/components/MyApprovalsInbox";
import NotificationBell from "@/components/NotificationBell";
import PageHelp from "@/components/PageHelp";
import AccessDeniedOverlay from "@/components/AccessDeniedOverlay";
import RouteGuard from "@/components/RouteGuard";
import useVisitTracker from "@/hooks/useVisitTracker";
import {
  DEPARTMENTS, MENU_ITEMS, isItemVisible,
} from "@/config/menuConfig";

/* ─────────── Sidebar Body ─────────── */
function SidebarBody({ collapsed, onItemClick, can, role, query }) {
  const location = useLocation();
  const STORAGE_KEY = "sidebar.openMap.v2";
  const [openMap, setOpenMap] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  });

  const filteredItems = useMemo(() => {
    const q = (query || "").trim().toLowerCase();
    return MENU_ITEMS.filter((it) => {
      if (!isItemVisible(it, { role, can })) return false;
      if (!q) return true;
      return it.label.toLowerCase().includes(q) || (it.to || "").toLowerCase().includes(q);
    });
  }, [query, role, can]);

  // Group filtered items by department then by parentLabel
  const grouped = useMemo(() => {
    const byDept = {};
    for (const it of filteredItems) {
      if (!byDept[it.department]) byDept[it.department] = {};
      const sub = it.parentLabel || "_root";
      if (!byDept[it.department][sub]) byDept[it.department][sub] = [];
      byDept[it.department][sub].push(it);
    }
    return byDept;
  }, [filteredItems]);

  const isDeptActive = (deptKey) =>
    Object.values(grouped[deptKey] || {}).flat().some((it) => it.to && location.pathname === it.to);

  const isDeptOpen = (deptKey) => {
    if (openMap[deptKey] !== undefined) return openMap[deptKey];
    // Open by default when there's a search query or when the dept matches active route
    if (query) return true;
    return isDeptActive(deptKey);
  };

  const toggleDept = (deptKey) =>
    setOpenMap((m) => {
      const next = { ...m, [deptKey]: !isDeptOpen(deptKey) };
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });

  const isSubOpen = (key) => openMap[key] !== false;  // sub-groups open by default
  const toggleSub = (key) =>
    setOpenMap((m) => {
      const next = { ...m, [key]: openMap[key] === false ? true : false };
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });

  const renderLeaf = (it, depth = 1) => {
    if (it.comingSoon) {
      return (
        <div
          key={it.testid}
          data-testid={it.testid}
          title="Coming soon"
          className={cn(
            "group flex items-center gap-3 px-3 py-2 rounded-sm text-sm cursor-not-allowed",
            "text-sidebar-foreground/40",
            depth > 0 && !collapsed && "ml-6 text-xs",
          )}
        >
          <it.icon className="h-4 w-4 shrink-0 opacity-60" strokeWidth={2} />
          {!collapsed && (
            <>
              <span className="truncate flex-1">{it.label}</span>
              <span className="text-[9px] px-1.5 py-0.5 bg-muted text-muted-foreground rounded-sm">Soon</span>
            </>
          )}
        </div>
      );
    }
    return (
      <NavLink
        key={it.testid}
        to={it.to}
        end={it.end}
        onClick={onItemClick}
        data-testid={it.testid}
        className={({ isActive }) =>
          cn(
            "group flex items-center gap-3 px-3 py-2 rounded-sm text-sm transition-colors duration-150",
            "text-sidebar-foreground/70 hover:bg-primary/10 hover:text-primary",
            depth > 0 && !collapsed && "ml-6 text-xs",
            isActive && "bg-primary/10 text-primary border-l-2 border-primary -ml-[2px] pl-[14px]",
          )
        }
        title={collapsed ? it.label : undefined}
      >
        <it.icon className="h-4 w-4 shrink-0" strokeWidth={2} />
        {!collapsed && <span className="truncate">{it.label}</span>}
      </NavLink>
    );
  };

  const renderSubGroup = (deptKey, subLabel, items) => {
    const key = `${deptKey}__${subLabel}`;
    const open = isSubOpen(key);
    return (
      <div key={key} className="ml-2 mt-1">
        {!collapsed && (
          <button
            type="button"
            onClick={() => toggleSub(key)}
            className="w-full flex items-center justify-between px-2 py-1 text-[10px] uppercase tracking-wider text-sidebar-foreground/50 hover:text-primary"
            data-testid={`sub-${key}`}
          >
            <span>{subLabel}</span>
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        )}
        {(open || collapsed) && (
          <div className="flex flex-col gap-0.5">
            {items.map((it) => renderLeaf(it, 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <nav className="flex flex-col gap-3 py-4">
      {DEPARTMENTS.map((dept) => {
        if (dept.superAdminOnly && role !== "super_admin") return null;
        const deptGroups = grouped[dept.key];
        if (!deptGroups) return null;
        const totalCount = Object.values(deptGroups).flat().length;
        const open = isDeptOpen(dept.key);
        const active = isDeptActive(dept.key);
        return (
          <div key={dept.key} data-testid={`sidebar-dept-${dept.key}`}>
            <button
              type="button"
              onClick={() => toggleDept(dept.key)}
              data-testid={`sidebar-dept-${dept.key}-toggle`}
              aria-expanded={open}
              className={cn(
                "w-full group flex items-center gap-3 px-3 py-2 rounded-sm text-sm font-medium transition-colors duration-150",
                "text-sidebar-foreground hover:bg-primary/10 hover:text-primary",
                active && "text-primary",
              )}
              title={collapsed ? dept.label : undefined}
            >
              <dept.icon className="h-4 w-4 shrink-0" strokeWidth={2} />
              {!collapsed && (
                <>
                  <span className="truncate flex-1 text-left">{dept.label}</span>
                  <span className="text-[10px] text-muted-foreground mr-1">{totalCount}</span>
                  {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                </>
              )}
            </button>
            {open && (
              <div className="flex flex-col gap-0.5 mt-0.5 ml-3 border-l border-sidebar-border pl-1" data-testid={`sidebar-dept-${dept.key}-items`}>
                {/* Root items first */}
                {(deptGroups._root || []).map((it) => renderLeaf(it, 1))}
                {/* Then sub-groups */}
                {Object.entries(deptGroups)
                  .filter(([k]) => k !== "_root")
                  .map(([sub, items]) => renderSubGroup(dept.key, sub, items))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

/* ─────────── Main Layout ─────────── */
export default function Layout({ children }) {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  useVisitTracker(!!user);
  const SIDEBAR_COLLAPSED_KEY = "sidebar.collapsed.v1";
  const [collapsed, setCollapsedRaw] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1"; }
    catch { return false; }
  });
  const setCollapsed = (next) => {
    setCollapsedRaw((prev) => {
      const value = typeof next === "function" ? next(prev) : next;
      try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? "1" : "0"); } catch { /* ignore */ }
      return value;
    });
  };
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuQuery, setMenuQuery] = useState("");

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
          collapsed ? "w-16" : "w-64",
        )}
        data-testid="desktop-sidebar"
      >
        <div
          className={cn(
            "h-16 border-b border-sidebar-border flex items-center",
            collapsed ? "justify-center px-0" : "justify-between px-4",
          )}
        >
          {!collapsed && <Brand compact={false} />}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-sidebar-foreground/60 hover:text-primary p-1.5 rounded-md hover:bg-sidebar-accent/40"
            data-testid="sidebar-collapse-btn"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>
        {!collapsed && (
          <div className="px-3 py-2 border-b border-sidebar-border">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-sidebar-foreground/40" />
              <Input
                placeholder="Search menu…"
                className="pl-7 h-8 text-xs rounded-sm bg-sidebar-accent/20 border-sidebar-border"
                value={menuQuery}
                onChange={(e) => setMenuQuery(e.target.value)}
                data-testid="sidebar-search"
              />
            </div>
          </div>
        )}
        <div className="flex-1 overflow-y-auto">
          <SidebarBody collapsed={collapsed} can={can} role={user?.role} query={menuQuery} />
        </div>
        {!collapsed && (
          <div className="px-4 py-3 border-t border-sidebar-border flex items-center gap-2 text-xs text-sidebar-foreground/50">
            <Construction className="h-3.5 w-3.5" />
            <span>INDIAN TRADE LINKS · ERP v1.2</span>
          </div>
        )}
      </aside>

      {/* Mobile sheet */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-0 bg-sidebar text-sidebar-foreground border-sidebar-border">
          <div className="flex items-center px-4 h-16 border-b border-sidebar-border">
            <Brand />
          </div>
          <div className="px-3 py-2 border-b border-sidebar-border">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-sidebar-foreground/40" />
              <Input
                placeholder="Search menu…"
                className="pl-7 h-8 text-xs rounded-sm bg-sidebar-accent/20 border-sidebar-border"
                value={menuQuery}
                onChange={(e) => setMenuQuery(e.target.value)}
                data-testid="sidebar-search-mobile"
              />
            </div>
          </div>
          <div className="overflow-y-auto h-[calc(100vh-130px)]">
            <SidebarBody collapsed={false} onItemClick={() => setMobileOpen(false)} can={can} role={user?.role} query={menuQuery} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Access Preview banner (impersonation) */}
        {user?.impersonated && (
          <div className="sticky top-0 z-40 h-9 flex items-center gap-3 px-4 lg:px-6 bg-orange-500 text-white text-sm font-semibold shadow-md" data-testid="impersonation-banner">
            <Eye className="h-4 w-4 shrink-0" />
            <span className="truncate">
              Access Preview — viewing as <b>{user?.name || user?.email}</b> ({(user?.role || "").replaceAll("_", " ")})
              {user?.impersonator_name ? ` · started by ${user.impersonator_name}` : ""}
            </span>
            <button
              onClick={async () => {
                try {
                  await api.post("/admin/impersonation/stop");
                  window.location.href = "/app/admin/users";
                } catch (e) {
                  window.location.href = "/login";
                }
              }}
              className="ml-auto shrink-0 inline-flex items-center gap-1.5 rounded-sm bg-white/20 hover:bg-white/30 px-3 py-1 text-xs font-bold uppercase tracking-wider transition-colors"
              data-testid="exit-preview-btn"
            >
              <LogOut className="h-3.5 w-3.5" /> Exit Preview
            </button>
          </div>
        )}
        {/* Topbar */}
        <header className={cn("sticky z-30 h-16 flex items-center gap-3 px-4 lg:px-6 bg-background/80 backdrop-blur-md border-b border-border", user?.impersonated ? "top-9" : "top-0")}>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
            <Menu className="h-5 w-5" />
          </Button>
          <BackButton />
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
            <PageHelp />
            <NotificationBell />
            {["manager_pnv", "manager_p_n_v", "manager_log", "manager_l_o_g"].includes(user?.role) && (
              <Button
                asChild
                size="sm"
                className="h-9 rounded-sm hidden md:inline-flex"
                data-testid="header-raise-payment-btn"
              >
                <NavLink to="/app/ops/requests?new=service">
                  <Wallet className="h-4 w-4 mr-1.5" /> Raise Payment Request
                </NavLink>
              </Button>
            )}
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-9 rounded-sm hidden md:inline-flex"
              data-testid="header-modules-btn"
            >
              <NavLink to="/app/modules">
                <LayoutGrid className="h-4 w-4 mr-1.5" /> Modules
              </NavLink>
            </Button>
            <MyApprovalsInbox />
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
                <DropdownMenuItem onClick={() => navigate("/app/me/email")} data-testid="menu-my-email">
                  <Mail className="h-4 w-4 mr-2" /> Email Settings (M365)
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onLogout} data-testid="menu-logout" className="text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-8">
          <RouteGuard>{children}</RouteGuard>
        </main>
        <AccessDeniedOverlay />
      </div>
    </div>
  );
}

/**
 * BackButton — sits in the global top bar.
 */
function BackButton() {
  const navigate = useNavigate();
  const location = useLocation();
  const hide = ["/app", "/app/", "/login"].includes(location.pathname);
  if (hide) return null;
  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/app");
    }
  };
  return (
    <Button
      variant="outline"
      size="sm"
      className="h-9 rounded-sm shrink-0"
      onClick={goBack}
      data-testid="global-back-btn"
      aria-label="Back"
    >
      <ChevronLeft className="h-4 w-4 md:mr-1" />
      <span className="hidden md:inline">Back</span>
    </Button>
  );
}
