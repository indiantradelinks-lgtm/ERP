/**
 * Service PO — Edit Mode (draft only).
 * Add / modify line items, pick Terms & Conditions from the master, set payment
 * terms & dates, then save. Everything saved here flows into the PO PDF.
 */
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Printer, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage, API } from "@/lib/api";
import { inr } from "./shared";

const blankLine = () => ({ description: "", unit: "Lot", quantity: 1, rate: 0, tax_pct: 18, remarks: "" });
const n = (v) => Number(v || 0);

export default function PoEditDialog({ po, open, onOpenChange, onSaved }) {
  const [lines, setLines] = useState([blankLine()]);
  const [h, setH] = useState({});
  const [terms, setTerms] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !po) return;
    const existing = (po.line_items || []).length
      ? po.line_items.map((l) => ({ description: l.description || "", unit: l.unit || "Lot", quantity: l.quantity ?? 1, rate: l.rate ?? 0, tax_pct: l.tax_pct ?? 18, remarks: l.remarks || "" }))
      : [{ description: po.service_details || po.scope_of_work || "Service", unit: po.unit || "Lot", quantity: po.quantity ?? 1, rate: po.rate ?? 0, tax_pct: po.tax_pct ?? 18, remarks: "" }];
    setLines(existing);
    setH({
      scope_of_work: po.scope_of_work || "", service_details: po.service_details || "",
      site_location: po.site_location || "", other_charges: po.other_charges || 0,
      service_period_from: po.service_period_from || "", service_period_to: po.service_period_to || "",
      completion_date: po.completion_date || "", payment_terms: po.payment_terms || "",
      terms_id: po.terms_id || "", terms_conditions: po.terms_conditions || "",
    });
    api.get("/service-workflow/terms?active=true").then((r) => setTerms(r.data)).catch(() => setTerms([]));
  }, [open, po]);

  const totals = useMemo(() => {
    let sub = 0, tax = 0;
    lines.forEach((l) => {
      const amt = n(l.quantity) * n(l.rate);
      sub += amt; tax += (amt * n(l.tax_pct)) / 100;
    });
    const other = n(h.other_charges);
    return { sub: +sub.toFixed(2), tax: +tax.toFixed(2), other, total: +(sub + tax + other).toFixed(2) };
  }, [lines, h.other_charges]);

  const setLine = (i, patch) => setLines((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  const pickTerms = (id) => {
    const t = terms.find((x) => x.id === id);
    setH((s) => ({ ...s, terms_id: id, terms_conditions: t ? t.body : "" }));
  };

  const save = async (thenPdf) => {
    setSaving(true);
    try {
      await api.put(`/service-workflow/pos/${po.id}`, {
        line_items: lines.map((l) => ({ ...l, quantity: n(l.quantity), rate: n(l.rate), tax_pct: n(l.tax_pct) })),
        ...h, other_charges: n(h.other_charges),
      });
      toast.success(`${po.po_no} updated — total ${inr(totals.total)}`);
      onSaved?.();
      if (thenPdf) window.open(`${API}/service-workflow/pos/${po.id}/pdf`, "_blank");
      else onOpenChange(false);
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[92vh] overflow-y-auto" data-testid="svc-po-edit-dialog">
        <DialogHeader>
          <DialogTitle>Edit PO {po?.po_no} — {po?.vendor_name}</DialogTitle>
          <p className="text-xs text-muted-foreground">
            Draft PO · {po?.sr_no} / {po?.rfq_no}. Add or modify line items and select Terms &amp; Conditions.
            Every change here appears on the PO PDF.
          </p>
        </DialogHeader>

        <div className="space-y-4">
          {/* Line items */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs font-semibold uppercase">Line Items</Label>
              <Button variant="outline" size="sm" className="h-7 text-xs"
                onClick={() => setLines((ls) => [...ls, blankLine()])} data-testid="svc-po-edit-add-line">
                <Plus className="h-3 w-3 mr-1" /> Add Line Item
              </Button>
            </div>
            <div className="border rounded-sm overflow-x-auto">
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="w-8">#</TableHead>
                  <TableHead className="min-w-[220px]">Service Description *</TableHead>
                  <TableHead className="w-20">Unit</TableHead>
                  <TableHead className="w-24">Qty</TableHead>
                  <TableHead className="w-28">Rate</TableHead>
                  <TableHead className="w-20">GST %</TableHead>
                  <TableHead className="w-28 text-right">Line Total</TableHead>
                  <TableHead className="w-8"></TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {lines.map((l, i) => {
                    const amt = n(l.quantity) * n(l.rate);
                    return (
                      <TableRow key={i} data-testid={`svc-po-edit-line-${i}`}>
                        <TableCell className="text-xs text-muted-foreground">{i + 1}</TableCell>
                        <TableCell>
                          <Input className="h-8" value={l.description} placeholder="e.g. Crane hire — 20T, day shift"
                            onChange={(e) => setLine(i, { description: e.target.value })} data-testid={`svc-po-edit-desc-${i}`} />
                          <Input className="h-7 mt-1 text-xs" value={l.remarks} placeholder="Remarks (optional)"
                            onChange={(e) => setLine(i, { remarks: e.target.value })} data-testid={`svc-po-edit-remarks-${i}`} />
                        </TableCell>
                        <TableCell><Input className="h-8" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} data-testid={`svc-po-edit-unit-${i}`} /></TableCell>
                        <TableCell><Input className="h-8" type="number" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} data-testid={`svc-po-edit-qty-${i}`} /></TableCell>
                        <TableCell><Input className="h-8" type="number" value={l.rate} onChange={(e) => setLine(i, { rate: e.target.value })} data-testid={`svc-po-edit-rate-${i}`} /></TableCell>
                        <TableCell><Input className="h-8" type="number" value={l.tax_pct} onChange={(e) => setLine(i, { tax_pct: e.target.value })} data-testid={`svc-po-edit-tax-${i}`} /></TableCell>
                        <TableCell className="text-right tabular-nums text-sm" data-testid={`svc-po-edit-linetotal-${i}`}>
                          {inr(amt + (amt * n(l.tax_pct)) / 100)}
                        </TableCell>
                        <TableCell>
                          {lines.length > 1 && (
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-red-600"
                              onClick={() => setLines((ls) => ls.filter((_, k) => k !== i))} data-testid={`svc-po-edit-del-${i}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            <div className="flex flex-wrap justify-end gap-6 text-sm mt-2 tabular-nums">
              <span>Sub-total <b data-testid="svc-po-edit-subtotal">{inr(totals.sub)}</b></span>
              <span>GST <b data-testid="svc-po-edit-tax">{inr(totals.tax)}</b></span>
              <span>Other <b>{inr(totals.other)}</b></span>
              <span className="text-emerald-700">Grand Total <b data-testid="svc-po-edit-total">{inr(totals.total)}</b></span>
            </div>
          </div>

          {/* Header fields */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div><Label className="text-xs">Other Charges</Label><Input type="number" value={h.other_charges} onChange={(e) => setH({ ...h, other_charges: e.target.value })} data-testid="svc-po-edit-other" /></div>
            <div><Label className="text-xs">Service Period From</Label><Input type="date" value={h.service_period_from} onChange={(e) => setH({ ...h, service_period_from: e.target.value })} data-testid="svc-po-edit-from" /></div>
            <div><Label className="text-xs">Service Period To</Label><Input type="date" value={h.service_period_to} onChange={(e) => setH({ ...h, service_period_to: e.target.value })} data-testid="svc-po-edit-to" /></div>
            <div><Label className="text-xs">Completion Date</Label><Input type="date" value={h.completion_date} onChange={(e) => setH({ ...h, completion_date: e.target.value })} data-testid="svc-po-edit-completion" /></div>
            <div><Label className="text-xs">Site / Location</Label><Input value={h.site_location} onChange={(e) => setH({ ...h, site_location: e.target.value })} data-testid="svc-po-edit-site" /></div>
            <div><Label className="text-xs">Payment Terms</Label><Input value={h.payment_terms} placeholder="e.g. 30 days from invoice" onChange={(e) => setH({ ...h, payment_terms: e.target.value })} data-testid="svc-po-edit-payment-terms" /></div>
            <div className="md:col-span-3"><Label className="text-xs">Scope of Service</Label><Textarea rows={2} value={h.scope_of_work} onChange={(e) => setH({ ...h, scope_of_work: e.target.value })} data-testid="svc-po-edit-scope" /></div>
          </div>

          {/* Terms & Conditions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs">Terms &amp; Conditions Template</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm"
                value={h.terms_id || ""} onChange={(e) => pickTerms(e.target.value)} data-testid="svc-po-edit-terms-select">
                <option value="">— Custom / none —</option>
                {terms.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">
                Picking a template loads its clauses below — one clause per line. Edit freely before saving.
              </p>
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs">Terms &amp; Conditions (printed on the PO)</Label>
              <Textarea rows={5} value={h.terms_conditions} onChange={(e) => setH({ ...h, terms_conditions: e.target.value })}
                placeholder="One clause per line" data-testid="svc-po-edit-terms-body" />
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="svc-po-edit-cancel">Cancel</Button>
          <Button variant="outline" disabled={saving} onClick={() => save(true)} data-testid="svc-po-edit-save-pdf">
            <Printer className="h-3.5 w-3.5 mr-1" /> Save &amp; View PDF
          </Button>
          <Button disabled={saving} onClick={() => save(false)} data-testid="svc-po-edit-save">
            {saving ? "Saving…" : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
