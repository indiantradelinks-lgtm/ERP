/**
 * Project Planning · P&O Phase 2 (Round 1)
 *
 * One-page planning workbench per project. Captures the charter, kickoff
 * date, target milestones, risks, stakeholders, success criteria and
 * scope/exclusions/assumptions. Status: draft → approved (PM / Ops Head /
 * Director).
 *
 * Backend: /api/proj-phase2/planning/{project_id}
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ClipboardList, Plus, Trash2, RefreshCcw, CheckCircle2, AlertTriangle, Users, Target, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const EMPTY_MILESTONE   = { name: "", target_date: "", status: "pending", remarks: "" };
const EMPTY_RISK        = { description: "", severity: "medium", likelihood: "medium", mitigation: "", owner: "" };
const EMPTY_STAKEHOLDER = { name: "", role: "", organization: "", contact: "" };

const EMPTY_PLAN = {
  kickoff_date: "", charter_summary: "", objectives: "", scope_summary: "",
  exclusions: "", assumptions: "", constraints: "",
  target_start_date: "", target_completion_date: "",
  success_criteria: "", deliverables: "", notes: "",
  milestones: [], risks: [], stakeholders: [],
  planning_status: "draft",
};

export default function ProjectPlanning() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [plan, setPlan]           = useState(EMPTY_PLAN);
  const [busy, setBusy]           = useState(false);
  const { user } = useAuth() || {};
  const canApprove = ["super_admin", "director", "general_manager", "dept_head", "project_manager"].includes(user?.role);
  const canEdit    = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => {
    api.get("/projects").then(r => setProjects(r.data || [])).catch(() => {});
  }, []);

  const loadPlan = async (pid) => {
    if (!pid) { setPlan(EMPTY_PLAN); return; }
    try {
      const { data } = await api.get(`/proj-phase2/planning/${pid}`);
      setPlan({ ...EMPTY_PLAN, ...data });
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load planning");
    }
  };

  useEffect(() => { loadPlan(projectId); }, [projectId]);

  const save = async () => {
    if (!projectId) { toast.error("Select a project first"); return; }
    setBusy(true);
    try {
      const payload = {
        kickoff_date: plan.kickoff_date || "",
        charter_summary: plan.charter_summary || "",
        objectives: plan.objectives || "",
        scope_summary: plan.scope_summary || "",
        exclusions: plan.exclusions || "",
        assumptions: plan.assumptions || "",
        constraints: plan.constraints || "",
        target_start_date: plan.target_start_date || "",
        target_completion_date: plan.target_completion_date || "",
        success_criteria: plan.success_criteria || "",
        deliverables: plan.deliverables || "",
        notes: plan.notes || "",
        milestones: plan.milestones || [],
        risks: plan.risks || [],
        stakeholders: plan.stakeholders || [],
      };
      const { data } = await api.put(`/proj-phase2/planning/${projectId}`, payload);
      setPlan({ ...EMPTY_PLAN, ...data });
      toast.success("Planning saved");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally { setBusy(false); }
  };

  const approve = async () => {
    if (!projectId) return;
    if (!window.confirm("Approve this Project Planning? It will be locked for normal users.")) return;
    try {
      const { data } = await api.post(`/proj-phase2/planning/${projectId}/approve`);
      setPlan({ ...EMPTY_PLAN, ...data });
      toast.success("Planning approved");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Approval failed");
    }
  };

  const selectedProject = useMemo(() => projects.find(p => p.id === projectId), [projects, projectId]);
  const isApproved = plan.planning_status === "approved";
  const locked     = isApproved && !["super_admin", "director"].includes(user?.role);

  // ── inline list editors ─────────────────────────────────────────
  const updateRow = (key, idx, patch) => {
    setPlan(prev => {
      const arr = [...(prev[key] || [])];
      arr[idx] = { ...arr[idx], ...patch };
      return { ...prev, [key]: arr };
    });
  };
  const addRow = (key, blank) => setPlan(prev => ({ ...prev, [key]: [...(prev[key] || []), { ...blank }] }));
  const removeRow = (key, idx) => setPlan(prev => ({ ...prev, [key]: (prev[key] || []).filter((_, i) => i !== idx) }));

  return (
    <div className="p-6 space-y-4" data-testid="page-project-planning">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-primary" /> Project Planning
          </h1>
          <p className="text-sm text-muted-foreground">
            Project charter, milestones, risks &amp; stakeholders. Required before mobilization.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => loadPlan(projectId)} disabled={!projectId}>
            <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
          </Button>
          {canEdit && !locked && (
            <Button onClick={save} disabled={!projectId || busy} data-testid="plan-save">
              <Save className="h-4 w-4 mr-1" /> Save
            </Button>
          )}
          {canApprove && !isApproved && (
            <Button variant="default" className="bg-emerald-600 hover:bg-emerald-700" onClick={approve} disabled={!projectId} data-testid="plan-approve">
              <CheckCircle2 className="h-4 w-4 mr-1" /> Approve
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Project *</Label>
              <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1"
                       data-testid="plan-project-select">
                <option value="">— select project —</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Client</Label>
              <div className="mt-2 text-sm">{selectedProject?.client_name || selectedProject?.client || "—"}</div>
            </div>
            <div className="flex items-end">
              <span className={`text-[11px] uppercase tracking-wider px-2 py-1 rounded border ${isApproved ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-slate-50 text-slate-600 border-slate-200"}`}>
                Status: {plan.planning_status || "draft"}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {projectId && (
        <>
          {/* Charter & Objectives */}
          <Card>
            <CardHeader><CardTitle className="text-base flex items-center gap-2"><Target className="h-4 w-4 text-primary"/>Charter &amp; Objectives</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <F label="Kickoff Date"><Input type="date" value={plan.kickoff_date || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, kickoff_date: e.target.value })} data-testid="plan-kickoff" /></F>
              <F label="Target Start Date"><Input type="date" value={plan.target_start_date || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, target_start_date: e.target.value })} /></F>
              <F label="Target Completion Date"><Input type="date" value={plan.target_completion_date || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, target_completion_date: e.target.value })} /></F>
              <F label="Charter Summary" full><Textarea rows={3} value={plan.charter_summary || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, charter_summary: e.target.value })} placeholder="High-level intent, why this project exists" /></F>
              <F label="Objectives" full><Textarea rows={3} value={plan.objectives || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, objectives: e.target.value })} placeholder="Measurable objectives (SMART)" /></F>
              <F label="Success Criteria" full><Textarea rows={2} value={plan.success_criteria || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, success_criteria: e.target.value })} /></F>
              <F label="Key Deliverables" full><Textarea rows={2} value={plan.deliverables || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, deliverables: e.target.value })} /></F>
            </CardContent>
          </Card>

          {/* Scope / Exclusions / Assumptions */}
          <Card>
            <CardHeader><CardTitle className="text-base">Scope, Exclusions &amp; Assumptions</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <F label="Scope Summary" full><Textarea rows={3} value={plan.scope_summary || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, scope_summary: e.target.value })} /></F>
              <F label="Exclusions"><Textarea rows={3} value={plan.exclusions || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, exclusions: e.target.value })} /></F>
              <F label="Assumptions"><Textarea rows={3} value={plan.assumptions || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, assumptions: e.target.value })} /></F>
              <F label="Constraints" full><Textarea rows={2} value={plan.constraints || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, constraints: e.target.value })} /></F>
            </CardContent>
          </Card>

          {/* Milestones */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-base">Milestones <span className="text-xs text-slate-400">({(plan.milestones || []).length})</span></CardTitle>
              {!locked && <Button size="sm" variant="outline" onClick={() => addRow("milestones", EMPTY_MILESTONE)} data-testid="plan-add-milestone"><Plus className="h-3.5 w-3.5 mr-1"/>Add Milestone</Button>}
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2 w-1/3">Name</th>
                    <th className="px-2 py-2">Target Date</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Remarks</th>
                    <th className="px-2 py-2 text-right w-10"></th>
                  </tr></thead>
                  <tbody>
                    {(plan.milestones || []).length === 0 && <tr><td colSpan={5} className="text-center py-4 text-slate-400">No milestones yet</td></tr>}
                    {(plan.milestones || []).map((m, i) => (
                      <tr key={i} className="border-b">
                        <td className="px-2 py-1"><Input value={m.name || ""} disabled={locked} onChange={(e) => updateRow("milestones", i, { name: e.target.value })} /></td>
                        <td className="px-2 py-1"><Input type="date" value={m.target_date || ""} disabled={locked} onChange={(e) => updateRow("milestones", i, { target_date: e.target.value })} /></td>
                        <td className="px-2 py-1">
                          <select value={m.status || "pending"} disabled={locked} onChange={(e) => updateRow("milestones", i, { status: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                            <option value="pending">pending</option>
                            <option value="in_progress">in_progress</option>
                            <option value="completed">completed</option>
                            <option value="delayed">delayed</option>
                          </select>
                        </td>
                        <td className="px-2 py-1"><Input value={m.remarks || ""} disabled={locked} onChange={(e) => updateRow("milestones", i, { remarks: e.target.value })} /></td>
                        <td className="px-2 py-1 text-right">
                          {!locked && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeRow("milestones", i)} data-testid={`plan-del-milestone-${i}`}><Trash2 className="h-3.5 w-3.5"/></Button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Risks */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-600"/>Risks <span className="text-xs text-slate-400">({(plan.risks || []).length})</span></CardTitle>
              {!locked && <Button size="sm" variant="outline" onClick={() => addRow("risks", EMPTY_RISK)} data-testid="plan-add-risk"><Plus className="h-3.5 w-3.5 mr-1"/>Add Risk</Button>}
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2 w-1/3">Description</th>
                    <th className="px-2 py-2">Severity</th>
                    <th className="px-2 py-2">Likelihood</th>
                    <th className="px-2 py-2">Mitigation</th>
                    <th className="px-2 py-2">Owner</th>
                    <th className="px-2 py-2 text-right w-10"></th>
                  </tr></thead>
                  <tbody>
                    {(plan.risks || []).length === 0 && <tr><td colSpan={6} className="text-center py-4 text-slate-400">No risks identified</td></tr>}
                    {(plan.risks || []).map((r, i) => (
                      <tr key={i} className="border-b">
                        <td className="px-2 py-1"><Input value={r.description || ""} disabled={locked} onChange={(e) => updateRow("risks", i, { description: e.target.value })} /></td>
                        <td className="px-2 py-1">
                          <select value={r.severity || "medium"} disabled={locked} onChange={(e) => updateRow("risks", i, { severity: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                            <option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="critical">critical</option>
                          </select>
                        </td>
                        <td className="px-2 py-1">
                          <select value={r.likelihood || "medium"} disabled={locked} onChange={(e) => updateRow("risks", i, { likelihood: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                            <option value="low">low</option><option value="medium">medium</option><option value="high">high</option>
                          </select>
                        </td>
                        <td className="px-2 py-1"><Input value={r.mitigation || ""} disabled={locked} onChange={(e) => updateRow("risks", i, { mitigation: e.target.value })} /></td>
                        <td className="px-2 py-1"><Input value={r.owner || ""} disabled={locked} onChange={(e) => updateRow("risks", i, { owner: e.target.value })} /></td>
                        <td className="px-2 py-1 text-right">
                          {!locked && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeRow("risks", i)} data-testid={`plan-del-risk-${i}`}><Trash2 className="h-3.5 w-3.5"/></Button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Stakeholders */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4 text-primary"/>Stakeholders <span className="text-xs text-slate-400">({(plan.stakeholders || []).length})</span></CardTitle>
              {!locked && <Button size="sm" variant="outline" onClick={() => addRow("stakeholders", EMPTY_STAKEHOLDER)} data-testid="plan-add-stakeholder"><Plus className="h-3.5 w-3.5 mr-1"/>Add Stakeholder</Button>}
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">Name</th>
                    <th className="px-2 py-2">Role</th>
                    <th className="px-2 py-2">Organization</th>
                    <th className="px-2 py-2">Contact</th>
                    <th className="px-2 py-2 text-right w-10"></th>
                  </tr></thead>
                  <tbody>
                    {(plan.stakeholders || []).length === 0 && <tr><td colSpan={5} className="text-center py-4 text-slate-400">No stakeholders added</td></tr>}
                    {(plan.stakeholders || []).map((s, i) => (
                      <tr key={i} className="border-b">
                        <td className="px-2 py-1"><Input value={s.name || ""} disabled={locked} onChange={(e) => updateRow("stakeholders", i, { name: e.target.value })} /></td>
                        <td className="px-2 py-1"><Input value={s.role || ""} disabled={locked} onChange={(e) => updateRow("stakeholders", i, { role: e.target.value })} /></td>
                        <td className="px-2 py-1"><Input value={s.organization || ""} disabled={locked} onChange={(e) => updateRow("stakeholders", i, { organization: e.target.value })} /></td>
                        <td className="px-2 py-1"><Input value={s.contact || ""} disabled={locked} onChange={(e) => updateRow("stakeholders", i, { contact: e.target.value })} /></td>
                        <td className="px-2 py-1 text-right">
                          {!locked && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeRow("stakeholders", i)} data-testid={`plan-del-stakeholder-${i}`}><Trash2 className="h-3.5 w-3.5"/></Button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Notes</CardTitle></CardHeader>
            <CardContent>
              <Textarea rows={3} value={plan.notes || ""} disabled={locked} onChange={(e) => setPlan({ ...plan, notes: e.target.value })} placeholder="Other notes" />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
