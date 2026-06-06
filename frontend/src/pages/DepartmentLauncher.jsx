import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck, LayoutGrid } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import MyAdvancesWidget from "@/components/MyAdvancesWidget";

const ICONS = { Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck };

const TONE_RING = {
  primary: "border-primary/30 hover:border-primary/70 hover:bg-primary/5",
  info: "border-chart-3/30 hover:border-chart-3/70 hover:bg-chart-3/5",
  success: "border-success/30 hover:border-success/70 hover:bg-success/5",
  warning: "border-warning/30 hover:border-warning/70 hover:bg-warning/5",
  danger: "border-destructive/30 hover:border-destructive/70 hover:bg-destructive/5",
  neutral: "border-border hover:border-foreground/40 hover:bg-muted/30",
};

const TONE_FG = {
  primary: "text-primary",
  info: "text-chart-3",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  neutral: "text-foreground",
};

export default function DepartmentLauncher() {
  const navigate = useNavigate();
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/departments")
      .then((r) => setDepartments(r.data.departments || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8" data-testid="department-launcher">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <LayoutGrid className="h-3 w-3" /> Departments
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Choose Your Workspace</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-xl">Every department operates as its own self-contained module — dedicated dashboard, menus, approvals and reports — while sharing the central ERP backbone.</p>
        </div>
        <div className="w-full md:w-80 shrink-0">
          <MyAdvancesWidget />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 stagger" data-testid="department-grid">
        {loading && Array.from({ length: 9 }).map((_, i) => (
          <div key={`s-${i}`} className="bg-card border border-border rounded-sm p-6 h-44 animate-pulse" />
        ))}
        {!loading && departments.map((d) => {
          const Icon = ICONS[d.icon] || LayoutGrid;
          return (
            <button
              key={d.slug}
              type="button"
              onClick={() => navigate(`/app/modules/${d.slug}`)}
              data-testid={`dept-tile-${d.slug}`}
              className={cn(
                "kpi-tile text-left bg-card border rounded-sm p-6 transition-colors group",
                TONE_RING[d.color] || TONE_RING.neutral,
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className={cn("h-12 w-12 grid place-items-center rounded-sm bg-muted/60", TONE_FG[d.color] || TONE_FG.neutral)}>
                  <Icon className="h-6 w-6" />
                </div>
                <div className="text-right">
                  <div className={cn("font-display font-black text-3xl tabular leading-none", TONE_FG[d.color] || TONE_FG.neutral)}>{d.headline}</div>
                  <div className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground mt-1">Live</div>
                </div>
              </div>
              <div className="mt-4">
                <div className="font-display font-bold text-lg leading-tight">{d.title}</div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{d.tagline}</p>
              </div>
              <div className={cn("mt-4 text-[10px] font-bold uppercase tracking-[0.18em]", TONE_FG[d.color] || TONE_FG.neutral)}>
                Open workspace →
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
