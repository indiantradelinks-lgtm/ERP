import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { inr, dt } from "./shared";

const num = (v) => (v === "" || v == null ? 0 : Number(v) || 0);

const blank = (row) => ({
  vendor_id: row?.vendor_id || "", ref_po_id: row?.ref_po_id || "", project_code: row?.project_code || "", project_name: row?.project_name || "",
  service_period: row?.service_period || new Date().toISOString().slice(0, 7), description: row?.description || "",
  vendor_invoice_no: row?.vendor_invoice_no || "", invoice_date: row?.invoice_date || new Date().toISOString().slice(0, 10),
  invoice_amount: row?.invoice_amount ?? "", tax_amount: row?.tax_amount ?? "", other_charges: row?.other_charges ?? "", tds_amount: row?.tds_amount ?? "",
  payment_amount: row?.payment_amount ?? "", due_date: row?.due_date || "", remarks: row?.remarks || "",
});

export default function DirectPaymentForm({ row, vendors, onClose, onSaved }) {
  const [f, setF] = useState(blank(row));
  const [summary, setSummary] = useState(null);
  const [vq, setVq] = useState("");
  const [payTouched, setPayTouched] = useState(!!row);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const net = useMemo(() => Math.round((num(f.invoice_amount) + num(f.tax_amount) + num(f.other_charges) - num(f.tds_amount)) * 100) / 100, [f]);
  useEffect(() => { if (!payTouched) setF((s) => ({ ...s, payment_amount: net > 0 ? net : "" })); }, [net, payTouched]);

  useEffect(() => {
    if (!f.vendor_id) { setSummary(null); return; }
    api.get(`/service-direct-payments/vendors/${f.vendor_id}/summary`).then(({ data }) => {
      setSummary(data);
      if (!row && data.last_po) {
        setF((s) => ({ ...s, ref_po_id: s.ref_po_id || data.last_po.id,
          project_code: s.project_code || data.last_po.project_code || "", project_name: s.project_name || data.last_po.project_name || "" }));
      }
    }).catch((e) => { setSummary(null); toast.error(apiErrorMessage(e)); });
  }, [f.vendor_id, row]);

  const filteredVendors = useMemo(() => vendors.filter((v) => !vq || `${v.name} ${v.code || ""}`.toLowerCase().includes(vq.toLowerCase())), [vendors, vq]);
  const lastPaid = summary?.last_paid_amount;
  const exceeds = lastPaid && num(f.payment_amount) > lastPaid;

  const save = async () => {
    if (!f.vendor_id) { toast.error("Select a vendor"); return; }
    if (num(f.invoice_amount) <= 0) { toast.error("Invoice amount must be > 0"); return; }
    setBusy(true);
    try {
      const body = { ...f, ref_po_id: f.ref_po_id || null, invoice_amount: num(f.invoice_amount), tax_amount: num(f.tax_amount),
        other_charges: num(f.other_charges), tds_amount: num(f.tds_amount), payment_amount: num(f.payment_amount) || null };
      const r = row ? await api.put(`/service-direct-payments/${row.id}`, body) : await api.post("/service-direct-payments", body);
      toast.success(`${r.data.dp_no} ${row ? "updated" : "raised — awaiting Super Admin approval"}${r.data.warnings?.length ? ` (warning: ${r.data.warnings[0]})` : ""}`);
      onSaved(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-dp-form-dialog">
        <DialogHeader><DialogTitle>{row ? `Edit ${row.dp_no}` : "New Direct Payment Request"}</DialogTitle></DialogHeader>
        <div className="grid md:grid-cols-2 gap-3 text-sm">
          <div className="md:col-span-2">
            <Label className="text-xs">Vendor (already paid through the Service workflow) *</Label>
            {!row && <Input className="h-8 mb-1" placeholder="Search vendor…" value={vq} onChange={(e) => setVq(e.target.value)} data-testid="svc-dp-vendor-search" />}
            <select className="h-9 border rounded-sm px-2 w-full" value={f.vendor_id} onChange={set("vendor_id")} disabled={!!row} data-testid="svc-dp-vendor">
              <option value="">Select vendor</option>
              {filteredVendors.map((v) => <option key={v.id} value={v.id}>{v.name}{v.code ? ` (${v.code})` : ""}</option>)}
            </select>
          </div>

          {summary && (
            <div className="md:col-span-2 border rounded-sm bg-slate-50 p-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs" data-testid="svc-dp-vendor-summary">
              <div><span className="text-muted-foreground block">GSTIN</span>{summary.vendor.gst || "—"}</div>
              <div><span className="text-muted-foreground block">Last paid</span>{lastPaid ? inr(lastPaid) : "—"} {summary.last_paid_invoice ? <span className="text-muted-foreground">({summary.last_paid_invoice.inv_no})</span> : ""}</div>
              <div><span className="text-muted-foreground block">Service invoices paid</span>{summary.service_invoices_paid} · {inr(summary.service_invoices_total)}</div>
              <div><span className="text-muted-foreground block">Direct payments paid</span>{summary.direct_payments_paid} · {inr(summary.direct_payments_total)}</div>
              <div className="col-span-2 md:col-span-4"><span className="text-muted-foreground">Bank: </span>{(summary.vendor.bank_accounts || [])[0] ? `${summary.vendor.bank_accounts[0].bank_name || ""} · ${summary.vendor.bank_accounts[0].account_no || summary.vendor.bank_accounts[0].account_number || ""} · ${summary.vendor.bank_accounts[0].ifsc || ""}` : "no bank account on Vendor Master — Accounts will need it before payment"}</div>
              {summary.open_direct_payments > 0 && <div className="col-span-2 md:col-span-4 text-amber-700">{summary.open_direct_payments} open Direct Payment request(s) already exist for this vendor</div>}
            </div>
          )}

          <div>
            <Label className="text-xs">Reference Service PO (optional)</Label>
            <select className="h-9 border rounded-sm px-2 w-full" value={f.ref_po_id} onChange={(e) => {
              const po = (summary?.pos || []).find((p) => p.id === e.target.value);
              setF((s) => ({ ...s, ref_po_id: e.target.value, project_code: po?.project_code || s.project_code, project_name: po?.project_name || s.project_name }));
            }} data-testid="svc-dp-ref-po">
              <option value="">No PO link</option>
              {(summary?.pos || []).map((p) => <option key={p.id} value={p.id}>{p.po_no} · {p.sr_no} · {p.project_code || "—"} · {inr(p.total_value)}</option>)}
            </select>
          </div>
          <div><Label className="text-xs">Service period (month)</Label><Input type="month" value={f.service_period} onChange={set("service_period")} data-testid="svc-dp-period" /></div>
          <div><Label className="text-xs">Project code</Label><Input value={f.project_code} onChange={set("project_code")} data-testid="svc-dp-project-code" /></div>
          <div><Label className="text-xs">Project name</Label><Input value={f.project_name} onChange={set("project_name")} data-testid="svc-dp-project-name" /></div>
          <div><Label className="text-xs">Vendor invoice no</Label><Input value={f.vendor_invoice_no} onChange={set("vendor_invoice_no")} data-testid="svc-dp-invoice-no" /></div>
          <div><Label className="text-xs">Invoice date</Label><Input type="date" value={f.invoice_date} onChange={set("invoice_date")} data-testid="svc-dp-invoice-date" /></div>
          <div><Label className="text-xs">Invoice amount *</Label><Input type="number" min="0" step="0.01" value={f.invoice_amount} onChange={set("invoice_amount")} data-testid="svc-dp-invoice-amount" /></div>
          <div><Label className="text-xs">GST / tax</Label><Input type="number" min="0" step="0.01" value={f.tax_amount} onChange={set("tax_amount")} data-testid="svc-dp-tax" /></div>
          <div><Label className="text-xs">Other charges</Label><Input type="number" min="0" step="0.01" value={f.other_charges} onChange={set("other_charges")} data-testid="svc-dp-other" /></div>
          <div><Label className="text-xs">TDS</Label><Input type="number" min="0" step="0.01" value={f.tds_amount} onChange={set("tds_amount")} data-testid="svc-dp-tds" /></div>
          <div><Label className="text-xs">Net payable</Label><div className="h-9 flex items-center font-semibold" data-testid="svc-dp-net">{inr(net)}</div></div>
          <div><Label className="text-xs">Payment amount * (≤ net)</Label><Input type="number" min="0" step="0.01" value={f.payment_amount} onChange={(e) => { setPayTouched(true); set("payment_amount")(e); }} data-testid="svc-dp-payment-amount" /></div>
          <div><Label className="text-xs">Due date</Label><Input type="date" value={f.due_date} onChange={set("due_date")} data-testid="svc-dp-due" /></div>
          <div className="md:col-span-2"><Label className="text-xs">Description</Label><Input value={f.description} onChange={set("description")} placeholder="e.g. Transportation services — Nov 2026" data-testid="svc-dp-description" /></div>
          <div className="md:col-span-2"><Label className="text-xs">Remarks</Label><Textarea rows={2} value={f.remarks} onChange={set("remarks")} data-testid="svc-dp-remarks" /></div>
          {exceeds ? (
            <div className="md:col-span-2 flex gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-2" data-testid="svc-dp-exceeds-warning">
              <AlertTriangle className="h-4 w-4 shrink-0" /> Payment {inr(num(f.payment_amount))} exceeds the vendor's last paid amount {inr(lastPaid)} — you can still submit; the Super Admin will see this warning.
            </div>
          ) : null}
          <p className="md:col-span-2 text-[11px] text-muted-foreground">Supporting documents are optional — attach them from the paperclip after saving. Previous-month documents are not required. {summary?.last_po ? `Last PO ${summary.last_po.po_no} (${dt(summary.last_po.created_at)}).` : ""}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy} onClick={save} data-testid="svc-dp-save">{row ? "Save changes" : "Raise for Super Admin approval"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
