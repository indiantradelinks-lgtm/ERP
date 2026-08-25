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
import FileUploader from "@/components/FileUploader";
import RowAttachments from "@/components/RowAttachments";

const GENERATE_ROLES = new Set(["super_admin", "director", "accounts_executive", "billing_executive"]);

const STATUS_BADGE = {
  pending_approval: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Approval</Badge>,
  approved: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Approved</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
  bill_generated: <Badge className="rounded-sm bg-blue-100 text-blue-900 border-blue-300">Bill Generated</Badge>,
};

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;

const blank = () => ({
  id: (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`),
  project_code: "", bill_type: "running", bill_nature: "", period_from: "", period_to: "",
  expected_amount: 0, items: [], remarks: "",
});

export default function BillRequests() {
  const { user, can } = useAuth();
  const nav = useNavigate();
  // Permission-driven (Role Register) — works for custom roles like Manager O P / Executive O P
  const canRequest = !!can && can("bill_requests", "write");
  const canGenerate = (user && GENERATE_ROLES.has(user.role)) || (!!can && can("ra_bills", "write"));
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [rejectFor, setRejectFor] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);

  const rejectBill = async () => {
    setRejecting(true);
    try {
      await api.post(`/bill-requests/${rejectFor.id}/reject`, { reason: rejectReason });
      toast.success(`${rejectFor.request_no || "Request"} rejected — remarks visible to the requester`);
      setRejectFor(null);
      setRejectReason("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to reject");
    } finally {
      setRejecting(false);
    }
  };
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blank());
  const [ctx, setCtx] = useState(null);
  const [attFiles, setAttFiles] = useState([]);
  const [attachFor, setAttachFor] = useState(null);

  const setItem = (i, patch) => setForm((f) => ({ ...f, items: f.items.map((x, ix) => ix === i ? { ...x, ...patch } : x) }));
  const totalAmount = form.items.reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0);

  const load = async () => {
    try {
      const r = await api.get("/bill-requests", { params: statusFilter ? { status: statusFilter } : {} });
      setRows(r.data || []);
    } catch { toast.error("Failed to load bill requests"); }
  };
  useEffect(() => { load(); }, [statusFilter]); // eslint-disable-line

  const onProjectPicked = async (code) => {
    setForm((f) => ({ ...f, project_code: code }));
    setCtx(null);
    if (!code) return;
    try {
      const { data } = await api.get(`/ra-bills/project-context/${encodeURIComponent(code)}`);
      setCtx(data);
      const items = (data.items || []).map((i) => ({
        description: i.description, quantity: i.quantity, unit: i.unit, rate: i.rate,
        offer_qty: i.offer_qty, billed_qty: i.billed_qty,
      }));
      setForm((f) => ({ ...f, project_code: code, items }));
      if (items.length) toast.success(`${items.length} line item(s) loaded from offer ${data.quotation_no || ""} — adjust quantities as per the customer work order`);
    } catch { /* context is a convenience only */ }
  };

  const create = async () => {
    if (!form.project_code) { toast.error("Select a project"); return; }
    if (!form.items.length) { toast.error("Add at least one line item (as per the customer work order)"); return; }
    try {
      const r = await api.post("/bill-requests", {
        ...form,
        client_name: ctx?.client_name || undefined,
        quotation_no: ctx?.quotation_no || undefined,
        po_number: ctx?.po_number || undefined,
        items: form.items.map((i) => ({ description: i.description, quantity: Number(i.quantity) || 0, unit: i.unit, rate: Number(i.rate) || 0 })),
        expected_amount: totalAmount,
      });
      toast.success(`Bill request ${r.data.request_no} submitted for approval with ${form.items.length} line item(s) & ${attFiles.length} document(s)`);
      setCreating(false); setForm(blank()); setCtx(null); setAttFiles([]); load();
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
                  {(r.quotation_no || r.po_number) && (
                    <div className="text-[10px] text-muted-foreground" data-testid={`br-refs-${r.id}`}>
                      {r.quotation_no && <>Offer: {r.quotation_no}</>}{r.quotation_no && r.po_number && " · "}{r.po_number && <>PO: {r.po_number}</>}
                    </div>
                  )}
                </TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm uppercase text-[10px]">{r.bill_type}</Badge></TableCell>
                <TableCell className="text-xs">{r.period_from || "—"} → {r.period_to || "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-xs">{inr(r.expected_amount)}
                  <div className="text-[10px] text-muted-foreground font-sans">
                    {(r.items || []).length > 0 && `${r.items.length} item(s)`}
                    {(r.attachment_count || 0) > 0 && (
                      <button className="ml-1 underline" onClick={() => setAttachFor(r)} data-testid={`br-atts-${r.id}`}>{r.attachment_count} doc(s)</button>
                    )}
                  </div>
                </TableCell>
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
                <TableCell>
                  {STATUS_BADGE[r.status] || r.status}
                  {r.status === "rejected" && r.reject_reason && (
                    <div className="text-[10px] text-rose-700 mt-0.5 max-w-[200px]" title={`Rejected by ${r.rejected_by || "Accounts"}: ${r.reject_reason}`} data-testid={`br-reject-reason-${r.id}`}>
                      ✗ {r.reject_reason}
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  {r.status === "approved" && canGenerate && (
                    <Button size="sm" className="h-7 rounded-sm" onClick={() => nav(`/app/ra-bills?fromRequest=${r.id}`)} data-testid={`br-generate-${r.id}`}>
                      Generate Bill <ArrowRight className="h-3 w-3 ml-1" />
                    </Button>
                  )}
                  {["approved", "pending_approval"].includes(r.status) && canGenerate && (
                    <Button size="sm" variant="ghost" className="h-7 rounded-sm text-rose-700 ml-1" onClick={() => { setRejectFor(r); setRejectReason(""); }} data-testid={`br-reject-${r.id}`} title="Reject this bill request with mandatory remarks">
                      Reject
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
        <DialogContent className="max-w-5xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> New Bill Generation Request</DialogTitle>
            <DialogDescription>Goes for approval: Project Manager → Dept Head → GM → Director (Super Admin can change this in Approval Matrix).</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Bill Type</Label>
                <select value={form.bill_type} onChange={(e) => setForm({ ...form, bill_type: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="br-form-type">
                  <option value="running">RA (Running) Bill</option>
                  <option value="final">Final Bill</option>
                </select>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Bill Nature</Label>
                <select value={form.bill_nature || ""} onChange={(e) => setForm({ ...form, bill_nature: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="br-form-nature">
                  <option value="">— Select —</option>
                  <option value="partial">Partial Bill</option>
                  <option value="one_time">One-Time Bill</option>
                  <option value="monthly_last">Last Bill of the Month</option>
                </select>
              </div>
              <div>
                <ProjectSelect label="Project Code" value={form.project_code} onChange={onProjectPicked} testid="br-form-project"
                  hint="Selecting a project auto-fills client, offer & line items" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Period From</Label>
                <Input type="date" value={form.period_from} onChange={(e) => setForm({ ...form, period_from: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="br-form-from" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Period To</Label>
                <Input type="date" value={form.period_to} onChange={(e) => setForm({ ...form, period_to: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="br-form-to" />
              </div>
            </div>
            {ctx && (ctx.client_name || ctx.quotation_no) && (
              <div className="text-[11px] text-muted-foreground -mt-1" data-testid="br-form-ctx">
                Client: <b>{ctx.client_name || "—"}</b>{ctx.quotation_no ? <> · Offer: <b>{ctx.quotation_no}</b></> : null}{ctx.po_number ? <> · Customer PO: <b>{ctx.po_number}</b></> : null}
              </div>
            )}

            <div className="border border-border rounded-sm">
              <div className="flex items-center justify-between p-2.5 border-b border-border">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">
                  Line Items
                  {ctx?.quotation_no && <span className="ml-2 normal-case tracking-normal font-normal text-muted-foreground">· format from offer {ctx.quotation_no}</span>}
                </div>
                <Button size="sm" variant="outline" className="h-7 rounded-sm"
                  onClick={() => setForm({ ...form, items: [...form.items, { description: "", quantity: 1, unit: "m²", rate: 0 }] })}
                  data-testid="br-add-item"><Plus className="h-3 w-3 mr-1" /> Add</Button>
              </div>
              <Table>
                <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Amount</TableHead>
                  <TableHead></TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {form.items.length === 0 && (
                    <TableRow><TableCell colSpan={6} className="text-xs text-muted-foreground text-center py-6">
                      Select a project to load the offer's line items, or click Add to enter manually.
                    </TableCell></TableRow>
                  )}
                  {form.items.map((it, i) => (
                    <TableRow key={`bri-${i}`}>
                      <TableCell><Input value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} className="h-8 rounded-sm" data-testid={`br-item-desc-${i}`} /></TableCell>
                      <TableCell>
                        <Input type="number" value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} className="h-8 rounded-sm w-20 tabular" data-testid={`br-item-qty-${i}`} />
                        {it.offer_qty != null && (
                          <div className="text-[10px] mt-0.5 whitespace-nowrap text-muted-foreground">Offer {it.offer_qty} · Billed {it.billed_qty || 0}</div>
                        )}
                      </TableCell>
                      <TableCell><Input value={it.unit} onChange={(e) => setItem(i, { unit: e.target.value })} className="h-8 rounded-sm w-20" /></TableCell>
                      <TableCell><Input type="number" value={it.rate} onChange={(e) => setItem(i, { rate: e.target.value })} className="h-8 rounded-sm w-24 tabular" data-testid={`br-item-rate-${i}`} /></TableCell>
                      <TableCell className="font-mono-data tabular text-xs font-bold">{inr((Number(it.quantity) || 0) * (Number(it.rate) || 0))}</TableCell>
                      <TableCell><Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: form.items.filter((_, ix) => ix !== i) })}><XCircle className="h-3 w-3" /></Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 bg-muted/30 border border-border rounded-sm p-3">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Items</div>
                <div className="font-mono-data tabular text-sm font-bold">{form.items.length}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Documents</div>
                <div className="font-mono-data tabular text-sm font-bold">{attFiles.length}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Request Total</div>
                <div className="font-mono-data tabular text-sm font-bold text-emerald-700" data-testid="br-form-total">{inr(totalAmount)}</div>
              </div>
            </div>

            <div>
              <Label className="text-[10px] uppercase tracking-wider">Supporting Billing Documents (measurement sheets, client sign-offs…)</Label>
              <div className="mt-1">
                <FileUploader folder="documents" parent_type="bill_requests" parent_id={form.id}
                  category="billing_support" compact
                  files={attFiles} onUploaded={(f) => setAttFiles((p) => [...p, f])}
                  onDeleted={(fid) => setAttFiles((p) => p.filter((x) => x.id !== fid))}
                  testidPrefix="br-uploader" />
              </div>
            </div>
            <div>
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

      <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
        parentType="bill_requests" parentId={attachFor?.id} recordTitle={`Documents — ${attachFor?.request_no || ""}`} />

      <Dialog open={!!rejectFor} onOpenChange={(o) => !o && setRejectFor(null)}>
        <DialogContent className="max-w-md rounded-sm" data-testid="br-reject-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-rose-700">Reject Bill Request — {rejectFor?.request_no}</DialogTitle>
            <DialogDescription>Rejection reason is mandatory and will be visible to the Manager/Operations user who raised this request.</DialogDescription>
          </DialogHeader>
          <Textarea rows={3} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Reason / remarks for rejection (min 5 characters)…" className="rounded-sm" data-testid="br-reject-reason-input" />
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRejectFor(null)}>Cancel</Button>
            <Button variant="destructive" className="rounded-sm" onClick={rejectBill} disabled={rejecting || rejectReason.trim().length < 5} data-testid="br-reject-confirm">Reject Request</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
