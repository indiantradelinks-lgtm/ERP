import { useEffect, useMemo, useState } from "react";
import {
  UserPlus, CheckCircle2, Circle, Trash2, Search, Plus,
  IdCard, Hammer, ShieldCheck, MapPinned, FileCheck, ChevronRight, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { api, apiErrorMessage, stripEmpty } from "@/lib/api";
import { toast } from "sonner";
import { DepartmentSelect } from "@/components/DepartmentSelect";

const STAGE_ICONS = {
  offer_accepted: FileCheck,
  docs_uploaded: FileCheck,
  id_card_issued: IdCard,
  ppe_issued: Hammer,
  induction_done: ShieldCheck,
  site_assigned: MapPinned,
};

const ROLES = [
  "supervisor", "site_engineer", "project_manager", "safety_officer",
  "store_incharge", "purchase_officer", "accounts_executive", "hr_executive", "client_rep",
];

const blankForm = () => ({
  name: "", email: "", phone: "",
  role: "supervisor", department: "", joining_date: "",
  designation: "", salary: 0, notes: "",
});

export default function Onboarding() {
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [detail, setDetail] = useState(null);
  const [completing, setCompleting] = useState(false);
  const [completeOpts, setCompleteOpts] = useState({
    create_login: true, default_password: "", issue_ppe_kit: true, schedule_induction: true,
  });

  const load = async () => {
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const r = await api.get("/hr/onboardings", { params });
      setRows(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) =>
      [r.name, r.email, r.department, r.designation].some((v) => (v || "").toLowerCase().includes(s))
    );
  }, [rows, q]);

  const create = async () => {
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    try {
      const payload = stripEmpty({ ...form, salary: form.salary ? Number(form.salary) : null });
      await api.post("/hr/onboardings", payload);
      toast.success("Onboarding created");
      setCreating(false); setForm(blankForm()); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Create failed")); }
  };

  const advance = async (oid, stage_key) => {
    try {
      const r = await api.post(`/hr/onboardings/${oid}/advance`, { stage_key });
      setDetail(r.data);
      load();
    } catch (e) { toast.error(apiErrorMessage(e, "Advance failed")); }
  };

  const complete = async () => {
    if (!detail) return;
    try {
      const r = await api.post(`/hr/onboardings/${detail.id}/complete`, completeOpts);
      toast.success(`Onboarded. EMP ${r.data.triggers?.emp_code || "—"} created. PPE & Induction auto-scheduled.`);
      setCompleting(false); setDetail(null); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Complete failed")); }
  };

  const remove = async (oid) => {
    if (!window.confirm("Delete this onboarding record?")) return;
    try {
      await api.delete(`/hr/onboardings/${oid}`);
      toast.success("Deleted"); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  const progressPct = (r) => {
    if (!r.stages?.length) return 0;
    const done = r.stages.filter((s) => s.done).length;
    return Math.round((done / r.stages.length) * 100);
  };

  return (
    <div className="space-y-6" data-testid="hr-onboarding-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <UserPlus className="h-3 w-3" /> Human Resources
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Onboarding</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Multi-stage joiner checklist. Completion auto-creates the employee record, login,
          PPE kit issuance, safety induction training and default leave balances.
        </p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="onb-search" />
          </div>
          <Select value={statusFilter || "__all"} onValueChange={(v) => setStatusFilter(v === "__all" ? "" : v)}>
            <SelectTrigger className="h-9 w-40 rounded-sm" data-testid="onb-status-filter">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">All status</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-[11px] text-muted-foreground">{filtered.length} of {rows.length}</span>
          <Button className="ml-auto h-9 rounded-sm" onClick={() => { setForm(blankForm()); setCreating(true); }} data-testid="onb-new">
            <Plus className="h-4 w-4 mr-1.5" /> New Onboarding
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Joiner</TableHead>
              <TableHead>Role / Dept</TableHead>
              <TableHead>Joining</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No onboardings.</TableCell></TableRow>
            )}
            {filtered.map((r) => (
              <TableRow key={r.id} data-testid={`onb-row-${r.id}`}>
                <TableCell>
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-[11px] text-muted-foreground">{r.email || "—"} · {r.phone || "—"}</div>
                </TableCell>
                <TableCell>
                  <div className="text-sm">{r.designation || r.role}</div>
                  <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{r.department || "—"}</div>
                </TableCell>
                <TableCell className="text-[12px]">{r.joining_date || "—"}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2 min-w-[160px]">
                    <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-primary transition-all" style={{ width: `${progressPct(r)}%` }} />
                    </div>
                    <span className="text-[11px] tabular text-muted-foreground">{progressPct(r)}%</span>
                  </div>
                </TableCell>
                <TableCell>
                  {r.status === "completed"
                    ? <Badge className="bg-emerald-100 text-emerald-900 border-emerald-300 rounded-sm">Completed</Badge>
                    : <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">In Progress</Badge>}
                </TableCell>
                <TableCell className="text-right">
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setDetail(r)} data-testid={`onb-open-${r.id}`}>
                      Open <ChevronRight className="h-3 w-3 ml-1" />
                    </Button>
                    {r.status !== "completed" && (
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r.id)} data-testid={`onb-delete-${r.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Create dialog */}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><UserPlus className="h-4 w-4 text-primary" /> New Onboarding</DialogTitle>
            <DialogDescription>Capture joiner details. You can advance stages from the Open view.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <Field label="Full Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="onb-form-name" />
            <Field label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="onb-form-email" />
            <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testid="onb-form-phone" />
            <Field label="Designation" value={form.designation} onChange={(v) => setForm({ ...form, designation: v })} testid="onb-form-desig" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="onb-form-role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => <SelectItem key={r} value={r}>{r.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <DepartmentSelect value={form.department} onChange={(v) => setForm({ ...form, department: v })} testid="onb-form-dept" />
            <Field label="Joining Date" type="date" value={form.joining_date} onChange={(v) => setForm({ ...form, joining_date: v })} testid="onb-form-joining" />
            <Field label="Salary (₹/mo)" type="number" value={form.salary} onChange={(v) => setForm({ ...form, salary: Number(v) })} testid="onb-form-salary" />
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Notes</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="onb-form-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="onb-form-save">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail / Stage tracker */}
      <Dialog open={!!detail} onOpenChange={() => { setDetail(null); setCompleting(false); }}>
        <DialogContent className="max-w-3xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><UserPlus className="h-4 w-4 text-primary" /> {detail?.name}</DialogTitle>
            <DialogDescription>
              {detail?.designation || detail?.role} · {detail?.department || "—"} · Joining {detail?.joining_date || "—"}
              {detail?.status === "completed" && (
                <Badge className="ml-2 bg-emerald-100 text-emerald-900 border-emerald-300 rounded-sm">Completed</Badge>
              )}
            </DialogDescription>
          </DialogHeader>

          {detail && (
            <div className="space-y-4">
              <div className="space-y-2">
                {detail.stages?.map((s) => {
                  const Icon = STAGE_ICONS[s.key] || Circle;
                  return (
                    <div key={s.key} className={`flex items-center gap-3 p-3 rounded-sm border ${s.done ? "border-emerald-300 bg-emerald-50" : "border-border bg-card"}`} data-testid={`onb-stage-${s.key}`}>
                      {s.done ? <CheckCircle2 className="h-5 w-5 text-emerald-700" /> : <Icon className="h-5 w-5 text-muted-foreground" />}
                      <div className="flex-1">
                        <div className="font-semibold text-sm">{s.label}</div>
                        {s.done && <div className="text-[11px] text-muted-foreground">{s.done_at?.slice(0, 16).replace("T", " ")} · {s.done_by}</div>}
                      </div>
                      {!s.done && detail.status !== "completed" && (
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => advance(detail.id, s.key)} data-testid={`onb-mark-${s.key}`}>
                          Mark Done
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>

              {detail.status === "completed" && detail.triggers && (
                <div className="bg-emerald-50 border border-emerald-300 rounded-sm p-3 text-[12px] space-y-1">
                  <div className="font-bold uppercase tracking-wider text-emerald-900 flex items-center gap-1"><Zap className="h-3 w-3" /> Auto-Triggers Fired</div>
                  <div>Employee Code: <span className="font-mono">{detail.triggers.emp_code}</span></div>
                  {detail.triggers.user_login && <div>Login: <span className="font-mono">{detail.triggers.user_login === "created" ? `Created (pwd: ${detail.triggers.default_password})` : "Existing user reused"}</span></div>}
                  {detail.triggers.ppe_issuance_id && <div>PPE Kit Issuance: <span className="font-mono">{detail.triggers.ppe_issuance_id.slice(0, 8)}…</span></div>}
                  {detail.triggers.safety_training_id && <div>Safety Induction: <span className="font-mono">{detail.triggers.safety_training_id.slice(0, 8)}…</span></div>}
                  <div>Leave balances granted across <span className="font-bold">{detail.triggers.leave_balances_granted}</span> types</div>
                </div>
              )}

              {completing && (
                <div className="bg-card border border-primary/40 rounded-sm p-3 space-y-2">
                  <div className="text-[11px] uppercase tracking-wider font-bold text-primary">Completion Triggers</div>
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox checked={completeOpts.create_login} onCheckedChange={(v) => setCompleteOpts({ ...completeOpts, create_login: !!v })} data-testid="onb-opt-login" />
                    Create login user (email + password)
                  </label>
                  {completeOpts.create_login && (
                    <Input placeholder="Default password (blank = Welcome@123)" value={completeOpts.default_password}
                      onChange={(e) => setCompleteOpts({ ...completeOpts, default_password: e.target.value })}
                      className="rounded-sm h-9" data-testid="onb-opt-pwd" />
                  )}
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox checked={completeOpts.issue_ppe_kit} onCheckedChange={(v) => setCompleteOpts({ ...completeOpts, issue_ppe_kit: !!v })} data-testid="onb-opt-ppe" />
                    Auto-issue starter PPE kit (helmet, shoes, vest, goggles, gloves)
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox checked={completeOpts.schedule_induction} onCheckedChange={(v) => setCompleteOpts({ ...completeOpts, schedule_induction: !!v })} data-testid="onb-opt-induction" />
                    Schedule Safety Induction training
                  </label>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            {detail?.status !== "completed" && !completing && (
              <Button className="rounded-sm" onClick={() => setCompleting(true)} data-testid="onb-complete-open">
                <Zap className="h-4 w-4 mr-1.5" /> Complete & Auto-Trigger
              </Button>
            )}
            {completing && (
              <>
                <Button variant="outline" className="rounded-sm" onClick={() => setCompleting(false)}>Back</Button>
                <Button className="rounded-sm" onClick={complete} data-testid="onb-complete-confirm">
                  <CheckCircle2 className="h-4 w-4 mr-1.5" /> Confirm & Complete
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
