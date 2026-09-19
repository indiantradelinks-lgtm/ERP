/**
 * Project Safety Closure (Phase 5) — 15-point live checklist per project
 * with Safety Head / PM approval and override capability.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ClipboardList, CheckCircle2, XCircle, ShieldAlert, RefreshCcw, Lock } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

export default function ProjectSafetyClosure() {
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [snap, setSnap] = useState(null);
  const [reportUrl, setReportUrl] = useState("");
  const [remarks, setRemarks] = useState("");
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");

  const loadProjects = async () => {
    try { const r = await lookupGet("/projects"); setProjects(r.data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load projects"); }
  };
  useEffect(() => { loadProjects(); }, []);

  const loadSnap = async (pid) => {
    if (!pid) return setSnap(null);
    try {
      const r = await api.post(`/safety/closure/${pid}/check`);
      setSnap(r.data);
      setReportUrl(r.data.final_report_url || "");
      setRemarks(r.data.remarks || "");
    } catch (e) { toast.error(e.response?.data?.detail || "Check failed"); }
  };
  useEffect(() => { if (selectedId) loadSnap(selectedId); }, [selectedId]);

  const save = async (approveAs) => {
    try {
      const r = await api.post(`/safety/closure/${selectedId}/submit`, {
        final_report_url: reportUrl || null,
        remarks: remarks || null,
        approve_as: approveAs || null,
      });
      setSnap(r.data);
      toast.success(approveAs ? `Stamped ${approveAs.replace("_", " ")}` : "Saved");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const submitOverride = async () => {
    if (overrideReason.length < 10) return toast.error("Reason must be at least 10 characters");
    try {
      await api.post(`/safety/closure/${selectedId}/override`, { reason: overrideReason });
      toast.success("Override recorded");
      setOverrideOpen(false); setOverrideReason("");
      loadSnap(selectedId);
    } catch (e) { toast.error(e.response?.data?.detail || "Override failed"); }
  };

  return (
    <div className="p-6 space-y-5" data-testid="project-closure-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 5</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <ClipboardList className="h-6 w-6 text-red-600" /> Project Safety Closure
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          15-point live checklist. All items must pass (or be overridden by Safety Head / Owner) before Projects & Operations can close the project.
        </p>
      </div>

      <div className="flex gap-3 items-end">
        <div className="flex-1 max-w-lg">
          <Label>Project</Label>
          <select className="w-full border rounded h-10 px-2 text-sm" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} data-testid="closure-project-select">
            <option value="">— Select a project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name} · {p.status}</option>)}
          </select>
        </div>
        <Button variant="outline" onClick={() => loadSnap(selectedId)} disabled={!selectedId} data-testid="closure-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      {snap && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 border rounded-sm p-3 bg-card">
            <div className="text-xs uppercase text-slate-500 font-bold tracking-wider">Progress</div>
            <div className="text-2xl font-black">
              <span className={snap.passed === snap.total ? "text-emerald-700" : "text-amber-700"}>{snap.passed}</span>
              <span className="text-slate-400"> / {snap.total}</span>
            </div>
            <div className="h-2 bg-slate-200 rounded flex-1 overflow-hidden max-w-md">
              <div
                className={`h-full ${snap.passed === snap.total ? "bg-emerald-500" : "bg-amber-500"}`}
                style={{ width: `${(snap.passed / snap.total) * 100}%` }}
              />
            </div>
            <span className={`text-[10px] uppercase font-bold px-2 py-1 rounded ${snap.can_close ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`} data-testid="closure-status">
              {snap.can_close ? "Ready to close" : "Blocked"}
            </span>
            {snap.override && (
              <span className="text-[10px] uppercase font-bold px-2 py-1 rounded bg-orange-100 text-orange-800" title={snap.override.reason}>
                Override by {snap.override.by}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {snap.checklist.map((c) => (
              <div key={c.key} className={`flex items-start gap-2 border rounded p-2 ${c.passed ? "bg-emerald-50/40 border-emerald-200" : "bg-red-50/40 border-red-200"}`} data-testid={`chk-${c.key}`}>
                {c.passed ? <CheckCircle2 className="h-4 w-4 text-emerald-600 mt-0.5" /> : <XCircle className="h-4 w-4 text-red-600 mt-0.5" />}
                <div className="text-sm">
                  <div className="font-medium">{c.label}</div>
                  <div className="text-[11px] text-slate-500 font-mono">{c.key}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="border rounded-sm p-4 bg-card space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-600">Final Safety Report & Approvals</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Final Safety Report URL / Reference</Label>
                <Input value={reportUrl} onChange={(e) => setReportUrl(e.target.value)} placeholder="Paste OneDrive link or ref" data-testid="closure-report-url" />
              </div>
              <div>
                <Label>Remarks</Label>
                <Textarea rows={1} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => save()} data-testid="closure-save">Save Draft</Button>
              <Button onClick={() => save("safety_head")} data-testid="closure-approve-safety">
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve as Safety Head
              </Button>
              <Button onClick={() => save("project_manager")} data-testid="closure-approve-pm">
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve as Project Manager
              </Button>
              <Button variant="destructive" onClick={() => setOverrideOpen(true)} data-testid="closure-override-btn">
                <ShieldAlert className="h-3.5 w-3.5 mr-1" /> Override (Safety Head / Owner)
              </Button>
              {snap.closure_status === "closed" && (
                <span className="ml-auto inline-flex items-center gap-1 text-emerald-700 text-sm">
                  <Lock className="h-4 w-4" /> Safety Closure Completed
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Safety Closure Override</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">
            This unblocks project closure despite pending safety items. Requires Safety Head or Owner role. A permanent audit-trail entry will be recorded.
          </p>
          <Label>Reason (min. 10 chars)</Label>
          <Textarea rows={4} value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} data-testid="override-reason" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={submitOverride} data-testid="override-submit">Confirm Override</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
