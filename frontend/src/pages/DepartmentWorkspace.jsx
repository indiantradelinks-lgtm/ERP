import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, LayoutGrid, Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const ICONS = { Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck };

const TONE_TEXT = {
  primary: "text-primary",
  info: "text-chart-3",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  neutral: "text-foreground",
};

function formatValue(v, hint) {
  if (v === null || v === undefined) return "—";
  if (hint === "currency") return "₹ " + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  if (hint === "percent") return `${Number(v).toLocaleString("en-IN")}%`;
  return Number(v).toLocaleString("en-IN");
}

export default function DepartmentWorkspace() {
  const { dept } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.get(`/dashboard/department/${dept}`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load department"));
  }, [dept]);

  if (error) {
    return (
      <div className="text-center py-16" data-testid="department-error">
        <div className="font-display font-bold text-lg">{error}</div>
        <Button className="mt-4 rounded-sm" onClick={() => navigate("/app/modules")}>← Back to Modules</Button>
      </div>
    );
  }
  if (!data) return <div className="text-sm text-muted-foreground">Loading workspace…</div>;

  const Icon = ICONS[data.icon] || LayoutGrid;
  return (
    <div className="space-y-8" data-testid={`dept-workspace-${dept}`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <div className={cn("h-12 w-12 grid place-items-center rounded-sm bg-muted/60", TONE_TEXT[data.color])}>
            <Icon className="h-6 w-6" />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-1.5">Department Workspace</div>
            <h1 className="font-display font-black text-3xl tracking-tight">{data.title}</h1>
            <p className="text-sm text-muted-foreground mt-1">{data.tagline}</p>
          </div>
        </div>
        <Button variant="outline" className="rounded-sm" onClick={() => navigate("/app/modules")} data-testid="dept-back">
          <ArrowLeft className="h-4 w-4 mr-1.5" /> All Modules
        </Button>
      </div>

      {/* KPI strip */}
      <section data-testid="dept-kpis">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">Key Indicators</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3 stagger">
          {data.kpis.map((k) => (
            <button
              key={k.label}
              type="button"
              disabled={!k.deeplink}
              onClick={() => k.deeplink && navigate(k.deeplink)}
              className={cn(
                "kpi-tile text-left bg-card border border-border rounded-sm p-3 transition-colors",
                k.deeplink ? "hover:border-primary/60 hover:bg-muted/30 cursor-pointer" : "cursor-default",
              )}
              data-testid={`dept-kpi-${k.label.replaceAll(' ', '-').toLowerCase()}`}
            >
              <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground leading-tight">{k.label}</div>
              <div className={cn("font-display font-black text-2xl tabular leading-none mt-1.5", TONE_TEXT[k.tone] || TONE_TEXT.neutral)}>
                {formatValue(k.value, k.format)}
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Quick links */}
      <section data-testid="dept-links">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">Modules in this Department</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 stagger">
          {data.links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="bg-card border border-border rounded-sm p-4 hover:border-primary/60 hover:bg-muted/30 transition-colors group"
              data-testid={`dept-link-${l.to.replaceAll('/', '-')}`}
            >
              <div className="flex items-center justify-between">
                <div className="font-display font-bold text-sm">{l.label}</div>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{l.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
