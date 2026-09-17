/**
 * Safety Readiness — 11-factor aggregate per (project × worker) with a
 * ready/conditional/not_ready/blocked classification and inline override request.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ShieldPlus, RefreshCcw, Send } from "lucide-react";
import { fmtDT } from "@/lib/datetime";

const CLASS_TONE = {
  ready: "bg-emerald-100 text-emerald-900 border-emerald-400",
  conditional: "bg-amber-100 text-amber-900 border-amber-400",
  not_ready: "bg-orange-100 text-orange-900 border-orange-400",
  blocked: "bg-red-100 text-red-900 border-red-500",
};
const STATE_ICON = { green: "🟢", yellow: "🟡", red: "🔴" };

export default function SafetyReadiness() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [data, setData] = useState(null);
  const [overrideFor, setOverrideFor] = useState(null);
  const [overrideForm, setOverrideForm] = useState({ reason: "", valid_until: "" });

  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  const compute = async () => {
    if (!projectId) { toast.error("Pick a project"); return; }
    try {
      const q = new URLSearchParams({ project_id: projectId });
      if (workerId) q.set("worker_id", workerId);
      const r = await api.get(`/safety/readiness?${q}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Compute failed"); }
  };

  const requestOverride = async () => {
    if (overrideForm.reason.length < 10) { toast.error("Reason must be at least 10 chars"); return; }
    try {
      await api.post("/safety/overrides", {
        project_id: projectId, worker_id: workerId || null,
        blocked_factor: overrideFor.key,
        reason: overrideForm.reason,
        valid_until: overrideForm.valid_until || null,
      });
      toast.success("Override requested — Safety Head to approve"); setOverrideFor(null);
    } catch (e) { toast.error(e.response?.data?.detail || "Override failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="safety-readiness-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><ShieldPlus className="h-6 w-6 text-blue-600" /> Safety Readiness</h1>
          <p className="text-xs text-muted-foreground mt-0.5">11-factor readiness check per project / worker. Request an override for blocked factors.</p>
        </div>
      </div>

      <div className="border rounded-sm bg-card p-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[280px]">
          <Label className="text-[10px] uppercase tracking-wider">Project *</Label>
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="readiness-project">
            <option value="">— select —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
        </div>
        <div className="min-w-[200px]"><Label className="text-[10px] uppercase tracking-wider">Worker ID (optional)</Label><Input value={workerId} onChange={(e) => setWorkerId(e.target.value)} /></div>
        <Button onClick={compute} data-testid="readiness-run"><RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Compute</Button>
      </div>

      {data && (
        <div data-testid="readiness-result" className="space-y-3">
          <div className={`border-2 rounded-sm p-4 flex items-center justify-between ${CLASS_TONE[data.classification] || "bg-slate-100"}`}>
            <div>
              <div className="text-[10px] uppercase tracking-wider">Overall Classification</div>
              <div className="font-display font-black text-3xl uppercase tracking-tight">{data.classification.replaceAll("_", " ")}</div>
              <div className="text-[10px] mt-0.5">{data.factors.length} factors evaluated · {fmtDT(data.as_of)}</div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.factors.map((f) => (
              <div key={f.key} className="border rounded-sm bg-card p-3" data-testid={`readiness-factor-${f.key}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">{f.label}</div>
                    <div className="text-lg mt-0.5">{STATE_ICON[f.state]} <span className="text-xs uppercase tracking-wider ml-1">{f.state}</span>{f.blocking && <span className="ml-2 text-[9px] text-red-600 uppercase font-bold">blocking</span>}</div>
                    {f.detail && <div className="text-xs text-muted-foreground mt-1">{f.detail}</div>}
                  </div>
                  {f.state === "red" && f.blocking && (
                    <Button size="sm" variant="outline" onClick={() => { setOverrideFor(f); setOverrideForm({ reason: "", valid_until: "" }); }} data-testid={`readiness-override-${f.key}`}>
                      <Send className="h-3.5 w-3.5 mr-1" /> Override
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Dialog open={overrideFor !== null} onOpenChange={(o) => !o && setOverrideFor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Request Override — {overrideFor?.label}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">A Safety Head must approve this override. It creates an approval doc and an audit-log entry.</p>
            <div><Label className="text-[10px] uppercase tracking-wider">Reason (min 10 chars) *</Label><Textarea rows={4} value={overrideForm.reason} onChange={(e) => setOverrideForm({ ...overrideForm, reason: e.target.value })} data-testid="override-reason" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Valid Until</Label><Input type="date" value={overrideForm.valid_until} onChange={(e) => setOverrideForm({ ...overrideForm, valid_until: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideFor(null)}>Cancel</Button>
            <Button onClick={requestOverride} data-testid="override-submit">Request Override</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
