import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Receipt, CheckCircle2, XCircle, Clock, ArrowRight, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect } from "@/components/MasterSelect";

const GENERATE_ROLES = new Set(["super_admin", "director", "accounts_executive", "billing_executive"]);
const REQUEST_ROLES = new Set(["super_admin", "director", "general_manager", "dept_head", "project_manager", "project_coordinator"]);

const STATUS_BADGE = {
  pending_approval: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Approval</Badge>,
  approved: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Approved</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
  bill_generated: <Badge className="rounded-sm bg-blue-100 text-blue-900 border-blue-300">Bill Generated</Badge>,
};

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;

const blank = () => ({ project_code: "", bill_type: "running", period_from: "", period_to: "", expected_amount: 0, remarks: "" });

export default function BillRequests() {
  const { user } = useAuth();
  const nav = useNavigate();
  const canRequest = user && REQUEST_ROLES.has(user.role);
  const canGenerate = user && GENERATE_ROLES.has(user.role);
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blank());
  const [ctx, setCtx] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/bill-requests", { params: statusFilter ? { status: statusFilter } : {} });
      setRows(r.data || []);
    } catch { toast.error("Failed to load bill requests"); }
  };
  useEffect(() => { load(); }, [statusFilter]); // eslint-disable-line

  const onProjectPicked = async (code) => {
    setForm({ ...form, project_code: code });
    setCtx(null);
    if (!code) return;
    try {
      const { data } = await api.get(`/ra-bills/project-context/${encodeURIComponent(code)}`);
      setCtx(data);
    } catch { /* context is a convenience only */ }
  };

  const create = async () => {
    if (!form.project_code) { toast.error("Select a project"); return; }
    try {
      const r = await api.post("/bill-requests", { ...form, expected_amount: Number(form.expected_amount) || 0 });
      toast.success(`Bill request ${r.data.request_no} submitted for approval (PM → Dept Head → GM → Director)`);
      setCreating(false); setForm(blank()); setCtx(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Create failed"); }
  };

  const kpi = useMemo(() => ({
    total: rows.length,
    pending: rows.filter((r) => r.status === "pending_approval").length,
    approved: rows.filter((r) => r.status === "approved").length,
    generated: rows.filter((r) => r.status === "bill_generated").length,
  }), [rows]);

  return (
    <div className="space-y-5" data-testid="bill-requests-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Receipt className="h-3 w-3" /> Billing Workflow
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Bill Generation Requests</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Projects & Operations team raises RA / Final bill requests → multi-level approval → Accounts generates the bill.
            Approval flow is editable anytime by Super Admin in Admin Console → Approval Matrix.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="br-reload"><RefreshCw className="h-4 w-4" /></Button>
          {canRequest && (
            <Button className="h-9 rounded-sm" onClick={() => { setForm(blank()); setCtx(null); setCreating(true); }} data-testid="br-new">
              <Plus className="h-4 w-4 mr-1.5" /> New Bill Request
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[["", "Total", kpi.total], ["pending_approval", "Pending Approval", kpi.pending],
          ["approved", "Approved — Awaiting Bill", kpi.approved], ["bill_generated", "Bills Generated", kpi.generated]].map(([k, label, v]) => (
          <button key={label} onClick={() => setStatusFilter(k)}
            className={`bg-card border rounded-sm p-3 text-left transition-colors hover:border-primary/50 ${statusFilter === k ? "border-primary" : "border-border"}`}
            data-testid={`br-kpi-${k || "total"}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <div className="text-2xl font-black tabular">{v}</div>
          </button>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request #</TableHead>
              <TableHead>Project / Client</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Period</TableHead>
              <TableHead className="text-right">Expected ₹</TableHead>
              <TableHead>Approval Progress</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                No bill requests yet. {canRequest ? "Raise one with New Bill Request." : ""}
              </TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`br-row-${r.id}`}>
                <TableCell className="font-mono-data text-xs font-bold">{r.request_no}
                  <div className="text-[10px] text-muted-foreground font-normal">{r.requested_by}</div>
                </TableCell>
                <TableCell>
                  <div className="font-semibold text-sm">{r.project_code}</div>
                  <div className="text-[11px] text-muted-foreground">{r.client_name || r.project_name}</div>
                </TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm uppercase text-[10px]">{r.bill_type}</Badge></TableCell>
                <TableCell className="text-xs">{r.period_from || "—"} → {r.period_to || "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-xs">{inr(r.expected_amount)}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1 flex-wrap" data-testid={`br-chain-${r.id}`}>
                    {(r.chain || []).map((s, i) => (
                      <span key={i} title={`${s.label}: ${s.status}`}
                        className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-sm border
                          ${s.status === "approved" ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                            : s.status === "rejected" ? "bg-rose-50 border-rose-300 text-rose-800"
                            : i === r.current_step && r.status === "pending_approval" ? "bg-amber-50 border-amber-300 text-amber-900"
                            : "bg-secondary border-border text-muted-foreground"}`}>
                        {s.status === "approved" ? <CheckCircle2 className="h-2.5 w-2.5" />
                          : s.status === "rejected" ? <XCircle className="h-2.5 w-2.5" />
                          : <Clock className="h-2.5 w-2.5" />}
                        {s.label}
                      </span>
                    ))}
                  </div>
                </TableCell>
                <TableCell>{STATUS_BADGE[r.status] || r.status}</TableCell>
                <TableCell className="text-right">
                  {r.status === "approved" && canGenerate && (
                    <Button size="sm" className="h-7 rounded-sm" onClick={() => nav(`/app/ra-bills?fromRequest=${r.id}`)} data-testid={`br-generate-${r.id}`}>
                      Generate Bill <ArrowRight className="h-3 w-3 ml-1" />
                    </Button>
                  )}
                  {r.status === "bill_generated" && (
                    <span className="text-xs font-mono-data text-blue-800" data-testid={`br-billno-${r.id}`}>{r.bill_number}</span>
                  )}
                  {r.status === "pending_approval" && (
                    <span className="text-[11px] text-muted-foreground">Awaiting {(r.chain || [])[r.current_step]?.label || "approval"}</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> New Bill Generation Request</DialogTitle>
            <DialogDescription>Goes for approval: Project Manager → Dept Head → GM → Director (Super Admin can change this in Approval Matrix).</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-1">
            <div className="col-span-2">
              <ProjectSelect label="Project" value={form.project_code} onChange={onProjectPicked} testid="br-form-project" />
              {ctx && (ctx.client_name || ctx.quotation_no) && (
                <div className="text-[11px] text-muted-foreground mt-1" data-testid="br-form-ctx">
                  Client: <b>{ctx.client_name || "—"}</b>{ctx.quotation_no ? <> · Offer: <b>{ctx.quotation_no}</b></> : null}{ctx.po_number ? <> · Customer PO: <b>{ctx.po_number}</b></> : null}
                </div>
              )}
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Bill Type</Label>
              <select value={form.bill_type} onChange={(e) => setForm({ ...form, bill_type: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="br-form-type">
                <option value="running">RA (Running) Bill</option>
                <option value="final">Final Bill</option>
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Expected Amount (₹)</Label>
              <Input type="number" value={form.expected_amount} onChange={(e) => setForm({ ...form, expected_amount: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="br-form-amount" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Period From</Label>
              <Input type="date" value={form.period_from} onChange={(e) => setForm({ ...form, period_from: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="br-form-from" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Period To</Label>
              <Input type="date" value={form.period_to} onChange={(e) => setForm({ ...form, period_to: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="br-form-to" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Remarks / Work Done Summary</Label>
              <Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="rounded-sm mt-1 min-h-[70px]" data-testid="br-form-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="br-form-submit">Submit for Approval</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
