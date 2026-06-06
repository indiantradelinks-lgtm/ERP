import { useEffect, useMemo, useState } from "react";
import {
  Wallet, Plus, Check, X as XIcon, Filter, Banknote, FileText,
  AlertTriangle, Clock, Users, TrendingUp, Edit3, Send, Trash2, Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DepartmentSelect } from "@/components/DepartmentSelect";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  submitted: "bg-amber-100 text-amber-900 border-amber-300",
  under_approval: "bg-amber-100 text-amber-900 border-amber-300",
  approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
  rejected: "bg-red-100 text-red-900 border-red-300",
  payment_pending: "bg-blue-100 text-blue-900 border-blue-300",
  paid: "bg-purple-100 text-purple-900 border-purple-300",
  under_recovery: "bg-teal-100 text-teal-900 border-teal-300",
  closed: "bg-secondary text-muted-foreground border-border",
};

const PAYMENT_MODES = [
  { value: "bank_transfer", label: "Bank Transfer" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
  { value: "upi", label: "UPI" },
];

const todayIso = () => new Date().toISOString().slice(0, 10);
const currentMonth = () => new Date().toISOString().slice(0, 7);
const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const PRIVILEGED = ["super_admin", "director", "general_manager", "hr_executive", "accounts_executive"];
const ON_BEHALF_ROLES = [
  "super_admin", "hr_executive", "general_manager", "director",
  "project_manager", "dept_head", "accounts_executive",
];
const PAYMENT_ROLES = ["super_admin", "accounts_executive", "general_manager", "director"];

export default function Advances() {
  const { user } = useAuth();
  const [tab, setTab] = useState("register");
  const [advances, setAdvances] = useState([]);
  const [types, setTypes] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ status: "", advance_type: "", department: "" });
  const [showCreate, setShowCreate] = useState(false);
  const [showDetail, setShowDetail] = useState(null);
  const [showPayment, setShowPayment] = useState(null);

  const isPrivileged = PRIVILEGED.includes(user?.role);
  const canCreateOnBehalf = ON_BEHALF_ROLES.includes(user?.role);
  const canPay = PAYMENT_ROLES.includes(user?.role);

  const load = async () => {
    setLoading(true);
    try {
      const reqs = [
        api.get("/advances"),
        api.get("/advance-types?active_only=true"),
        api.get("/employees"),
      ];
      if (isPrivileged) reqs.push(api.get("/advances/dashboard/summary"));
      const results = await Promise.all(reqs);
      setAdvances(results[0].data || []);
      setTypes(results[1].data || []);
      setEmployees(results[2].data || []);
      if (results[3]) setSummary(results[3].data);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to load advances"));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    return advances.filter((a) => {
      if (filter.status && a.status !== filter.status) return false;
      if (filter.advance_type && a.advance_type !== filter.advance_type) return false;
      if (filter.department && a.department !== filter.department) return false;
      return true;
    });
  }, [advances, filter]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="advances-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="h-6 w-6 text-emerald-600" /> Employee Advance Register
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Salary/Medical/Emergency advances · approval workflow · payment & recovery ledger.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} data-testid="advance-new-btn">
          <Plus className="h-4 w-4 mr-1" /> New Advance Request
        </Button>
      </div>

      {/* Summary widgets */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryTile label="Outstanding" value={inr(summary.totals.outstanding)} icon={Wallet} tone="rose" />
          <SummaryTile label="Pending Approval" value={summary.totals.pending_approval} icon={Clock} tone="amber" />
          <SummaryTile label="Requested (lifetime)" value={inr(summary.totals.requested)} icon={FileText} tone="slate" />
          <SummaryTile label="Paid (lifetime)" value={inr(summary.totals.paid)} icon={Banknote} tone="emerald" />
          <SummaryTile label="Approved (lifetime)" value={inr(summary.totals.approved)} icon={Check} tone="blue" />
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="register" data-testid="tab-register">Register</TabsTrigger>
          {summary && <TabsTrigger value="dept-summary" data-testid="tab-dept">By Department</TabsTrigger>}
        </TabsList>

        <TabsContent value="register">
          <Card>
            <CardHeader className="flex flex-col md:flex-row md:items-center gap-3">
              <CardTitle className="flex-1 flex items-center gap-2 text-base"><Filter className="h-4 w-4" />Filters</CardTitle>
              <div className="flex flex-wrap gap-2">
                <Select value={filter.status} onValueChange={(v) => setFilter({ ...filter, status: v === "all" ? "" : v })}>
                  <SelectTrigger className="w-40" data-testid="filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    {Object.keys(STATUS_TONE).map((s) => <SelectItem key={s} value={s}>{s.replace(/_/g, " ")}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Select value={filter.advance_type} onValueChange={(v) => setFilter({ ...filter, advance_type: v === "all" ? "" : v })}>
                  <SelectTrigger className="w-44" data-testid="filter-type"><SelectValue placeholder="Type" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {types.map((t) => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <div className="w-44">
                  <DepartmentSelect label="" value={filter.department} onChange={(v) => setFilter({ ...filter, department: v })} testid="filter-department" />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : (
                <div className="overflow-x-auto border rounded">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Advance #</TableHead>
                        <TableHead>Employee</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead className="text-right">Requested</TableHead>
                        <TableHead className="text-right">Approved</TableHead>
                        <TableHead className="text-right">Outstanding</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Awaiting</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filtered.length === 0 && (
                        <TableRow><TableCell colSpan={9} className="text-center text-muted-foreground py-8">No advances yet</TableCell></TableRow>
                      )}
                      {filtered.map((a) => (
                        <TableRow key={a.id} data-testid={`advance-row-${a.advance_no}`}>
                          <TableCell className="font-mono text-xs font-medium">
                            {a.dept_doc_no || a.advance_no}
                            {a.dept_doc_no && <div className="text-[10px] text-muted-foreground">{a.advance_no}</div>}
                          </TableCell>
                          <TableCell>
                            <div className="font-medium text-sm">{a.employee_name}</div>
                            <div className="text-xs text-muted-foreground">{a.employee_code} · {a.department}</div>
                            {a.on_behalf_of && <Badge variant="outline" className="text-[10px] mt-0.5">On behalf · {a.created_by_role}</Badge>}
                          </TableCell>
                          <TableCell><Badge variant="outline">{a.advance_type}</Badge>{a.emergency && <Badge className="ml-1 bg-rose-100 text-rose-700">!</Badge>}</TableCell>
                          <TableCell className="text-right">{inr(a.requested_amount)}</TableCell>
                          <TableCell className="text-right">{inr(a.approved_amount)}</TableCell>
                          <TableCell className="text-right font-medium">{inr(a.outstanding)}</TableCell>
                          <TableCell><Badge className={STATUS_TONE[a.status] + " border"}>{a.status.replace(/_/g, " ")}</Badge></TableCell>
                          <TableCell className="text-xs">{a.awaiting_label || "—"}</TableCell>
                          <TableCell className="text-right">
                            <Button size="sm" variant="ghost" onClick={() => setShowDetail(a.id)} data-testid={`advance-view-${a.advance_no}`}><Eye className="h-3 w-3" /></Button>
                            {a.status === "approved" && canPay && (
                              <Button size="sm" variant="outline" className="ml-1" onClick={() => setShowPayment(a)} data-testid={`advance-pay-${a.advance_no}`}>
                                <Banknote className="h-3 w-3 mr-1" /> Pay
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {summary && (
          <TabsContent value="dept-summary">
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4" /> Department-wise Outstanding</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow><TableHead>Department</TableHead><TableHead className="text-right">Active Advances</TableHead><TableHead className="text-right">Outstanding</TableHead></TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.by_department.map((d) => (
                      <TableRow key={d.department || "—"}><TableCell className="font-medium">{d.department || "—"}</TableCell><TableCell className="text-right">{d.count}</TableCell><TableCell className="text-right">{inr(d.outstanding)}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {showCreate && (
        <CreateAdvanceDialog
          open={!!showCreate}
          onOpenChange={(v) => { if (!v) setShowCreate(false); }}
          types={types}
          employees={employees}
          canCreateOnBehalf={canCreateOnBehalf}
          currentUser={user}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}

      {showDetail && (
        <AdvanceDetailDialog
          id={showDetail}
          onOpenChange={(v) => { if (!v) setShowDetail(null); }}
          onChange={load}
          user={user}
        />
      )}

      {showPayment && (
        <PaymentDialog
          advance={showPayment}
          onOpenChange={(v) => { if (!v) setShowPayment(null); }}
          onPaid={() => { setShowPayment(null); load(); }}
        />
      )}
    </div>
  );
}

function SummaryTile({ label, value, icon: Icon, tone = "slate" }) {
  const TONE = { slate: "border-slate-200 bg-slate-50", emerald: "border-emerald-200 bg-emerald-50", rose: "border-rose-200 bg-rose-50", amber: "border-amber-200 bg-amber-50", blue: "border-blue-200 bg-blue-50" };
  return (
    <div className={`p-3 rounded border ${TONE[tone]}`}>
      <div className="flex items-center justify-between text-xs uppercase text-muted-foreground"><span>{label}</span><Icon className="h-3 w-3" /></div>
      <div className="text-xl font-bold mt-1">{value}</div>
    </div>
  );
}

function CreateAdvanceDialog({ open, onOpenChange, types, employees, canCreateOnBehalf, currentUser, onCreated }) {
  const [onBehalf, setOnBehalf] = useState(false);
  const [form, setForm] = useState({
    employee_id: "", advance_type: "", requested_amount: "", reason: "",
    emergency: false, site: "", project: "",
    repayment_start_month: currentMonth(), installments: 1, remarks: "",
  });
  const [saving, setSaving] = useState(false);
  const [selfEmpId, setSelfEmpId] = useState("");

  // Find current user's employee record for self-request
  useEffect(() => {
    if (!currentUser?.email) return;
    const me = employees.find((e) => (e.email || "").toLowerCase() === (currentUser.email || "").toLowerCase());
    if (me) setSelfEmpId(me.id);
  }, [employees, currentUser]);

  useEffect(() => {
    if (!onBehalf && selfEmpId) setForm((f) => ({ ...f, employee_id: selfEmpId }));
  }, [onBehalf, selfEmpId]);

  const selectedEmp = employees.find((e) => e.id === form.employee_id);
  const emi = form.installments > 0 && form.requested_amount > 0
    ? Math.round(Number(form.requested_amount) / Number(form.installments))
    : 0;

  const submit = async (asDraft) => {
    if (!form.employee_id || !form.advance_type || !form.requested_amount || !form.reason) {
      toast.error("Employee, type, amount and reason are required");
      return;
    }
    setSaving(true);
    try {
      await api.post("/advances", { ...form, requested_amount: Number(form.requested_amount), installments: Number(form.installments), submit: !asDraft });
      toast.success(asDraft ? "Saved as draft" : "Advance request submitted for approval");
      onCreated();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to submit"));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="advance-create-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus className="h-5 w-5" /> New Advance Request</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {canCreateOnBehalf && (
            <div className="flex items-center gap-2 p-2 border rounded bg-amber-50 border-amber-200">
              <Checkbox id="on-behalf" checked={onBehalf} onCheckedChange={(v) => setOnBehalf(!!v)} data-testid="on-behalf-toggle" />
              <Label htmlFor="on-behalf" className="cursor-pointer text-sm font-medium">
                Create on behalf of another employee (site request) — Coordinator workflow
              </Label>
            </div>
          )}

          {onBehalf ? (
            <div>
              <Label>Employee *</Label>
              <Select value={form.employee_id} onValueChange={(v) => setForm({ ...form, employee_id: v })}>
                <SelectTrigger data-testid="emp-select"><SelectValue placeholder="Pick site employee" /></SelectTrigger>
                <SelectContent>{employees.filter((e) => e.active !== false).map((e) => (
                  <SelectItem key={e.id} value={e.id}>{e.name} ({e.employee_id || e.emp_code || e.id.slice(0, 6)}) — {(e.departments || [])[0] || e.department || "—"}</SelectItem>
                ))}</SelectContent>
              </Select>
            </div>
          ) : (
            <div className="p-2 border rounded bg-slate-50 text-xs">
              <strong>Self-request:</strong> linked to <strong>{selectedEmp?.name || currentUser?.name || currentUser?.email}</strong>
              {!selfEmpId && <div className="text-rose-600 mt-1">⚠ No employee record matches your email — ask HR to create one or use "On Behalf".</div>}
            </div>
          )}

          {selectedEmp && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3 rounded border bg-slate-50 text-xs">
              <KV label="Code" value={selectedEmp.employee_id || selectedEmp.emp_code} />
              <KV label="Designation" value={selectedEmp.designation} />
              <KV label="Salary" value={inr(selectedEmp.salary)} />
              <KV label="Joining" value={selectedEmp.joining_date} />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Advance Type *</Label>
              <Select value={form.advance_type} onValueChange={(v) => setForm({ ...form, advance_type: v })}>
                <SelectTrigger data-testid="type-select"><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>{types.map((t) => (
                  <SelectItem key={t.id} value={t.name}>{t.name} {t.max_amount > 0 && <span className="text-xs text-muted-foreground ml-1">(max {inr(t.max_amount)})</span>}</SelectItem>
                ))}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Requested Amount *</Label>
              <Input type="number" value={form.requested_amount} onChange={(e) => setForm({ ...form, requested_amount: e.target.value })} data-testid="amount" />
            </div>
            <div>
              <Label>Installments</Label>
              <Input type="number" min={1} value={form.installments} onChange={(e) => setForm({ ...form, installments: e.target.value })} data-testid="installments" />
            </div>
            <div>
              <Label>Repayment Start Month</Label>
              <Input type="month" value={form.repayment_start_month} onChange={(e) => setForm({ ...form, repayment_start_month: e.target.value })} data-testid="repay-month" />
            </div>
            <div>
              <Label>Site</Label>
              <Input value={form.site} onChange={(e) => setForm({ ...form, site: e.target.value })} data-testid="site" />
            </div>
            <div>
              <Label>Project</Label>
              <Input value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} data-testid="project" />
            </div>
          </div>

          <div>
            <Label>Reason *</Label>
            <Textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} rows={2} data-testid="reason" />
          </div>
          <div>
            <Label>Remarks</Label>
            <Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} rows={2} data-testid="remarks" />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox id="emerg" checked={form.emergency} onCheckedChange={(v) => setForm({ ...form, emergency: !!v })} data-testid="emergency" />
            <Label htmlFor="emerg" className="cursor-pointer text-sm flex items-center gap-1"><AlertTriangle className="h-3 w-3 text-rose-600" /> Mark as Emergency (skip-line approval)</Label>
          </div>

          {emi > 0 && (
            <div className="p-3 rounded border bg-blue-50 border-blue-200 text-sm">
              <strong>Computed EMI:</strong> {inr(emi)} × {form.installments} starting {form.repayment_start_month}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => submit(true)} disabled={saving} data-testid="save-draft-btn"><FileText className="h-4 w-4 mr-1" />Save as Draft</Button>
          <Button onClick={() => submit(false)} disabled={saving} data-testid="submit-btn"><Send className="h-4 w-4 mr-1" />{saving ? "Submitting…" : "Submit for Approval"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KV({ label, value }) {
  return <div><div className="text-muted-foreground text-[10px] uppercase">{label}</div><div className="font-medium">{value || "—"}</div></div>;
}

function AdvanceDetailDialog({ id, onOpenChange, onChange, user }) {
  const [adv, setAdv] = useState(null);
  const [loading, setLoading] = useState(true);
  const reload = async () => {
    setLoading(true);
    try { const { data } = await api.get(`/advances/${id}`); setAdv(data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); }, [id]);

  const approvalAct = async (action) => {
    const comment = action === "reject" ? prompt("Rejection reason?") : prompt("Optional remark");
    if (action === "reject" && !comment) return;
    try {
      await api.post(`/approvals/${adv.approval.id}/action`, { action, comment: comment || "" });
      toast.success(`Marked as ${action}`);
      await reload();
      onChange?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const remove = async () => {
    if (!confirm("Delete this advance?")) return;
    try { await api.delete(`/advances/${id}`); toast.success("Deleted"); onChange?.(); onOpenChange(false); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const doRecovery = async (action) => {
    const month = prompt("Month (YYYY-MM)?", currentMonth());
    if (!month) return;
    let body = { month, note: "" };
    let url = "";
    if (action === "skip") {
      body.amount = adv.emi;
      body.note = prompt("Skip note (optional)") || "";
      url = `/advances/${id}/recovery/skip`;
    } else if (action === "foreclose") {
      body.amount = adv.outstanding;
      body.note = prompt("Receipt details (txn/cheque #)") || "";
      url = `/advances/${id}/recovery/foreclose`;
    } else if (action === "settle") {
      const w = prompt(`Waive how much? (max ₹${adv.outstanding})`, String(adv.outstanding));
      if (!w) return;
      body = { month, waived_amount: Number(w), note: prompt("Settlement reason") || "" };
      url = `/advances/${id}/recovery/settle`;
    }
    try {
      await api.post(url, body);
      toast.success("Recovery recorded");
      await reload();
      onChange?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  if (!adv) return (
    <Dialog open onOpenChange={onOpenChange}><DialogContent><DialogTitle>Loading…</DialogTitle></DialogContent></Dialog>
  );

  const isCurrentApprover = adv.approval && adv.approval.chain
    && adv.approval.chain[adv.approval.current_step]?.role === user?.role;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="advance-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="h-5 w-5" /> {adv.advance_no} — {adv.employee_name}
            <Badge className={STATUS_TONE[adv.status] + " border ml-2"}>{adv.status.replace(/_/g, " ")}</Badge>
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 border rounded bg-slate-50">
            <KV label="Type" value={adv.advance_type} />
            <KV label="Requested" value={inr(adv.requested_amount)} />
            <KV label="Approved" value={inr(adv.approved_amount)} />
            <KV label="Paid" value={inr(adv.paid_amount)} />
            <KV label="Installments" value={`${adv.remaining_installments} / ${adv.installments}`} />
            <KV label="EMI" value={inr(adv.emi)} />
            <KV label="Outstanding" value={inr(adv.outstanding)} />
            <KV label="Recovered" value={inr(adv.recovered_amount)} />
            <KV label="Repayment Start" value={adv.repayment_start_month} />
            <KV label="Site" value={adv.site} />
            <KV label="Project" value={adv.project} />
            <KV label="Emergency" value={adv.emergency ? "Yes ⚠" : "No"} />
          </div>

          <div>
            <Label className="font-semibold">Reason</Label>
            <div className="p-2 border rounded bg-white">{adv.reason}</div>
            {adv.remarks && <><Label className="font-semibold mt-2 block">Remarks</Label><div className="p-2 border rounded bg-white text-xs">{adv.remarks}</div></>}
          </div>

          {/* Approval Timeline */}
          {adv.approval?.chain && (
            <div>
              <Label className="font-semibold flex items-center gap-1"><Check className="h-4 w-4" /> Approval Timeline</Label>
              <ol className="space-y-1 mt-2">
                {adv.approval.chain.map((step, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <Badge variant="outline" className={
                      step.status === "approved" ? "bg-emerald-100 text-emerald-800" :
                      step.status === "rejected" ? "bg-rose-100 text-rose-800" :
                      i === adv.approval.current_step ? "bg-amber-100 text-amber-800" : "bg-slate-100"
                    }>{i + 1}</Badge>
                    <span className="font-medium">{step.label}</span>
                    <span className="text-muted-foreground">{step.role}</span>
                    {step.approver && <span className="text-muted-foreground">· {step.approver} · {step.at && new Date(step.at).toLocaleString()}</span>}
                    {step.comment && <span className="italic text-muted-foreground">"{step.comment}"</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Approver actions */}
          {isCurrentApprover && adv.approval?.status !== "approved" && adv.approval?.status !== "rejected" && (
            <div className="flex gap-2 p-3 border rounded bg-amber-50 border-amber-200">
              <Button onClick={() => approvalAct("approve")} data-testid="appr-approve"><Check className="h-4 w-4 mr-1" />Approve</Button>
              <Button variant="destructive" onClick={() => approvalAct("reject")} data-testid="appr-reject"><XIcon className="h-4 w-4 mr-1" />Reject</Button>
            </div>
          )}

          {/* Payment details */}
          {adv.payment && (
            <div>
              <Label className="font-semibold flex items-center gap-1"><Banknote className="h-4 w-4" /> Payment</Label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 border rounded bg-slate-50 text-xs">
                <KV label="Mode" value={adv.payment.mode} />
                <KV label="Amount" value={inr(adv.payment.paid_amount)} />
                <KV label="Date" value={adv.payment.payment_date} />
                <KV label="Voucher #" value={adv.payment.voucher_no} />
                <KV label="Txn #" value={adv.payment.txn_no} />
                <KV label="Bank" value={adv.payment.bank_name} />
                <KV label="Paid By" value={adv.payment.paid_by} />
                <KV label="Paid At" value={adv.payment.paid_at && new Date(adv.payment.paid_at).toLocaleString()} />
              </div>
            </div>
          )}

          {/* Recovery actions */}
          {(adv.status === "paid" || adv.status === "under_recovery") && adv.outstanding > 0 && (
            <div className="p-3 border rounded bg-teal-50 border-teal-200">
              <Label className="font-semibold flex items-center gap-1 mb-2"><TrendingUp className="h-4 w-4" />Recovery Actions</Label>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => doRecovery("skip")} data-testid="rec-skip">Skip EMI (this month)</Button>
                <Button size="sm" variant="outline" onClick={() => doRecovery("foreclose")} data-testid="rec-foreclose">Foreclose</Button>
                {(user?.role === "super_admin" || user?.role === "general_manager" || user?.role === "director") && (
                  <Button size="sm" variant="outline" onClick={() => doRecovery("settle")} data-testid="rec-settle">Settle & Write Off</Button>
                )}
              </div>
            </div>
          )}

          {/* Recovery history */}
          {adv.recoveries && adv.recoveries.length > 0 && (
            <div>
              <Label className="font-semibold">Recovery Ledger</Label>
              <div className="border rounded mt-1 overflow-x-auto">
                <Table>
                  <TableHeader><TableRow><TableHead>Month</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Note</TableHead><TableHead>By</TableHead></TableRow></TableHeader>
                  <TableBody>{adv.recoveries.map((r) => (
                    <TableRow key={r.id}><TableCell>{r.month}</TableCell><TableCell><Badge variant="outline">{r.type}</Badge></TableCell><TableCell className="text-right">{inr(r.amount)}</TableCell><TableCell className="text-xs">{r.note}</TableCell><TableCell className="text-xs">{r.by}</TableCell></TableRow>
                  ))}</TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* Status history */}
          {adv.status_history && (
            <div>
              <Label className="font-semibold">Activity Log</Label>
              <ul className="text-xs space-y-1 mt-1 max-h-40 overflow-y-auto border rounded p-2 bg-slate-50">
                {adv.status_history.map((h, i) => (
                  <li key={i}>
                    <span className="text-muted-foreground">{new Date(h.at).toLocaleString()}</span> · <strong>{h.by}</strong> ({h.by_role}) — {h.from} → {h.to}
                    {h.comment && <span className="italic"> · "{h.comment}"</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <DialogFooter>
          {(user?.role === "super_admin" || user?.role === "hr_executive") && !["paid", "under_recovery", "closed"].includes(adv.status) && (
            <Button variant="destructive" onClick={remove} data-testid="advance-delete-btn"><Trash2 className="h-4 w-4 mr-1" />Delete</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaymentDialog({ advance, onOpenChange, onPaid }) {
  const [form, setForm] = useState({
    mode: "bank_transfer",
    paid_amount: advance.approved_amount,
    payment_date: todayIso(),
    bank_name: "",
    voucher_no: "",
    txn_no: "",
    remarks: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!form.txn_no && form.mode !== "cash") {
      if (!confirm("Transaction number is empty — proceed anyway?")) return;
    }
    setSaving(true);
    try {
      await api.post(`/advances/${advance.id}/payment`, { ...form, paid_amount: Number(form.paid_amount) });
      toast.success(`Payment recorded — ${inr(form.paid_amount)}`);
      onPaid();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="payment-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Banknote className="h-5 w-5" /> Record Payment · {advance.advance_no}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="p-2 border rounded bg-emerald-50 text-xs">
            <strong>{advance.employee_name}</strong> · Approved {inr(advance.approved_amount)} · EMI {inr(advance.emi)} × {advance.installments}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Payment Mode *</Label>
              <Select value={form.mode} onValueChange={(v) => setForm({ ...form, mode: v })}>
                <SelectTrigger data-testid="pay-mode"><SelectValue /></SelectTrigger>
                <SelectContent>{PAYMENT_MODES.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Amount *</Label>
              <Input type="number" value={form.paid_amount} onChange={(e) => setForm({ ...form, paid_amount: e.target.value })} data-testid="pay-amount" />
            </div>
            <div>
              <Label>Date *</Label>
              <Input type="date" value={form.payment_date} onChange={(e) => setForm({ ...form, payment_date: e.target.value })} data-testid="pay-date" />
            </div>
            <div>
              <Label>Bank Name</Label>
              <Input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} data-testid="pay-bank" />
            </div>
            <div>
              <Label>Voucher #</Label>
              <Input value={form.voucher_no} onChange={(e) => setForm({ ...form, voucher_no: e.target.value })} data-testid="pay-voucher" />
            </div>
            <div>
              <Label>Transaction #</Label>
              <Input value={form.txn_no} onChange={(e) => setForm({ ...form, txn_no: e.target.value })} data-testid="pay-txn" />
            </div>
          </div>
          <div>
            <Label>Remarks</Label>
            <Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} rows={2} data-testid="pay-remarks" />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={saving} data-testid="pay-submit">{saving ? "Saving…" : "Record Payment"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
