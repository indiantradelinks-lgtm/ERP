import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, HeartPulse, ShieldPlus, UserMinus, RotateCcw, FileSpreadsheet, FileText, Pencil, Trash2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect } from "@/components/MasterSelect";

const WRITE_ROLES = new Set(["super_admin", "hr_executive", "general_manager", "director"]);
const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const blankPolicy = () => ({ policy_number: "", insurer: "", tpa: "", policy_start: "", policy_end: "", sum_insured_default: 0, premium_total: 0, notes: "", status: "active" });

export default function GroupMedical() {
  const { user } = useAuth();
  const canWrite = user && WRITE_ROLES.has(user.role);
  const [policies, setPolicies] = useState([]);
  const [policyId, setPolicyId] = useState("");
  const [members, setMembers] = useState([]);
  const [summary, setSummary] = useState(null);
  const [designations, setDesignations] = useState([]);
  const [filters, setFilters] = useState({ scope: "", project_code: "", designation: "", status: "active", q: "" });
  const [policyDlg, setPolicyDlg] = useState(null);
  const [addDlg, setAddDlg] = useState(false);
  const [removeFor, setRemoveFor] = useState(null);
  const [removeReason, setRemoveReason] = useState("");

  const loadPolicies = async () => {
    try {
      const r = await api.get("/gmc/policies");
      setPolicies(r.data || []);
      if (!policyId && r.data?.length) setPolicyId(r.data[0].id);
    } catch { toast.error("Failed to load policies"); }
  };
  const loadMembers = async () => {
    try {
      const params = { policy_id: policyId || undefined };
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const [m, s] = await Promise.all([
        api.get("/gmc/members", { params }),
        api.get("/gmc/summary", { params: { policy_id: policyId || undefined } }),
      ]);
      setMembers(m.data || []); setSummary(s.data);
    } catch { toast.error("Failed to load members"); }
  };
  useEffect(() => { loadPolicies(); api.get("/hr/designations").then((r) => setDesignations(r.data || [])).catch(() => {}); }, []); // eslint-disable-line
  useEffect(() => { loadMembers(); }, [policyId, filters]); // eslint-disable-line

  const savePolicy = async () => {
    const p = policyDlg;
    if (!p.policy_number || !p.insurer) { toast.error("Policy number & insurer are required"); return; }
    try {
      if (p.id) await api.put(`/gmc/policies/${p.id}`, p);
      else {
        const r = await api.post("/gmc/policies", p);
        setPolicyId(r.data.id);
      }
      toast.success("Policy saved"); setPolicyDlg(null); loadPolicies();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
  };

  const deletePolicy = async (pid) => {
    if (!window.confirm("Delete this policy and all its member records?")) return;
    try { await api.delete(`/gmc/policies/${pid}`); toast.success("Policy deleted"); setPolicyId(""); loadPolicies(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  const removeMember = async () => {
    try {
      await api.post(`/gmc/members/${removeFor.id}/remove`, { reason: removeReason });
      toast.success(`${removeFor.name} removed from policy`);
      setRemoveFor(null); setRemoveReason(""); loadMembers(); loadPolicies();
    } catch (e) { toast.error(e?.response?.data?.detail || "Remove failed"); }
  };

  const restoreMember = async (m) => {
    try { await api.post(`/gmc/members/${m.id}/restore`); toast.success(`${m.name} restored`); loadMembers(); loadPolicies(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Restore failed"); }
  };

  const download = async (fmt) => {
    try {
      const params = { policy_id: policyId || undefined };
      Object.entries(filters).forEach(([k, v]) => { if (v && k !== "q") params[k] = v; });
      const { data, headers } = await api.get(`/gmc/export.${fmt}`, { responseType: "blob", params });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = (headers["content-disposition"] || "").split('filename="')[1]?.replace('"', "") || `group_medical.${fmt}`;
      a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const policy = policies.find((p) => p.id === policyId);

  return (
    <div className="space-y-5" data-testid="gmc-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <HeartPulse className="h-3 w-3" /> Employee Welfare
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Group Medical Policy</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Manage GMC policies & member enrolment — project-wise, designation-wise or head office.
            Members are pulled from the Employee Master; exited employees (FNF finalised) are removed automatically.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => { loadPolicies(); loadMembers(); }} data-testid="gmc-reload"><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="gmc-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="gmc-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> PDF</Button>
          {canWrite && (
            <Button className="h-9 rounded-sm" onClick={() => setPolicyDlg(blankPolicy())} data-testid="gmc-new-policy">
              <Plus className="h-4 w-4 mr-1.5" /> New Policy
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {policies.map((p) => (
          <button key={p.id} onClick={() => setPolicyId(p.id)}
            className={`bg-card border rounded-sm p-3 text-left transition-colors hover:border-primary/50 ${policyId === p.id ? "border-primary" : "border-border"}`}
            data-testid={`gmc-policy-${p.id}`}>
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{p.insurer}{p.tpa ? ` · TPA: ${p.tpa}` : ""}</div>
              <Badge variant="outline" className={`rounded-sm text-[10px] uppercase ${p.status === "active" ? "border-emerald-300 text-emerald-800 bg-emerald-50" : ""}`}>{p.status}</Badge>
            </div>
            <div className="font-mono-data font-bold text-sm mt-1">{p.policy_number}</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {p.policy_start || "—"} → {p.policy_end || "—"} · <b>{p.active_members}</b> covered · SI default {inr(p.sum_insured_default)}
            </div>
            {canWrite && policyId === p.id && (
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="outline" className="h-6 rounded-sm text-[11px]" onClick={(e) => { e.stopPropagation(); setPolicyDlg({ ...p }); }} data-testid="gmc-edit-policy"><Pencil className="h-3 w-3 mr-1" /> Edit</Button>
                <Button size="sm" variant="outline" className="h-6 rounded-sm text-[11px] text-destructive" onClick={(e) => { e.stopPropagation(); deletePolicy(p.id); }}><Trash2 className="h-3 w-3 mr-1" /> Delete</Button>
              </div>
            )}
          </button>
        ))}
        {policies.length === 0 && (
          <div className="col-span-3 bg-card border border-dashed border-border rounded-sm p-6 text-center text-sm text-muted-foreground">
            No GMC policy yet. {canWrite ? "Create one with New Policy." : ""}
          </div>
        )}
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[["Covered Employees", summary.active], ["Project-wise", summary.project], ["Head Office", summary.head_office],
            ["Dependents", summary.dependents], ["Total Sum Insured", inr(summary.sum_insured_total)], ["Removed / Exited", summary.removed]].map(([label, v]) => (
            <div key={label} className="bg-card border border-border rounded-sm p-3" data-testid={`gmc-kpi-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
              <div className="text-xl font-black tabular">{v}</div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-2 top-2.5 text-muted-foreground" />
            <Input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="Search name / code…"
              className="h-8 rounded-sm pl-7 w-48" data-testid="gmc-search" />
          </div>
          <select value={filters.scope} onChange={(e) => setFilters({ ...filters, scope: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="gmc-filter-scope">
            <option value="">All coverage</option>
            <option value="project">Project-wise</option>
            <option value="head_office">Head Office</option>
          </select>
          <ProjectSelect label="" value={filters.project_code} onChange={(v) => setFilters({ ...filters, project_code: v })}
            className="w-52" testid="gmc-filter-project" placeholder="— all projects —" />
          <select value={filters.designation} onChange={(e) => setFilters({ ...filters, designation: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="gmc-filter-designation">
            <option value="">All designations</option>
            {designations.map((d) => <option key={d.id || d.name} value={d.name}>{d.name}</option>)}
          </select>
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="gmc-filter-status">
            <option value="active">Active members</option>
            <option value="removed">Removed / Exited</option>
            <option value="">All</option>
          </select>
          <div className="flex-1" />
          {canWrite && policyId && (
            <Button size="sm" className="h-8 rounded-sm" onClick={() => setAddDlg(true)} data-testid="gmc-add-members">
              <ShieldPlus className="h-3.5 w-3.5 mr-1.5" /> Add Members
            </Button>
          )}
        </div>
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Employee</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Designation</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Coverage</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Sum Insured</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Premium</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            <TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {members.length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                No members {filters.status === "removed" ? "removed yet" : "enrolled yet"}. {canWrite && policyId ? "Use Add Members to enrol employees from the Employee Master." : ""}
              </TableCell></TableRow>
            )}
            {members.map((m) => (
              <TableRow key={m.id} data-testid={`gmc-member-${m.id}`} className={m.status === "removed" ? "opacity-60" : ""}>
                <TableCell>
                  <div className="font-semibold text-sm">{m.name}</div>
                  <div className="text-[10px] font-mono-data text-muted-foreground">{m.emp_code}{m.department ? ` · ${m.department}` : ""}</div>
                </TableCell>
                <TableCell className="text-xs">{m.designation || "—"}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="rounded-sm text-[10px] uppercase">{m.coverage_scope === "head_office" ? "Head Office" : "Project"}</Badge>
                  {(m.dependents || 0) > 0 && <div className="text-[10px] text-muted-foreground mt-0.5">+{m.dependents} dependent(s)</div>}
                </TableCell>
                <TableCell className="text-xs font-mono-data">{m.project_code || "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-xs">{inr(m.sum_insured)}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-xs">{inr(m.premium)}</TableCell>
                <TableCell>
                  {m.status === "active"
                    ? <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Active</Badge>
                    : <div>
                        <Badge variant="destructive" className="rounded-sm">Removed</Badge>
                        <div className="text-[10px] text-muted-foreground mt-0.5 max-w-[180px]">{m.removal_reason}</div>
                      </div>}
                </TableCell>
                <TableCell className="text-right">
                  {canWrite && m.status === "active" && (
                    <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive" onClick={() => setRemoveFor(m)} data-testid={`gmc-remove-${m.id}`}>
                      <UserMinus className="h-3 w-3 mr-1" /> Remove
                    </Button>
                  )}
                  {canWrite && m.status === "removed" && (
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => restoreMember(m)} data-testid={`gmc-restore-${m.id}`}>
                      <RotateCcw className="h-3 w-3 mr-1" /> Restore
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!policyDlg} onOpenChange={(o) => !o && setPolicyDlg(null)}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">{policyDlg?.id ? "Edit Policy" : "New Group Medical Policy"}</DialogTitle>
            <DialogDescription className="sr-only">Group medical policy details.</DialogDescription>
          </DialogHeader>
          {policyDlg && (
            <div className="grid grid-cols-2 gap-3 py-1">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Policy Number *</Label>
                <Input value={policyDlg.policy_number} onChange={(e) => setPolicyDlg({ ...policyDlg, policy_number: e.target.value })} className="h-9 rounded-sm mt-1 font-mono-data" data-testid="gmc-policy-number" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Insurer *</Label>
                <Input value={policyDlg.insurer} onChange={(e) => setPolicyDlg({ ...policyDlg, insurer: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="gmc-policy-insurer" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">TPA</Label>
                <Input value={policyDlg.tpa || ""} onChange={(e) => setPolicyDlg({ ...policyDlg, tpa: e.target.value })} className="h-9 rounded-sm mt-1" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Status</Label>
                <select value={policyDlg.status} onChange={(e) => setPolicyDlg({ ...policyDlg, status: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1">
                  <option value="active">Active</option>
                  <option value="expired">Expired</option>
                </select>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Policy Start</Label>
                <Input type="date" value={policyDlg.policy_start || ""} onChange={(e) => setPolicyDlg({ ...policyDlg, policy_start: e.target.value })} className="h-9 rounded-sm mt-1" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Policy End</Label>
                <Input type="date" value={policyDlg.policy_end || ""} onChange={(e) => setPolicyDlg({ ...policyDlg, policy_end: e.target.value })} className="h-9 rounded-sm mt-1" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Default Sum Insured / Employee</Label>
                <Input type="number" value={policyDlg.sum_insured_default} onChange={(e) => setPolicyDlg({ ...policyDlg, sum_insured_default: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="gmc-policy-si" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Total Annual Premium</Label>
                <Input type="number" value={policyDlg.premium_total} onChange={(e) => setPolicyDlg({ ...policyDlg, premium_total: e.target.value })} className="h-9 rounded-sm mt-1 tabular" />
              </div>
              <div className="col-span-2">
                <Label className="text-[10px] uppercase tracking-wider">Notes</Label>
                <Textarea value={policyDlg.notes || ""} onChange={(e) => setPolicyDlg({ ...policyDlg, notes: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setPolicyDlg(null)}>Cancel</Button>
            <Button className="rounded-sm" onClick={savePolicy} data-testid="gmc-policy-save">Save Policy</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {addDlg && policy && (
        <AddMembersDialog policy={policy} onClose={() => setAddDlg(false)} onAdded={() => { setAddDlg(false); loadMembers(); loadPolicies(); }} />
      )}

      <Dialog open={!!removeFor} onOpenChange={(o) => !o && setRemoveFor(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Remove from policy</DialogTitle>
            <DialogDescription>Removing <b>{removeFor?.name}</b> from {policy?.policy_number}. This is recorded with reason & timestamp.</DialogDescription>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Reason</Label>
            <Textarea value={removeReason} onChange={(e) => setRemoveReason(e.target.value)} placeholder="e.g. Resigned / transferred / opted out" className="rounded-sm mt-1 min-h-[60px]" data-testid="gmc-remove-reason" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRemoveFor(null)}>Cancel</Button>
            <Button variant="destructive" className="rounded-sm" onClick={removeMember} data-testid="gmc-remove-confirm">Remove Member</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AddMembersDialog({ policy, onClose, onAdded }) {
  const [eligible, setEligible] = useState([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(new Set());
  const [scope, setScope] = useState("auto");
  const [projectCode, setProjectCode] = useState("");
  const [sumInsured, setSumInsured] = useState(policy.sum_insured_default || 0);
  const [premium, setPremium] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      api.get("/gmc/eligible-employees", { params: { policy_id: policy.id, q: q || undefined } })
        .then((r) => setEligible(r.data || [])).catch(() => setEligible([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, policy.id]);

  const toggle = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allVisible = eligible.length > 0 && eligible.every((e) => picked.has(e.id));

  const add = async () => {
    if (!picked.size) { toast.error("Select at least one employee"); return; }
    setBusy(true);
    try {
      const r = await api.post("/gmc/members/bulk-add", {
        policy_id: policy.id, employee_ids: Array.from(picked),
        coverage_scope: scope, project_code: scope === "project" ? projectCode : "",
        sum_insured: Number(sumInsured) || 0, premium: Number(premium) || 0, dependents: 0,
      });
      toast.success(`${r.data.added} member(s) added${r.data.skipped ? ` · ${r.data.skipped} skipped` : ""}`);
      onAdded();
    } catch (e) { toast.error(e?.response?.data?.detail || "Add failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="gmc-add-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Add Members — {policy.policy_number}</DialogTitle>
          <DialogDescription>Only active employees from the Employee Master not already covered are listed. Exited employees are excluded automatically.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Coverage</Label>
            <select value={scope} onChange={(e) => setScope(e.target.value)}
              className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="gmc-add-scope">
              <option value="auto">Auto (from employee's project)</option>
              <option value="project">Project-wise</option>
              <option value="head_office">Head Office</option>
            </select>
          </div>
          <div>
            {scope === "project"
              ? <ProjectSelect label="Project" value={projectCode} onChange={setProjectCode} testid="gmc-add-project" />
              : <div>
                  <Label className="text-[10px] uppercase tracking-wider">Project</Label>
                  <div className="h-9 mt-1 flex items-center px-2 border border-border rounded-sm bg-secondary text-xs text-muted-foreground">{scope === "head_office" ? "Head Office" : "Auto from employee"}</div>
                </div>}
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Sum Insured / Employee</Label>
            <Input type="number" value={sumInsured} onChange={(e) => setSumInsured(e.target.value)} className="h-9 rounded-sm mt-1 tabular" data-testid="gmc-add-si" />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Premium / Employee</Label>
            <Input type="number" value={premium} onChange={(e) => setPremium(e.target.value)} className="h-9 rounded-sm mt-1 tabular" />
          </div>
        </div>
        <div className="border border-border rounded-sm">
          <div className="flex items-center gap-2 p-2 border-b border-border">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search employee name / code…" className="h-8 rounded-sm w-64" data-testid="gmc-add-search" />
            <div className="flex-1" />
            <span className="text-[11px] text-muted-foreground">{picked.size} selected</span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
                <TableHead className="w-8"><Checkbox checked={allVisible} onCheckedChange={() => {
                  setPicked((s) => { const n = new Set(s); eligible.forEach((e) => allVisible ? n.delete(e.id) : n.add(e.id)); return n; });
                }} data-testid="gmc-add-pick-all" /></TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Employee</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Designation</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Dept</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Current Project</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {eligible.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center py-6 text-xs text-muted-foreground">No eligible employees found.</TableCell></TableRow>
                )}
                {eligible.map((e) => (
                  <TableRow key={e.id} className="cursor-pointer" onClick={() => toggle(e.id)} data-testid={`gmc-eligible-${e.id}`}>
                    <TableCell onClick={(ev) => ev.stopPropagation()}><Checkbox checked={picked.has(e.id)} onCheckedChange={() => toggle(e.id)} /></TableCell>
                    <TableCell><div className="text-sm font-semibold">{e.name}</div><div className="text-[10px] font-mono-data text-muted-foreground">{e.emp_code}</div></TableCell>
                    <TableCell className="text-xs">{e.designation || "—"}</TableCell>
                    <TableCell className="text-xs">{e.department || "—"}</TableCell>
                    <TableCell className="text-xs font-mono-data">{e.current_project_code || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={add} disabled={busy} data-testid="gmc-add-confirm">
            <ShieldPlus className="h-4 w-4 mr-1.5" /> Add {picked.size ? `${picked.size} ` : ""}Member(s)
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
