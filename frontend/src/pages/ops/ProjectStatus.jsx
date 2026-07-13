/**
 * Project Status · kanban-style board grouped by status (planned/active/on_hold/completed/cancelled).
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Activity, RefreshCcw } from "lucide-react";

const STATUSES = ["planned", "active", "on_hold", "completed", "cancelled"];
const TONES = {
  planned: "bg-amber-50 border-amber-200 text-amber-900",
  active: "bg-emerald-50 border-emerald-200 text-emerald-900",
  on_hold: "bg-orange-50 border-orange-200 text-orange-900",
  completed: "bg-blue-50 border-blue-200 text-blue-900",
  cancelled: "bg-rose-50 border-rose-200 text-rose-900",
};

export default function ProjectStatus() {
  const [projects, setProjects] = useState([]);
  const load = async () => { const r = await api.get("/projects").catch(() => ({ data: [] })); setProjects(r.data); };
  useEffect(() => { load(); }, []);

  const byStatus = useMemo(() => {
    const m = Object.fromEntries(STATUSES.map((s) => [s, []]));
    projects.forEach((p) => { (m[p.status] || m.planned).push(p); });
    return m;
  }, [projects]);

  const totalValue = projects.reduce((s, p) => s + (Number(p.contract_value || p.budget) || 0), 0);

  return (
    <div className="p-6 space-y-4" data-testid="page-project-status">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="h-6 w-6 text-primary" /> Project Status</h1>
          <p className="text-sm text-muted-foreground">Quick status board — every project bucketed by lifecycle stage.</p>
        </div>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {STATUSES.map((s) => (
          <div key={s} className={`border rounded-sm p-3 ${TONES[s]}`}>
            <div className="text-[10px] uppercase tracking-wider">{s.replace("_", " ")}</div>
            <div className="text-2xl font-bold">{byStatus[s].length}</div>
          </div>
        ))}
      </div>
      <div className="text-sm text-muted-foreground">
        Total portfolio value: <strong>₹ {totalValue.toLocaleString("en-IN")}</strong> · across {projects.length} projects.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
        {STATUSES.map((s) => (
          <Card key={s} className={TONES[s]}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm uppercase tracking-wider">{s.replace("_", " ")} <span className="text-xs">({byStatus[s].length})</span></CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[60vh] overflow-y-auto">
              {byStatus[s].length === 0 && <div className="text-xs text-muted-foreground italic">— empty —</div>}
              {byStatus[s].map((p) => (
                <div key={p.id} className="border rounded-sm p-2 bg-white/80" data-testid={`ps-card-${p.id}`}>
                  <div className="font-mono text-[10px] text-primary">{p.code}</div>
                  <div className="font-medium text-sm">{p.name}</div>
                  <div className="text-xs text-muted-foreground">{p.client} · {p.site}</div>
                  <div className="flex items-center justify-between mt-1 text-[11px]">
                    <span>{p.manager || "no PM"}</span>
                    <span className="font-mono">₹ {Number(p.contract_value || p.budget || 0).toLocaleString("en-IN")}</span>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
