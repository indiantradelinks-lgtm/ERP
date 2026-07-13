import { useEffect, useMemo, useState } from "react";
import {
  LogOut, Plus, Check, X as XIcon, Calculator, FileCheck, ChevronRight,
  Search, AlertTriangle, Trash2, Banknote,
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
import { api, apiErrorMessage, stripEmpty } from "@/lib/api";
import { toast } from "sonner";

const STATUS_TONE = {
  draft: "bg-secondary text-muted-foreground border-border",
  clearance_in_progress: "bg-amber-100 text-amber-900 border-amber-300",
  fnf_computed: "bg-blue-100 text-blue-900 border-blue-300",
  finalised: "bg-emerald-100 text-emerald-900 border-emerald-300",
};

const ITEM_TONE = {
  pending: "bg-amber-100 text-amber-900 border-amber-300",
  approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
  rejected: "bg-red-100 text-red-900 border-red-300",
};

const blankForm = () => ({
  employee_id: "", resignation_date: "", last_working_day: "",
  reason: "", notice_period_days: 30, advances: 0, bonus_accrual: 0, notes: "",
});

export default function Exit() {
  const [exits, setExits] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [detail, setDetail] = useState(null);
  const [remarksDialog, setRemarksDialog] = useState(null); // {item_key, mode}
  const [remarks, setRemarks] = useState("");

  const load = async () => {
    try {
      const [ex, emps] = await Promise.all([
        api.get("/hr/exits"),
        api.get("/employees"),
      ]);
      setExits(ex.data || []);
      setEmployees(emps.data || []);
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!q.trim()) return exits;
    const s = q.toLowerCase();
    return exits.filter((r) => [r.employee_name, r.emp_code, r.department, r.reason].some((v) => (v || "").toLowerCase().includes(s)));
  }, [exits, q]);

  const create = async () => {
    if (!form.employee_id || !form.resignation_date || !form.last_working_day) {
      toast.error("Employee, resignation date and last working day are required"); return;
    }
    try {
      await api.post("/hr/exits", stripEmpty(form));
      toast.success("Exit created — clearance pending");
      setCreating(false); setForm(blankForm()); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Create failed")); }
  };

  const refreshDetail = async (eid) => {
    try {
      const r = await api.get(`/hr/exits/${eid}`);
      setDetail(r.data);
      load();
    } catch (e) { toast.error(apiErrorMessage(e, "Reload failed")); }
  };

  const decideItem = async () => {
    if (!remarksDialog || !detail) return;
    try {
      await api.post(`/hr/exits/${detail.id}/clearance/${remarksDialog.item_key}/${remarksDialog.mode}`, { remarks });
      toast.success(`Item ${remarksDialog.mode}d`);
      setRemarksDialog(null); setRemarks("");
      refreshDetail(detail.id);
    } catch (e) { toast.error(apiErrorMessage(e, "Action failed")); }
  };

  const computeFnf = async () => {
    if (!detail) return;
    try {
      await api.post(`/hr/exits/${detail.id}/compute-fnf`);
      toast.success("FNF computed");
      refreshDetail(detail.id);
    } catch (e) { toast.error(apiErrorMessage(e, "Compute failed")); }
  };

  const overrideFnf = async (overrides) => {
    if (!detail) return;
    try {
      await api.put(`/hr/exits/${detail.id}/fnf`, { overrides });
      toast.success("FNF updated");
      refreshDetail(detail.id);
    } catch (e) { toast.error(apiErrorMessage(e, "Update failed")); }
  };

  const finalise = async () => {
    if (!detail) return;
    if (!window.confirm("Finalise this exit? Employee status will flip to 'exited' and a relieving letter will be auto-generated if a 'relieving' template exists.")) return;
    try {
      await api.post(`/hr/exits/${detail.id}/finalise`);
      toast.success("Exit finalised");
      refreshDetail(detail.id);
    } catch (e) { toast.error(apiErrorMessage(e, "Finalise failed")); }
  };

  const remove = async (eid) => {
    if (!window.confirm("Delete this draft exit?")) return;
    try {
      await api.delete(`/hr/exits/${eid}`);
      toast.success("Deleted"); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  const clearancePct = (r) => {
    const items = r.clearance || [];
    if (!items.length) return 0;
    return Math.round(items.filter((c) => c.status === "approved").length / items.length * 100);
  };

  return (
    <div className="space-y-6" data-testid="hr-exit-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <LogOut className="h-3 w-3" /> Human Resources
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Exit & FNF</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Resignation → 8-item clearance → FNF auto-compute (pending salary + EL/PL encashment + gratuity − advances − short-notice recovery) → finalise with auto-generated relieving letter.
        </p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="exit-search" />
          </div>
          <span className="text-[11px] text-muted-foreground">{filtered.length} of {exits.length}</span>
          <Button className="ml-auto h-9 rounded-sm" onClick={() => { setForm(blankForm()); setCreating(true); }} data-testid="exit-new">
            <Plus className="h-4 w-4 mr-1.5" /> New Exit
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead>LWD</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Clearance</TableHead>
              <TableHead className="text-right">Net Payable</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">No exits yet.</TableCell></TableRow>}
            {filtered.map((r) => (
              <TableRow key={r.id} data-testid={`exit-row-${r.id}`}>
                <TableCell>
                  <div className="font-semibold">{r.employee_name}</div>
                  <div className="text-[11px] text-muted-foreground"><span className="font-mono">{r.emp_code}</span> · {r.department || "—"}</div>
                </TableCell>
                <TableCell className="text-[12px]">{r.last_working_day}</TableCell>
                <TableCell className="text-[12px] max-w-xs truncate">{r.reason || "—"}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2 min-w-[120px]">
                    <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-primary transition-all" style={{ width: `${clearancePct(r)}%` }} />
                    </div>
                    <span className="text-[11px] tabular text-muted-foreground">{clearancePct(r)}%</span>
                  </div>
                </TableCell>
                <TableCell className="text-right tabular font-bold">
                  {r.fnf ? `₹ ${Number(r.fnf.net_payable || 0).toLocaleString("en-IN")}` : "—"}
                </TableCell>
                <TableCell>
                  <Badge className={`rounded-sm border ${STATUS_TONE[r.status] || ""}`}>{r.status.replace(/_/g, " ")}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setDetail(r)} data-testid={`exit-open-${r.id}`}>
                      Open <ChevronRight className="h-3 w-3 ml-1" />
                    </Button>
                    {r.status !== "finalised" && (
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r.id)} data-testid={`exit-delete-${r.id}`}>
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
            <DialogTitle className="font-display flex items-center gap-2"><LogOut className="h-4 w-4 text-primary" /> New Exit</DialogTitle>
            <DialogDescription>Capture resignation and notice details. Clearance + FNF flow follows.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Employee *</Label>
              <Select value={form.employee_id} onValueChange={(v) => setForm({ ...form, employee_id: v })}>
                <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="exit-form-emp"><SelectValue placeholder="Pick employee…" /></SelectTrigger>
                <SelectContent>
                  {employees.filter((e) => e.status === "active").map((e) => (
                    <SelectItem key={e.id} value={e.id}>{e.name} ({e.emp_code}) · {e.department || "—"}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Field label="Resignation Date *" type="date" value={form.resignation_date} onChange={(v) => setForm({ ...form, resignation_date: v })} testid="exit-form-res-date" />
            <Field label="Last Working Day *" type="date" value={form.last_working_day} onChange={(v) => setForm({ ...form, last_working_day: v })} testid="exit-form-lwd" />
            <Field label="Notice Period (days)" type="number" value={form.notice_period_days} onChange={(v) => setForm({ ...form, notice_period_days: Number(v) })} testid="exit-form-notice" />
            <Field label="Advances (₹)" type="number" value={form.advances} onChange={(v) => setForm({ ...form, advances: Number(v) })} testid="exit-form-advances" />
            <Field label="Bonus Accrual (₹)" type="number" value={form.bonus_accrual} onChange={(v) => setForm({ ...form, bonus_accrual: Number(v) })} testid="exit-form-bonus" />
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Reason</Label>
              <Textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="exit-form-reason" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Notes</Label>
              <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="exit-form-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="exit-form-save">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-3xl rounded-sm">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display flex items-center gap-2">
                  <LogOut className="h-4 w-4 text-primary" /> {detail.employee_name}
                  <Badge className={`ml-2 rounded-sm border ${STATUS_TONE[detail.status]}`}>{detail.status.replace(/_/g, " ")}</Badge>
                </DialogTitle>
                <DialogDescription>
                  <span className="font-mono">{detail.emp_code}</span> · {detail.department || "—"} · Joined {detail.joining_date || "—"} · LWD <b>{detail.last_working_day}</b>
                </DialogDescription>
              </DialogHeader>

              {/* Clearance grid */}
              <div className="space-y-2">
                <div className="text-[10px] uppercase tracking-wider font-bold text-primary">Clearance Checklist</div>
                {(detail.clearance || []).map((c) => (
                  <div key={c.key} className="flex items-center gap-3 p-2.5 rounded-sm border border-border bg-card" data-testid={`clearance-${c.key}`}>
                    <Badge className={`rounded-sm border text-[10px] uppercase ${ITEM_TONE[c.status] || ""}`}>{c.status}</Badge>
                    <div className="flex-1">
                      <div className="text-sm font-semibold">{c.label}</div>
                      <div className="text-[11px] text-muted-foreground">Approver: <span className="font-mono">{c.approver_role}</span>{c.approved_by ? ` · ${c.approved_by} on ${(c.approved_at || "").slice(0, 16).replace("T", " ")}` : ""}</div>
                      {c.remarks && <div className="text-[11px] text-muted-foreground italic">"{c.remarks}"</div>}
                    </div>
                    {c.status === "pending" && detail.status !== "finalised" && (
                      <div className="inline-flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm border-emerald-300 text-emerald-700" onClick={() => { setRemarksDialog({ item_key: c.key, mode: "approve" }); setRemarks(""); }} data-testid={`clearance-approve-${c.key}`}>
                          <Check className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm border-red-300 text-red-700" onClick={() => { setRemarksDialog({ item_key: c.key, mode: "reject" }); setRemarks(""); }} data-testid={`clearance-reject-${c.key}`}>
                          <XIcon className="h-3 w-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* FNF section */}
              {detail.fnf ? (
                <FnfPanel fnf={detail.fnf} onOverride={overrideFnf} disabled={detail.status === "finalised"} />
              ) : (
                <div className="bg-amber-50 border border-amber-300 rounded-sm p-3 text-[12px] flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-700" />
                  <span>FNF not computed yet. Approve all clearance items, then click <b>Compute FNF</b>.</span>
                </div>
              )}

              <DialogFooter className="gap-2">
                {!detail.fnf && detail.status !== "finalised" && (
                  <Button className="rounded-sm" onClick={computeFnf} data-testid="exit-compute-fnf">
                    <Calculator className="h-4 w-4 mr-1.5" /> Compute FNF
                  </Button>
                )}
                {detail.fnf && detail.status !== "finalised" && (
                  <Button className="rounded-sm bg-emerald-700 hover:bg-emerald-800" onClick={finalise} data-testid="exit-finalise">
                    <FileCheck className="h-4 w-4 mr-1.5" /> Finalise Exit
                  </Button>
                )}
                {detail.status === "finalised" && detail.relieving_letter_id && (
                  <span className="text-[12px] text-emerald-700">✓ Relieving letter auto-generated.</span>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Remarks dialog */}
      <Dialog open={!!remarksDialog} onOpenChange={() => setRemarksDialog(null)}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              {remarksDialog?.mode === "approve" ? <Check className="h-5 w-5 text-emerald-700" /> : <XIcon className="h-5 w-5 text-red-700" />}
              {remarksDialog?.mode === "approve" ? "Approve" : "Reject"} Clearance Item
            </DialogTitle>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Remarks (optional)</Label>
            <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} className="rounded-sm mt-1 min-h-[80px]" data-testid="clearance-remarks" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRemarksDialog(null)}>Cancel</Button>
            <Button className={`rounded-sm ${remarksDialog?.mode === "approve" ? "bg-emerald-700 hover:bg-emerald-800" : "bg-red-700 hover:bg-red-800"}`} onClick={decideItem} data-testid="clearance-confirm">
              {remarksDialog?.mode === "approve" ? "Approve" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function FnfPanel({ fnf, onOverride, disabled }) {
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState({});
  const fmt = (n) => `₹ ${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

  const row = (label, key, value, neg = false) => (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      {editing && !disabled ? (
        <Input
          type="number"
          defaultValue={value}
          onChange={(e) => setEdits({ ...edits, [key]: Number(e.target.value) })}
          className="h-7 w-32 rounded-sm tabular text-right"
          data-testid={`fnf-edit-${key}`}
        />
      ) : (
        <span className={`text-sm font-bold tabular ${neg ? "text-red-700" : ""}`}>{neg ? "−" : ""}{fmt(value)}</span>
      )}
    </div>
  );

  const save = () => {
    if (Object.keys(edits).length === 0) { setEditing(false); return; }
    onOverride(edits);
    setEdits({});
    setEditing(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 space-y-1">
      <div className="flex items-center gap-2 mb-1">
        <Banknote className="h-4 w-4 text-primary" />
        <div className="font-display font-bold text-sm">FNF Computation</div>
        {!disabled && (
          editing ? (
            <div className="ml-auto inline-flex gap-1">
              <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => { setEditing(false); setEdits({}); }}>Cancel</Button>
              <Button size="sm" className="h-7 rounded-sm" onClick={save} data-testid="fnf-save-overrides">Save</Button>
            </div>
          ) : (
            <Button size="sm" variant="outline" className="ml-auto h-7 rounded-sm" onClick={() => setEditing(true)} data-testid="fnf-edit">Edit</Button>
          )
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 text-sm">
        {row(`Pending Salary (${fnf.pending_days}d × ₹${fnf.per_day_rate}/d)`, "pending_salary", fnf.pending_salary)}
        {row(`Leave Encashment (${fnf.encashable_days} EL+PL days)`, "leave_encashment", fnf.leave_encashment)}
        {row(`Gratuity (tenure ${fnf.tenure_years}y)`, "gratuity", fnf.gratuity)}
        {row("Bonus Accrual", "bonus_accrual", fnf.bonus_accrual)}
        {row("Advances", "advances", fnf.advances, true)}
        {row(`Notice Recovery (${fnf.short_notice_days}d short)`, "notice_recovery", fnf.notice_recovery, true)}
      </div>
      <div className="border-t border-border pt-2 mt-2 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider font-bold">Net Payable</span>
        <span className="text-xl font-black tabular text-emerald-700">{fmt(fnf.net_payable)}</span>
      </div>
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
