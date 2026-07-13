/**
 * ModuleMenu — reusable side-rail menu rendered inside any module landing
 * page. Reads from the SAME central menuConfig so sidebar and module menu
 * never drift out of sync.
 *
 * Usage:
 *    import ModuleMenu from "@/components/ModuleMenu";
 *    <ModuleMenu department="sales" />
 */
import { NavLink, useLocation } from "react-router-dom";
import { useState } from "react";
import { Search, ChevronDown, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { DEPARTMENT_MAP, itemsByDepartment, isItemVisible } from "@/config/menuConfig";

export default function ModuleMenu({ department, title, dense = false }) {
  const { user, can } = useAuth();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const dept = DEPARTMENT_MAP[department];
  if (!dept) return null;

  const allGroups = itemsByDepartment(department);
  const q = query.trim().toLowerCase();

  const filteredGroups = {};
  for (const [groupKey, items] of Object.entries(allGroups)) {
    const filtered = items.filter((it) => {
      if (!isItemVisible(it, { role: user?.role, can })) return false;
      if (!q) return true;
      return it.label.toLowerCase().includes(q);
    });
    if (filtered.length > 0) filteredGroups[groupKey] = filtered;
  }

  const totalVisible = Object.values(filteredGroups).flat().length;

  return (
    <Card className="rounded-sm" data-testid={`module-menu-${department}`}>
      <CardContent className={cn("p-3", dense && "p-2")}>
        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-border">
          <dept.icon className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold flex-1">{title || dept.label}</h3>
          <span className="text-[10px] text-muted-foreground">{totalVisible}</span>
        </div>
        <div className="relative mb-3">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={`Search ${dept.label}…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-7 h-8 text-xs rounded-sm"
            data-testid={`module-menu-search-${department}`}
          />
        </div>
        <div className="flex flex-col gap-0.5 max-h-[60vh] overflow-y-auto">
          {(filteredGroups._root || []).map((it) => renderItem(it, location))}
          {Object.entries(filteredGroups)
            .filter(([k]) => k !== "_root")
            .map(([sub, items]) => (
              <SubGroup key={sub} label={sub} items={items} location={location} />
            ))}
          {totalVisible === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">No items match</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function SubGroup({ label, items, location }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground hover:text-primary"
        data-testid={`module-sub-${label}`}
      >
        <span>{label}</span>
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>
      {open && (
        <div className="flex flex-col gap-0.5 pl-2">
          {items.map((it) => renderItem(it, location))}
        </div>
      )}
    </div>
  );
}

function renderItem(it, location) {
  if (it.comingSoon) {
    return (
      <div
        key={it.testid}
        title="Coming soon"
        data-testid={`module-menu-item-${it.testid}`}
        className="flex items-center gap-2 px-2 py-1.5 text-xs rounded-sm text-muted-foreground/60 cursor-not-allowed"
      >
        <it.icon className="h-3.5 w-3.5 shrink-0 opacity-60" />
        <span className="truncate flex-1">{it.label}</span>
        <span className="text-[9px] px-1 py-0.5 bg-muted text-muted-foreground rounded-sm">Soon</span>
      </div>
    );
  }
  return (
    <NavLink
      key={it.testid}
      to={it.to}
      data-testid={`module-menu-item-${it.testid}`}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 px-2 py-1.5 text-xs rounded-sm transition-colors",
          "hover:bg-primary/10 hover:text-primary",
          isActive || location.pathname === it.to
            ? "bg-primary/10 text-primary font-medium"
            : "text-foreground/80",
        )
      }
    >
      <it.icon className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{it.label}</span>
    </NavLink>
  );
}
