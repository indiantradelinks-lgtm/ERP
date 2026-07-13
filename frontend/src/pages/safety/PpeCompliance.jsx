/**
 * PPE Compliance — pick project (± worker) and see what's required vs. what's
 * actually issued & valid.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ShieldCheck, RefreshCcw } from "lucide-react";

export default function PpeCompliance() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  const compute = async () => {
    if (!projectId) { toast.error("Pick a project"); return; }
    try {
      const q = new URLSearchParams({ project_id: projectId });
      if (workerId) q.set("worker_id", workerId);
      const r = await api.get(`/safety/ppe-compliance?${q}`);
      setResult(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Compute failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="ppe-compliance-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><ShieldCheck className="h-6 w-6 text-emerald-600" /> PPE Compliance</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Compares required PPE (from PPE Requirements) with what's actually issued & valid in Store.</p>
        </div>
      </div>

      <div className="border rounded-sm bg-card p-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[280px]">
          <Label className="text-[10px] uppercase tracking-wider">Project *</Label>
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="ppe-comp-project">
            <option value="">— select —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
        </div>
        <div className="min-w-[200px]">
          <Label className="text-[10px] uppercase tracking-wider">Worker ID (optional)</Label>
          <input value={workerId} onChange={(e) => setWorkerId(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" />
        </div>
        <Button onClick={compute} data-testid="ppe-comp-run"><RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Compute</Button>
      </div>

      {result && (
        <div className="border rounded-sm bg-card p-4 space-y-3" data-testid="ppe-comp-result">
          <div className="flex items-center gap-3 flex-wrap">
            <Chip label="Required" value={result.required_count} tone="slate" />
            <Chip label="Issued & Valid" value={result.issued_count} tone="emerald" />
            <Chip label="Missing" value={result.missing_count} tone={result.missing_count ? "red" : "slate"} />
            <div className={`ml-auto px-3 py-1 rounded-sm text-xs uppercase tracking-wider font-semibold ${result.compliant ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
              {result.compliant ? "Compliant" : "NON-Compliant"}
            </div>
          </div>
          {result.missing.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-red-700 mb-1.5">Missing PPE</div>
              <ul className="text-sm space-y-1">
                {result.missing.map((m) => <li key={m.id} className="border rounded-sm px-2 py-1 bg-red-50/50 text-red-900">{m.name}</li>)}
              </ul>
            </div>
          )}
          <div className="text-[10px] text-muted-foreground">As of {new Date(result.as_of).toLocaleString()}</div>
        </div>
      )}
    </div>
  );
}

function Chip({ label, value, tone }) {
  const t = tone === "red" ? "border-red-300 bg-red-50 text-red-700" : tone === "emerald" ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-slate-300 bg-slate-50 text-slate-700";
  return (
    <div className={`border rounded-sm px-3 py-1.5 ${t}`}>
      <div className="text-[9px] font-bold uppercase tracking-wider">{label}</div>
      <div className="font-display font-black text-lg tabular leading-none">{value}</div>
    </div>
  );
}
