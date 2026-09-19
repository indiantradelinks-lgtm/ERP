/**
 * Debit / Credit Notes · Finance Phase 2
 *
 * Single page that manages both Debit Notes (against vendor bills) and
 * Credit Notes (against client invoices). On approval the backend auto-posts
 * the reversal JE via accounting_service.post_journal_entry().
 *
 * Backend: /api/finance/notes/*
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Receipt, Plus, RefreshCcw, CheckCircle2, Send, X, FileDown, AlertTriangle } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  cancelled: "bg-rose-100 text-rose-700",
};
const KIND_LABEL = { credit_note: "Credit Note", debit_note: "Debit Note" };

export default function DebitCreditNotes() {
  const [tab, setTab] = useState("credit_note");
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [reasonCodes, setReasonCodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openCreate, setOpenCreate] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [notesRes, clRes, vRes, rcRes] = await Promise.all([
        api.get(`/finance/notes?kind=${tab}`),
        lookupGet("/clients"),
        api.get("/vendors?status=approved"),
        api.get("/finance/notes/reason-codes"),
      ]);
      setRows(notesRes.data || []);
      const cl = Array.isArray(clRes.data) ? clRes.data : (clRes.data?.data || []);
      setClients(cl);
      setVendors(vRes.data || []);
      setReasonCodes(rcRes.data || []);
    } catch (e) {
      toast.error("Failed to load notes");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadAll(); }, [tab]);

  const counts = useMemo(() => {
    const out = { draft: 0, pending_approval: 0, approved: 0, cancelled: 0 };
    rows.forEach((r) => { out[r.status] = (out[r.status] || 0) + 1; });
    return out;
  }, [rows]);

  const submit = async (id) => {
    try {
      await api.post(`/finance/notes/${id}/submit`);
      toast.success("Submitted for approval");
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Submit failed"); }
  };
  const approve = async (id) => {
    try {
      const { data } = await api.post(`/finance/notes/${id}/approve`);
      toast.success(`Approved · JE ${data.je_number} posted`);
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Approve failed"); }
  };
  const cancel = async (id) => {
    const reason = window.prompt("Cancellation reason (min 3 chars):");
    if (!reason || reason.length < 3) return;
    try {
      await api.post(`/finance/notes/${id}/cancel?reason=${encodeURIComponent(reason)}`);
      toast.success("Cancelled");
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Cancel failed"); }
  };
  const downloadPdf = async (id, num) => {
    try {
      const res = await api.get(`/finance/notes/${id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${num || id}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("PDF download failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-debit-credit-notes">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Receipt className="h-6 w-6 text-primary" /> Debit / Credit Notes</h1>
          <p className="text-sm text-muted-foreground">Approve once · double-entry JE posts automatically to AR/AP + Revenue/Expense + GST.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} data-testid="dn-cn-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button size="sm" data-testid="dn-cn-new"><Plus className="h-4 w-4 mr-1" />New {KIND_LABEL[tab]}</Button>
            </DialogTrigger>
            <CreateNoteDialog kind={tab} clients={clients} vendors={vendors} reasonCodes={reasonCodes}
                              onClose={() => { setOpenCreate(false); loadAll(); }} />
          </Dialog>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {["draft", "pending_approval", "approved", "cancelled"].map((s) => (
          <Card key={s} className="p-2" data-testid={`kpi-${s}`}>
            <div className="text-xs text-slate-600">{s.replace("_", " ").toUpperCase()}</div>
            <div className="text-2xl font-bold">{counts[s]}</div>
          </Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="credit_note" data-testid="tab-credit-note">Credit Notes (Client)</TabsTrigger>
          <TabsTrigger value="debit_note" data-testid="tab-debit-note">Debit Notes (Vendor)</TabsTrigger>
        </TabsList>
        <TabsContent value={tab}>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-left">Note #</th>
                    <th className="px-3 py-2 text-left">Date</th>
                    <th className="px-3 py-2 text-left">Party</th>
                    <th className="px-3 py-2 text-left">Against</th>
                    <th className="px-3 py-2 text-left">Reason</th>
                    <th className="px-3 py-2 text-right">Total</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">Loading…</td></tr>}
                  {!loading && rows.length === 0 && <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">No {KIND_LABEL[tab]}s yet</td></tr>}
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b" data-testid={`note-row-${r.id}`}>
                      <td className="px-3 py-2 font-mono text-xs">{r.note_number}</td>
                      <td className="px-3 py-2 text-xs">{r.date}</td>
                      <td className="px-3 py-2 text-xs">{r.party_name}</td>
                      <td className="px-3 py-2 text-xs">{r.against_type} {r.against_number ? `· ${r.against_number}` : ""}</td>
                      <td className="px-3 py-2 text-xs">{r.reason_code?.replace("_", " ")}</td>
                      <td className="px-3 py-2 text-right">₹{Number(r.total_amount || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2">
                        <Badge className={STATUS_TONE[r.status] || ""}>{r.status?.replace("_", " ")}</Badge>
                        {r.auto_je_number && <div className="text-[10px] text-emerald-700 font-mono mt-0.5">JE: {r.auto_je_number}</div>}
                      </td>
                      <td className="px-3 py-2 text-right space-x-1">
                        {r.status === "draft" && (
                          <Button size="sm" variant="outline" onClick={() => submit(r.id)} data-testid={`note-submit-${r.id}`}>
                            <Send className="h-3.5 w-3.5 mr-1" />Submit
                          </Button>
                        )}
                        {r.status === "pending_approval" && (
                          <Button size="sm" variant="outline" onClick={() => approve(r.id)} data-testid={`note-approve-${r.id}`}>
                            <CheckCircle2 className="h-3.5 w-3.5 mr-1" />Approve
                          </Button>
                        )}
                        {r.status !== "approved" && r.status !== "cancelled" && (
                          <Button size="sm" variant="ghost" onClick={() => cancel(r.id)} data-testid={`note-cancel-${r.id}`}>
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => downloadPdf(r.id, r.note_number)} data-testid={`note-pdf-${r.id}`}>
                          <FileDown className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CreateNoteDialog({ kind, clients, vendors, reasonCodes, onClose }) {
  const isCredit = kind === "credit_note";
  const parties = isCredit ? clients : vendors;
  const [partyId, setPartyId] = useState("");
  const [againstType, setAgainstType] = useState(isCredit ? "invoice" : "vendor_bill");
  const [againstNumber, setAgainstNumber] = useState("");
  const [reasonCode, setReasonCode] = useState("price_difference");
  const [reason, setReason] = useState("");
  const [taxable, setTaxable] = useState(0);
  const [gst, setGst] = useState(18);
  const [tds, setTds] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const previewTotal = useMemo(() => {
    const base = Number(taxable) || 0;
    const gstA = (base * Number(gst)) / 100;
    const tdsA = (base * Number(tds)) / 100;
    return { base, gstA, tdsA, total: base + gstA - tdsA };
  }, [taxable, gst, tds]);

  const submit = async () => {
    if (!partyId || !reason || !taxable) { toast.error("Party, reason and taxable value required"); return; }
    setSubmitting(true);
    try {
      await api.post("/finance/notes", {
        kind, against_type: againstType, against_number: againstNumber || null,
        party_id: partyId, party_type: isCredit ? "client" : "vendor",
        reason_code: reasonCode, reason,
        taxable_value: Number(taxable), gst_percent: Number(gst), tds_percent: Number(tds),
      });
      toast.success(`${KIND_LABEL[kind]} created (draft)`);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogContent className="max-w-2xl" data-testid="note-create-dialog">
      <DialogHeader><DialogTitle>New {KIND_LABEL[kind]}</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="col-span-2">
          <Label>{isCredit ? "Client" : "Vendor"} *</Label>
          <Select value={partyId || undefined} onValueChange={setPartyId}>
            <SelectTrigger data-testid="note-party"><SelectValue placeholder={`— select ${isCredit ? "client" : "vendor"} —`} /></SelectTrigger>
            <SelectContent>
              {parties.map(p => <SelectItem key={p.id} value={p.id}>{p.vendor_code || p.client_code || p.code || ""} {p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Against type</Label>
          <Select value={againstType} onValueChange={setAgainstType}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={isCredit ? "invoice" : "vendor_bill"}>{isCredit ? "Client Invoice" : "Vendor Bill"}</SelectItem>
              <SelectItem value="po">Purchase Order</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div><Label>Against #</Label><Input value={againstNumber} onChange={e => setAgainstNumber(e.target.value)} placeholder="INV-… / VB-…" data-testid="note-against-number" /></div>
        <div className="col-span-2">
          <Label>Reason code</Label>
          <Select value={reasonCode} onValueChange={setReasonCode}>
            <SelectTrigger data-testid="note-reason-code"><SelectValue /></SelectTrigger>
            <SelectContent>
              {reasonCodes.map(rc => <SelectItem key={rc.code} value={rc.code}>{rc.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-2"><Label>Reason / narration *</Label><Textarea rows={2} value={reason} onChange={e => setReason(e.target.value)} data-testid="note-reason" /></div>
        <div><Label>Taxable value (₹) *</Label><Input type="number" value={taxable} onChange={e => setTaxable(e.target.value)} data-testid="note-taxable" /></div>
        <div><Label>GST %</Label><Input type="number" value={gst} onChange={e => setGst(e.target.value)} /></div>
        <div><Label>TDS %</Label><Input type="number" value={tds} onChange={e => setTds(e.target.value)} /></div>
        <div className="col-span-2 bg-slate-50 p-2 rounded text-xs font-mono">
          Base: ₹{previewTotal.base.toFixed(2)} · GST: ₹{previewTotal.gstA.toFixed(2)} · TDS: ₹{previewTotal.tdsA.toFixed(2)} · <b>Total: ₹{previewTotal.total.toFixed(2)}</b>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={submitting} data-testid="note-submit-btn">{submitting ? "Saving…" : "Save Draft"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}
