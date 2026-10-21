import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Paperclip, Send, Scale, FileSearch } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import TermsEditor from "@/components/TermsEditor";
import { StatusChip, inr, dt, useSvcMeta } from "./shared";

const blankQuote = () => ({ vendor_id: "", amount: "", tax_pct: 18, other_charges: 0, timeline_days: "", validity_date: "", payment_terms: "", commercial_terms: "", technical_compliance: "compliant", remarks: "" });
const blankPo = () => ({ rate: "", quantity: 1, unit: "Lot", tax_pct: 18, other_charges: 0, service_period_from: "", service_period_to: "", completion_date: "", payment_terms: "", terms_conditions: "", terms_id: "", exception_override: false, exception_note: "" });

export default function ServiceRfqs() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const meta = useSvcMeta();
  const caps = meta?.role_caps || {};
  const [rows, setRows] = useState([]);
  const [approvedSrs, setApprovedSrs] = useState([]);
  const [creating, setCreating] = useState(null); // {sr_id, vendor_ids:[], ...}
  const [quoting, setQuoting] = useState(null); // rfq
  const [quote, setQuote] = useState(blankQuote());
  const [comparing, setComparing] = useState(null); // {rfq, rows, lowest}
  const [recommendId, setRecommendId] = useState("");
  const [recommendRemarks, setRecommendRemarks] = useState("");
  const [poFor, setPoFor] = useState(null); // rfq
  const [po, setPo] = useState(blankPo());
  const [terms, setTerms] = useState([]);
  const [docsFor, setDocsFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/service-workflow/rfqs"),
        api.get("/service-workflow/requests?status=approved"),
      ]);
      setRows(a.data); setApprovedSrs(b.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const srId = sp.get("create_sr");
    if (srId) {
      setCreating({ sr_id: srId, vendor_ids: [], scope_of_work: "", service_requirements: "", required_completion_date: "", commercial_terms: "", technical_terms: "", taxes_notes: "" });
      setSp({}, { replace: true });
    }
  }, [sp, setSp]);

  const createRfq = async () => {
    if (!creating.sr_id) return toast.error("Select an approved Service Request");
    if (!creating.vendor_ids.length) return toast.error("Select at least one vendor");
    setBusy(true);
    try {
      const { sr_id, ...body } = creating;
      const r = await api.post(`/service-workflow/requests/${sr_id}/rfq`, body);
      toast.success(`RFQ ${r.data.rfq_no} created`);
      setCreating(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const issue = async (r) => {
    try { await api.post(`/service-workflow/rfqs/${r.id}/issue`); toast.success(`${r.rfq_no} issued to vendors`); load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const saveQuote = async () => {
    setBusy(true);
    try {
      await api.post(`/service-workflow/rfqs/${quoting.id}/quotation`, {
        ...quote, amount: Number(quote.amount) || 0, tax_pct: Number(quote.tax_pct) || 0,
        other_charges: Number(quote.other_charges) || 0,
        timeline_days: quote.timeline_days === "" ? null : Number(quote.timeline_days),
      });
      toast.success("Quotation recorded");
      setQuoting(null); setQuote(blankQuote()); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const openCompare = async (r) => {
    try {
      const res = await api.get(`/service-workflow/rfqs/${r.id}/comparison`);
      setComparing({ ...res.data, rfq_id: r.id, status: r.status });
      setRecommendId(res.data.rfq.recommended_vendor_id || res.data.lowest_vendor_id || "");
      setRecommendRemarks("");
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const recommend = async () => {
    setBusy(true);
    try {
      await api.post(`/service-workflow/rfqs/${comparing.rfq_id}/recommend`, { vendor_id: recommendId, remarks: recommendRemarks });
      toast.success("Vendor selected — ready to create the PO");
      setComparing(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const createPo = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/service-workflow/rfqs/${poFor.id}/po`, {
        ...po, rate: Number(po.rate) || 0, quantity: Number(po.quantity) || 1,
        tax_pct: Number(po.tax_pct) || 0, other_charges: Number(po.other_charges) || 0,
      });
      toast.success(`Service PO ${r.data.po_no} created (draft)`);
      setPoFor(null); setPo(blankPo()); load();
      nav("/app/services/pos");
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const selectedVendorQuote = (rfq) => {
    const v = (rfq?.vendors || []).find((x) => x.vendor_id === rfq.recommended_vendor_id);
    return v?.quotation;
  };

  return (
    <div className="p-4 space-y-4" data-testid="svc-rfqs-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><FileSearch className="h-5 w-5" /> Service RFQs & Quotations</h1>
          <p className="text-xs text-muted-foreground">Float RFQs from approved Service Requests, capture vendor quotes, compare & select</p>
        </div>
        {caps.procurement && <Button onClick={() => setCreating({ sr_id: "", vendor_ids: [], scope_of_work: "", service_requirements: "", required_completion_date: "", commercial_terms: "", technical_terms: "", taxes_notes: "" })} data-testid="svc-rfq-new-btn"><Plus className="h-4 w-4 mr-1" /> Create RFQ</Button>}
      </div>

      <div className="border rounded-md bg-white overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead>RFQ No</TableHead><TableHead>Date</TableHead><TableHead>Service Request</TableHead>
            <TableHead>Category</TableHead><TableHead>Vendors</TableHead><TableHead>Quotes</TableHead>
            <TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => {
              const quoted = r.vendors.filter((v) => v.quotation).length;
              return (
                <TableRow key={r.id} data-testid={`svc-rfq-row-${r.rfq_no}`}>
                  <TableCell className="font-medium text-primary">{r.rfq_no}</TableCell>
                  <TableCell>{dt(r.rfq_date)}</TableCell>
                  <TableCell className="text-xs cursor-pointer text-primary" onClick={() => nav(`/app/services/requests/${r.sr_id}`)}>{r.sr_no}</TableCell>
                  <TableCell className="text-xs">{r.service_category || "—"}</TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{r.vendors.length}</Badge></TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{quoted}/{r.vendors.length}</Badge></TableCell>
                  <TableCell><StatusChip status={r.status} testid={`svc-rfq-status-${r.rfq_no}`} /></TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {caps.procurement && r.status === "draft" &&
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => issue(r)} data-testid={`svc-rfq-issue-${r.rfq_no}`}><Send className="h-3 w-3 mr-1" /> Issue</Button>}
                    {caps.procurement && ["issued", "quotations_received", "recommended"].includes(r.status) &&
                      <Button variant="outline" size="sm" className="h-7 text-xs ml-1" onClick={() => { setQuoting(r); setQuote(blankQuote()); }} data-testid={`svc-rfq-quote-${r.rfq_no}`}>Record Quote</Button>}
                    {["issued", "quotations_received", "recommended", "selection_approved", "po_created"].includes(r.status) &&
                      <Button variant="outline" size="sm" className="h-7 text-xs ml-1" onClick={() => openCompare(r)} data-testid={`svc-rfq-compare-${r.rfq_no}`}><Scale className="h-3 w-3 mr-1" /> Compare</Button>}
                    {caps.procurement && r.status === "selection_approved" &&
                      <Button size="sm" className="h-7 text-xs ml-1" onClick={async () => { setPoFor(r); const q = selectedVendorQuote(r); setPo({ ...blankPo(), rate: q?.amount ?? "", tax_pct: q?.tax_pct ?? 18, other_charges: q?.other_charges ?? 0, payment_terms: q?.payment_terms || "" }); try { setTerms((await api.get("/service-workflow/terms?active=true")).data); } catch { /* noop */ } }} data-testid={`svc-rfq-create-po-${r.rfq_no}`}>Create PO</Button>}
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDocsFor(r)} data-testid={`svc-rfq-docs-${r.rfq_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {!rows.length && <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">No RFQs yet — create one from an approved Service Request</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* Create RFQ */}
      <Dialog open={!!creating} onOpenChange={(o) => !o && setCreating(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-rfq-create-dialog">
          <DialogHeader><DialogTitle>Create RFQ from approved Service Request</DialogTitle></DialogHeader>
          {creating && (
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Approved Service Request *</Label>
                <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={creating.sr_id} onChange={(e) => setCreating({ ...creating, sr_id: e.target.value })} data-testid="svc-rfq-create-sr">
                  <option value="">— select —</option>
                  {approvedSrs.map((s) => <option key={s.id} value={s.id}>{s.sr_no} · {s.service_category} · {s.service_description?.slice(0, 60)}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Vendors * (multiple allowed)</Label>
                <div className="border rounded-md max-h-44 overflow-y-auto p-2 space-y-1" data-testid="svc-rfq-vendor-list">
                  {(meta?.vendors || []).map((v) => (
                    <label key={v.id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <Checkbox checked={creating.vendor_ids.includes(v.id)}
                        onCheckedChange={(c) => setCreating({ ...creating, vendor_ids: c ? [...creating.vendor_ids, v.id] : creating.vendor_ids.filter((x) => x !== v.id) })}
                        data-testid={`svc-rfq-vendor-${v.id}`} />
                      {v.name}{v.gstin ? <span className="text-[10px] text-muted-foreground">· {v.gstin}</span> : null}
                    </label>
                  ))}
                  {!(meta?.vendors || []).length && <p className="text-xs text-muted-foreground">No vendors in the master</p>}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><Label className="text-xs">Required Completion Date</Label><Input type="date" value={creating.required_completion_date} onChange={(e) => setCreating({ ...creating, required_completion_date: e.target.value })} data-testid="svc-rfq-create-date" /></div>
                <div><Label className="text-xs">Taxes (notes)</Label><Input value={creating.taxes_notes} onChange={(e) => setCreating({ ...creating, taxes_notes: e.target.value })} placeholder="e.g. GST 18% extra" data-testid="svc-rfq-create-taxes" /></div>
              </div>
              <div><Label className="text-xs">Scope of Work (carried from SR if blank)</Label><Textarea rows={2} value={creating.scope_of_work} onChange={(e) => setCreating({ ...creating, scope_of_work: e.target.value })} data-testid="svc-rfq-create-scope" /></div>
              <div><Label className="text-xs">Service Requirements</Label><Textarea rows={2} value={creating.service_requirements} onChange={(e) => setCreating({ ...creating, service_requirements: e.target.value })} data-testid="svc-rfq-create-reqs" /></div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><Label className="text-xs">Commercial Terms</Label><Textarea rows={2} value={creating.commercial_terms} onChange={(e) => setCreating({ ...creating, commercial_terms: e.target.value })} data-testid="svc-rfq-create-commercial" /></div>
                <div><Label className="text-xs">Technical Terms</Label><Textarea rows={2} value={creating.technical_terms} onChange={(e) => setCreating({ ...creating, technical_terms: e.target.value })} data-testid="svc-rfq-create-technical" /></div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(null)}>Cancel</Button>
            <Button disabled={busy} onClick={createRfq} data-testid="svc-rfq-create-confirm">Create RFQ</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Record quotation */}
      <Dialog open={!!quoting} onOpenChange={(o) => !o && setQuoting(null)}>
        <DialogContent className="max-w-xl rounded-sm" data-testid="svc-rfq-quote-dialog">
          <DialogHeader><DialogTitle>Record Vendor Quotation — {quoting?.rfq_no}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="md:col-span-2">
              <Label className="text-xs">Vendor *</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={quote.vendor_id} onChange={(e) => setQuote({ ...quote, vendor_id: e.target.value })} data-testid="svc-quote-vendor">
                <option value="">— select —</option>
                {(quoting?.vendors || []).map((v) => <option key={v.vendor_id} value={v.vendor_id}>{v.vendor_name}{v.quotation ? " (re-quote)" : ""}</option>)}
              </select>
            </div>
            <div><Label className="text-xs">Service Cost (₹, pre-tax) *</Label><Input type="number" min="0" value={quote.amount} onChange={(e) => setQuote({ ...quote, amount: e.target.value })} data-testid="svc-quote-amount" /></div>
            <div><Label className="text-xs">Tax / GST %</Label><Input type="number" min="0" value={quote.tax_pct} onChange={(e) => setQuote({ ...quote, tax_pct: e.target.value })} data-testid="svc-quote-tax" /></div>
            <div><Label className="text-xs">Other Charges (₹)</Label><Input type="number" min="0" value={quote.other_charges} onChange={(e) => setQuote({ ...quote, other_charges: e.target.value })} data-testid="svc-quote-other" /></div>
            <div><Label className="text-xs">Service Timeline (days)</Label><Input type="number" min="0" value={quote.timeline_days} onChange={(e) => setQuote({ ...quote, timeline_days: e.target.value })} data-testid="svc-quote-timeline" /></div>
            <div><Label className="text-xs">Quotation Validity</Label><Input type="date" value={quote.validity_date} onChange={(e) => setQuote({ ...quote, validity_date: e.target.value })} data-testid="svc-quote-validity" /></div>
            <div><Label className="text-xs">Payment Terms</Label><Input value={quote.payment_terms} onChange={(e) => setQuote({ ...quote, payment_terms: e.target.value })} data-testid="svc-quote-payterms" /></div>
            <div>
              <Label className="text-xs">Technical Compliance</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={quote.technical_compliance} onChange={(e) => setQuote({ ...quote, technical_compliance: e.target.value })} data-testid="svc-quote-compliance">
                <option value="compliant">Compliant</option><option value="partial">Partially compliant</option><option value="non_compliant">Non-compliant</option>
              </select>
            </div>
            <div className="md:col-span-2"><Label className="text-xs">Commercial Terms</Label><Input value={quote.commercial_terms} onChange={(e) => setQuote({ ...quote, commercial_terms: e.target.value })} data-testid="svc-quote-commercial" /></div>
            <div className="md:col-span-2"><Label className="text-xs">Vendor Remarks</Label><Input value={quote.remarks} onChange={(e) => setQuote({ ...quote, remarks: e.target.value })} data-testid="svc-quote-remarks" /></div>
            <p className="md:col-span-2 text-xs text-muted-foreground">
              Total: <b>{inr((Number(quote.amount) || 0) * (1 + (Number(quote.tax_pct) || 0) / 100) + (Number(quote.other_charges) || 0))}</b> · Upload the vendor's quotation PDF via the RFQ paperclip.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setQuoting(null)}>Cancel</Button>
            <Button disabled={busy || !quote.vendor_id} onClick={saveQuote} data-testid="svc-quote-save">Save Quotation</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Comparison */}
      <Dialog open={!!comparing} onOpenChange={(o) => !o && setComparing(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-rfq-compare-dialog">
          <DialogHeader><DialogTitle>Quotation Comparison — {comparing?.rfq?.rfq_no}</DialogTitle></DialogHeader>
          {comparing && (
            <>
              <div className="overflow-x-auto border rounded-md">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Vendor</TableHead><TableHead>Service Cost</TableHead><TableHead>Tax</TableHead>
                    <TableHead>Other</TableHead><TableHead>Total</TableHead><TableHead>Timeline</TableHead>
                    <TableHead>Validity</TableHead><TableHead>Pay Terms</TableHead><TableHead>Tech</TableHead><TableHead>Remarks</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {comparing.rows.map((r) => (
                      <TableRow key={r.vendor_id} className={r.vendor_id === comparing.lowest_vendor_id ? "bg-emerald-50/60" : ""} data-testid={`svc-compare-row-${r.vendor_id}`}>
                        <TableCell className="font-medium">{r.vendor_name}{r.vendor_id === comparing.lowest_vendor_id && <Badge className="ml-1 text-[9px] bg-emerald-600">L1</Badge>}</TableCell>
                        <TableCell>{r.has_quote ? inr(r.amount) : "—"}</TableCell>
                        <TableCell className="text-xs">{r.has_quote ? `${r.tax_pct}% (${inr(r.tax_amount)})` : "—"}</TableCell>
                        <TableCell>{r.has_quote ? inr(r.other_charges) : "—"}</TableCell>
                        <TableCell className="font-semibold tabular-nums">{r.has_quote ? inr(r.total) : "no quote"}</TableCell>
                        <TableCell className="text-xs">{r.timeline_days != null ? `${r.timeline_days}d` : "—"}</TableCell>
                        <TableCell className="text-xs">{dt(r.validity_date)}</TableCell>
                        <TableCell className="text-xs">{r.payment_terms || "—"}</TableCell>
                        <TableCell className="text-xs">{(r.technical_compliance || "—").replace("_", " ")}</TableCell>
                        <TableCell className="text-xs max-w-[140px] truncate" title={r.remarks}>{r.remarks || "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {caps.procurement && !["selection_approved", "po_created"].includes(comparing.rfq.status) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border rounded-md p-3 bg-muted/20">
                  <div>
                    <Label className="text-xs">Recommended Vendor</Label>
                    <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={recommendId} onChange={(e) => setRecommendId(e.target.value)} data-testid="svc-compare-recommend-vendor">
                      <option value="">— select —</option>
                      {comparing.rows.filter((r) => r.has_quote).map((r) => <option key={r.vendor_id} value={r.vendor_id}>{r.vendor_name} — {inr(r.total)}</option>)}
                    </select>
                  </div>
                  <div><Label className="text-xs">Justification / Remarks</Label><Input value={recommendRemarks} onChange={(e) => setRecommendRemarks(e.target.value)} data-testid="svc-compare-recommend-remarks" /></div>
                </div>
              )}
            </>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setComparing(null)}>Close</Button>
            {caps.procurement && comparing && !["selection_approved", "po_created"].includes(comparing.rfq.status) &&
              <Button disabled={busy || !recommendId} onClick={recommend} data-testid="svc-compare-recommend-submit">Submit Recommendation for Approval</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create PO */}
      <Dialog open={!!poFor} onOpenChange={(o) => !o && setPoFor(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-rfq-po-dialog">
          <DialogHeader><DialogTitle>Create Service PO — {poFor?.rfq_no} · {(poFor?.vendors || []).find((v) => v.vendor_id === poFor?.recommended_vendor_id)?.vendor_name}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div><Label className="text-xs">Rate (₹)</Label><Input type="number" min="0" value={po.rate} onChange={(e) => setPo({ ...po, rate: e.target.value })} data-testid="svc-po-rate" /></div>
            <div><Label className="text-xs">Quantity</Label><Input type="number" min="0" value={po.quantity} onChange={(e) => setPo({ ...po, quantity: e.target.value })} data-testid="svc-po-qty" /></div>
            <div><Label className="text-xs">Unit</Label><Input value={po.unit} onChange={(e) => setPo({ ...po, unit: e.target.value })} data-testid="svc-po-unit" /></div>
            <div><Label className="text-xs">Tax %</Label><Input type="number" min="0" value={po.tax_pct} onChange={(e) => setPo({ ...po, tax_pct: e.target.value })} data-testid="svc-po-tax" /></div>
            <div><Label className="text-xs">Other Charges (₹)</Label><Input type="number" min="0" value={po.other_charges} onChange={(e) => setPo({ ...po, other_charges: e.target.value })} data-testid="svc-po-other" /></div>
            <div><Label className="text-xs">Completion Date</Label><Input type="date" value={po.completion_date} onChange={(e) => setPo({ ...po, completion_date: e.target.value })} data-testid="svc-po-completion" /></div>
            <div><Label className="text-xs">Service Period From</Label><Input type="date" value={po.service_period_from} onChange={(e) => setPo({ ...po, service_period_from: e.target.value })} data-testid="svc-po-from" /></div>
            <div><Label className="text-xs">Service Period To</Label><Input type="date" value={po.service_period_to} onChange={(e) => setPo({ ...po, service_period_to: e.target.value })} data-testid="svc-po-to" /></div>
            <div><Label className="text-xs">Payment Terms</Label><Input value={po.payment_terms} onChange={(e) => setPo({ ...po, payment_terms: e.target.value })} data-testid="svc-po-payterms" /></div>
            <div className="md:col-span-3">
              <Label className="text-xs">Terms &amp; Conditions Template</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={po.terms_id}
                onChange={(e) => {
                  const t = terms.find((x) => x.id === e.target.value);
                  setPo({ ...po, terms_id: e.target.value, terms_conditions: t ? t.body : po.terms_conditions });
                }} data-testid="svc-po-terms-template">
                <option value="">— select from T&amp;C master (optional) —</option>
                {terms.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </select>
            </div>
            <div className="md:col-span-3"><TermsEditor rows={8} label="Terms & Conditions (printed on the PO PDF)" value={po.terms_conditions} onChange={(v) => setPo({ ...po, terms_conditions: v })} testid="svc-po-terms" /></div>
            <p className="md:col-span-3 text-xs text-muted-foreground">
              PO value: <b>{inr((Number(po.rate) || 0) * (Number(po.quantity) || 1) * (1 + (Number(po.tax_pct) || 0) / 100) + (Number(po.other_charges) || 0))}</b> · PO is created as Draft → Submit → Approve → Issue to vendor.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPoFor(null)}>Cancel</Button>
            <Button disabled={busy} onClick={createPo} data-testid="svc-po-create-confirm">Create PO</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_rfqs" parentId={docsFor?.id} recordTitle={docsFor?.rfq_no} testidPrefix="svc-rfq-attach" />
    </div>
  );
}
