/**
 * Project Dashboard · 20 real-time KPI cards with drill-down.
 *
 * Data: /api/proj-masters/dashboard-kpis
 * Drill-down: clicking any card opens a side panel listing matched projects;
 * each project row links to the Project Master detail.
 */
import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Activity, Calendar, CheckCircle2, Clock, AlertTriangle,
  Zap, UserX, MapPinOff, ShieldAlert, Users, Package, ClipboardCheck,
  IndianRupee, FolderClosed, Hourglass, FileText, TrendingUp, BarChart3, RefreshCcw,
} from "lucide-react";

const CARDS = [
  { key: "total_projects",                       title: "Total Projects",                tone: "blue",    Icon: LayoutDashboard },
  { key: "active_projects",                       title: "Active",                        tone: "emerald", Icon: Activity },
  { key: "planned_projects",                      title: "Planned",                       tone: "amber",   Icon: Calendar },
  { key: "mobilization_pending_projects",         title: "Mobilization Pending",          tone: "amber",   Icon: Clock },
  { key: "projects_on_hold",                      title: "On Hold",                       tone: "orange",  Icon: Hourglass },
  { key: "completed_projects",                    title: "Completed",                     tone: "blue",    Icon: CheckCircle2 },
  { key: "closure_pending_projects",              title: "Closure Pending",               tone: "violet",  Icon: FolderClosed },
  { key: "delayed_projects",                      title: "Delayed",                       tone: "rose",    Icon: AlertTriangle },
  { key: "shutdown_projects",                     title: "Shutdown",                      tone: "rose",    Icon: Zap },
  { key: "projects_without_pm",                   title: "Without PM",                    tone: "amber",   Icon: UserX },
  { key: "projects_without_site_incharge",        title: "Without Site Incharge",         tone: "amber",   Icon: MapPinOff },
  { key: "projects_pending_approval",             title: "Pending Approval",              tone: "violet",  Icon: ClipboardCheck },
  { key: "projects_requiring_manpower",           title: "Need Manpower",                 tone: "blue",    Icon: Users },
  { key: "projects_requiring_material",           title: "Need Material",                 tone: "blue",    Icon: Package },
  { key: "projects_requiring_safety_clearance",   title: "Need Safety Clearance",         tone: "amber",   Icon: ShieldAlert },
  { key: "projects_pending_billing",              title: "Pending Client Billing",        tone: "violet",  Icon: IndianRupee },
  { key: "projects_with_pending_closure",         title: "Closure To-Do",                 tone: "violet",  Icon: FolderClosed },
  { key: "recent_projects",                       title: "Recent Projects",               tone: "blue",    Icon: Clock },
  { key: "high_value_projects",                   title: "High-Value (> ₹10 L)",          tone: "emerald", Icon: TrendingUp },
];

const TONE = {
  blue:    "border-blue-200 bg-blue-50 text-blue-900",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
  amber:   "border-amber-200 bg-amber-50 text-amber-900",
  orange:  "border-orange-200 bg-orange-50 text-orange-900",
  violet:  "border-violet-200 bg-violet-50 text-violet-900",
  rose:    "border-rose-200 bg-rose-50 text-rose-900",
};

export default function ProjectDashboard() {
  const [kpis, setKpis] = useState(null);
  const [drill, setDrill] = useState(null);  // {key, title, items}
  const [projects, setProjects] = useState([]);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/proj-masters/dashboard-kpis"),
        api.get("/projects"),
      ]);
      setKpis(a.data);
      setProjects(b.data);
    } catch (e) { /* swallow */ }
  };
  useEffect(() => { load(); }, []);

  const byId = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);

  const openDrill = (card) => {
    if (!kpis) return;
    const k = kpis[card.key];
    let items = [];
    if (k?.items) items = k.items.map((it) => ({ ...it, ...(byId[it.id] || {}) }));
    else if (k?.ids) items = k.ids.map((id) => byId[id]).filter(Boolean);
    setDrill({ key: card.key, title: card.title, items });
  };

  if (!kpis) return <div className="p-6 text-muted-foreground">Loading dashboard…</div>;

  return (
    <div className="p-6 space-y-4" data-testid="page-project-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-primary" /> Project Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">Real-time portfolio snapshot · click any card to drill down</p>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="pdb-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {CARDS.map((c) => {
          const v = kpis[c.key] || {};
          const n = v.count ?? (v.items?.length || v.ids?.length || 0);
          const Icon = c.Icon;
          return (
            <button key={c.key}
                     onClick={() => openDrill(c)}
                     className={`text-left border rounded-sm p-3 ${TONE[c.tone]} hover:shadow-md transition focus:outline-none focus:ring-2 focus:ring-primary/40`}
                     data-testid={`pdb-card-${c.key}`}>
              <div className="flex items-start justify-between">
                <div className="text-[10px] uppercase tracking-wider opacity-80">{c.title}</div>
                <Icon className="h-4 w-4 opacity-60" />
              </div>
              <div className="text-3xl font-bold mt-1">{n}</div>
            </button>
          );
        })}
      </div>

      {/* Status summary as a strip */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Status Summary</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(kpis.status_summary || {}).map(([s, n]) => (
              <span key={s} className="px-2 py-1 rounded-sm border bg-card font-mono" data-testid={`pdb-ss-${s}`}>
                {s.replace(/_/g, " ")} · <b>{n}</b>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Drill-down panel */}
      <Sheet open={drill !== null} onOpenChange={(o) => !o && setDrill(null)}>
        <SheetContent className="w-[640px] sm:max-w-[640px] overflow-y-auto" data-testid="pdb-drill-panel">
          <SheetHeader><SheetTitle>{drill?.title} <span className="text-sm text-muted-foreground">({drill?.items.length || 0})</span></SheetTitle></SheetHeader>
          <div className="mt-4 space-y-2">
            {(drill?.items || []).length === 0 && <div className="text-muted-foreground text-sm">No matching projects.</div>}
            {(drill?.items || []).map((p) => (
              <button key={p.id}
                       onClick={() => { setDrill(null); navigate(`/app/projects?focus=${p.id}`); }}
                       className="w-full text-left border rounded-sm p-2 hover:bg-accent" data-testid={`pdb-drill-item-${p.id}`}>
                <div className="flex justify-between text-xs">
                  <span className="font-mono text-primary">{p.code}</span>
                  <span className="uppercase tracking-wider text-[10px]">{p.status}</span>
                </div>
                <div className="font-medium text-sm">{p.name}</div>
                <div className="text-xs text-muted-foreground flex justify-between">
                  <span>{p.client || "—"} · {p.site || "—"}</span>
                  {p.contract_value && <span className="font-mono">₹ {Number(p.contract_value).toLocaleString("en-IN")}</span>}
                </div>
              </button>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
