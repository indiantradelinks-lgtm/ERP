import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Lock, Plus, X } from "lucide-react";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const GST_PRESETS = [0, 5, 12, 18, 28];
export const PO_LOCKED_STATUSES = ["pending_approval", "submitted", "approved", "sent_to_vendor", "received", "partially_received"];

export const POItemsDialog = ({ po, canWrite, onClose }) => {
  const locked = PO_LOCKED_STATUSES.includes(po.status);
  const editable = canWrite && !locked;
  const [items, setItems] = useState(() => (po.items || []).map((it) => ({ ...it, gst_pct: it.gst_pct ?? po.gst_pct ?? 18 })));
  const [gstType, setGstType] = useState(po.gst_type || "cgst_sgst");
  const [terms, setTerms] = useState({ delivery_terms: po.delivery_terms || "", special_terms: po.special_terms || "", other_terms: po.other_terms || "" });
  const [paymentTerms, setPaymentTerms] = useState(po.payment_terms || "");
  const [pcts, setPcts] = useState({ tds_pct: po.tds_pct ?? "", retention_pct: po.retention_pct ?? "", advance_pct: po.advance_pct ?? "" });
  const [saving, setSaving] = useState(false);

  const rows = useMemo(() => items.map((it) => {
    const qty = Number(it.quantity || 0);
    const rate = Number(it.rate || 0);
    const amount = qty * rate;
    const gstPct = Number(it.gst_pct || 0);
    const gstAmt = amount * gstPct / 100;
    return { ...it, qty, rate, amount, gstPct, gstAmt, lineTotal: amount + gstAmt };
  }), [items]);

  const subTotal = rows.reduce((s, r) => s + r.amount, 0);
  const gstTotal = rows.reduce((s, r) => s + r.gstAmt, 0);
  const setField = (idx, key, val) => setItems((arr) => arr.map((it, i) => (i === idx ? { ...it, [key]: val } : it)));
  const addRow = () => setItems((arr) => [...arr, { name: "", quantity: 1, rate: 0, unit: "Nos", gst_pct: 18, _new: true }]);
  const removeRow = (idx) => setItems((arr) => arr.filter((_, i) => i !== idx));

  const save = async () => {
    for (let i = 0; i < items.length; i++) {
      const name = (items[i].name || "").trim();
      if (!name) return toast.error(`Data missing: Item ${i + 1} has no name/description`);
      if (Number(items[i].quantity || 0) <= 0) return toast.error(`Data missing: '${name}' has zero quantity`);
      if (Number(items[i].rate || 0) <= 0) return toast.error(`Data missing: '${name}' has zero rate/price`);
    }
    setSaving(true);
    try {
      await api.put(`/procurement/pos/${po.id}/items`, {
        items: items.map(({ _new, ...it }) => ({ ...it, quantity: Number(it.quantity || 0), rate: Number(it.rate || 0), gst_pct: Number(it.gst_pct || 0) })),
        gst_type: gstType, ...terms, payment_terms: paymentTerms,
        tds_pct: pcts.tds_pct === "" ? null : Number(pcts.tds_pct),
        retention_pct: pcts.retention_pct === "" ? null : Number(pcts.retention_pct),
        advance_pct: pcts.advance_pct === "" ? null : Number(pcts.advance_pct),
      });
      toast.success("PO updated — totals recalculated");
      onClose(true);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to update PO"));
    } finally {
      setSaving(false);
    }
  };

  const cell = "py-2 pr-2";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-6xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="po-items-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            PO Preview & Edit — {po.po_number}{Number(po.revision) > 0 && <span className="text-xs font-normal bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded-sm">Rev {po.revision}</span>}
            {locked && <span className="inline-flex items-center gap-1 text-xs font-normal bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-sm" data-testid="po-locked-badge"><Lock className="h-3 w-3" /> Locked ({po.status})</span>}
          </DialogTitle>
          <DialogDescription>
            {editable ? "Edit qty, rate, item-wise GST, make & specs. Totals recalculate automatically." : locked ? "This PO is under approval / final-approved — raise an amendment request to modify it." : "Item-wise breakup with GST."}
          </DialogDescription>
        </DialogHeader>

        {po.status === "pending_revision" && po.reject_reason && (
          <div className="border border-red-200 bg-red-50 text-red-700 rounded-sm px-3 py-2 text-sm" data-testid="po-reject-banner">
            <b>Rejected — revision required:</b> {po.reject_reason}
          </div>
        )}
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">GST Type</div>
            {editable ? (
              <select value={gstType} onChange={(e) => setGstType(e.target.value)} className="h-8 rounded-sm border bg-background px-2 text-sm" data-testid="po-gst-type-select">
                <option value="cgst_sgst">CGST + SGST (intra-state)</option>
                <option value="igst">IGST (inter-state)</option>
              </select>
            ) : <span className="font-medium">{(po.gst_type || "cgst_sgst") === "igst" ? "IGST" : "CGST + SGST"}</span>}
          </div>
          <div className="text-muted-foreground">PR: <span className="font-medium text-foreground">{po.pr_number || "—"}</span></div>
          <div className="text-muted-foreground">Vendor: <span className="font-medium text-foreground">{po.vendor || "—"}</span></div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Payment Terms</div>
            {editable ? <Input value={paymentTerms} onChange={(e) => setPaymentTerms(e.target.value)} placeholder="e.g. 30 days credit" className="h-8 w-44 rounded-sm text-sm" data-testid="po-payment-terms-input" />
              : <span className="font-medium">{po.payment_terms || "—"}</span>}
          </div>
          {[["tds_pct", "TDS %"], ["retention_pct", "Retention %"], ["advance_pct", "Advance %"]].map(([k, label]) => (
            <div key={k}>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">{label}</div>
              {editable ? <Input type="number" min="0" max="100" step="0.1" value={pcts[k]} onChange={(e) => setPcts((p) => ({ ...p, [k]: e.target.value }))} placeholder="0" className="h-8 w-20 rounded-sm text-sm text-right" data-testid={`po-${k.replace("_", "-")}-input`} />
                : <span className="font-medium">{po[k] != null ? `${po[k]}%` : "—"}</span>}
            </div>
          ))}
        </div>

        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground py-6 text-center" data-testid="po-items-empty">
            No line items on this PO.
            {editable && <div className="mt-2"><Button size="sm" variant="outline" className="rounded-sm" onClick={addRow} data-testid="po-add-item-empty-btn"><Plus className="h-3.5 w-3.5 mr-1" /> Add Line Item</Button></div>}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="po-items-table">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className={cell}>#</th><th className={cell}>Item / Make / Specs</th><th className={`${cell} text-right`}>Qty</th><th className={cell}>Unit</th>
                  <th className={`${cell} text-right`}>Rate</th><th className={`${cell} text-right`}>Amount</th><th className={`${cell} text-right`}>GST %</th>
                  <th className={`${cell} text-right`}>GST Amt</th><th className="py-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={idx} className="border-b last:border-0 align-top" data-testid={`po-item-row-${idx}`}>
                    <td className={`${cell} text-muted-foreground`}>{idx + 1}</td>
                    <td className={cell}>
                      {r._new && editable ? (
                        <Input placeholder="Item name *" value={r.name} onChange={(e) => setField(idx, "name", e.target.value)} className="h-7 w-40 text-sm rounded-sm" data-testid={`po-item-name-${idx}`} />
                      ) : <div className="font-medium">{r.name}</div>}
                      {editable ? (
                        <div className="flex gap-1 mt-1 flex-wrap">
                          <Input placeholder="HSN/SAC" value={r.hsn_sac || ""} onChange={(e) => setField(idx, "hsn_sac", e.target.value)} className="h-6 w-20 text-xs rounded-sm" data-testid={`po-item-hsn-${idx}`} />
                          <Input placeholder="Make" value={r.make || ""} onChange={(e) => setField(idx, "make", e.target.value)} className="h-6 w-24 text-xs rounded-sm" data-testid={`po-item-make-${idx}`} />
                          <Input placeholder="Technical specs" value={r.technical_specs || ""} onChange={(e) => setField(idx, "technical_specs", e.target.value)} className="h-6 w-40 text-xs rounded-sm" data-testid={`po-item-specs-${idx}`} />
                        </div>
                      ) : (r.hsn_sac || r.make || r.technical_specs) && (
                        <div className="text-[11px] text-muted-foreground">{[r.hsn_sac && `HSN/SAC: ${r.hsn_sac}`, r.make && `Make: ${r.make}`, r.technical_specs && `Specs: ${r.technical_specs}`].filter(Boolean).join(" · ")}</div>
                      )}
                    </td>
                    <td className={`${cell} text-right`}>
                      {editable ? <Input type="number" min="0" step="any" value={r.quantity} onChange={(e) => setField(idx, "quantity", e.target.value)} className="h-7 w-20 text-right rounded-sm" data-testid={`po-item-qty-${idx}`} /> : r.qty.toLocaleString("en-IN")}
                    </td>
                    <td className={cell}>{r.unit || "Nos"}</td>
                    <td className={`${cell} text-right`}>
                      {editable ? <Input type="number" min="0" step="any" value={r.rate} onChange={(e) => setField(idx, "rate", e.target.value)} className="h-7 w-24 text-right rounded-sm" data-testid={`po-item-rate-${idx}`} /> : inr(r.rate)}
                    </td>
                    <td className={`${cell} text-right`}>{inr(r.amount)}</td>
                    <td className={`${cell} text-right`}>
                      {editable ? (
                        <div className="flex items-center justify-end gap-1">
                          <Input type="number" min="0" max="100" step="0.1" value={r.gst_pct} onChange={(e) => setField(idx, "gst_pct", e.target.value)} className="h-7 w-16 text-right rounded-sm" data-testid={`po-item-gst-input-${idx}`} />
                          <select value={GST_PRESETS.includes(Number(r.gst_pct)) ? Number(r.gst_pct) : ""} onChange={(e) => e.target.value !== "" && setField(idx, "gst_pct", Number(e.target.value))} className="h-7 rounded-sm border bg-background text-xs px-1" data-testid={`po-item-gst-preset-${idx}`}>
                            <option value="">%</option>
                            {GST_PRESETS.map((p) => <option key={p} value={p}>{p}%</option>)}
                          </select>
                        </div>
                      ) : `${Number(r.gst_pct || 0)}%`}
                    </td>
                    <td className={`${cell} text-right`} data-testid={`po-item-gst-amt-${idx}`}>{inr(r.gstAmt)}</td>
                    <td className="py-2 text-right font-medium whitespace-nowrap" data-testid={`po-item-total-${idx}`}>
                      {inr(r.lineTotal)}
                      {editable && (
                        <button type="button" onClick={() => removeRow(idx)} className="ml-1.5 text-muted-foreground hover:text-red-600 align-middle" title="Remove item" data-testid={`po-item-remove-${idx}`}>
                          <X className="h-3.5 w-3.5 inline" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="text-sm border-t">
                  <td colSpan={8} className="py-1.5 pr-2 text-right text-muted-foreground">Sub-total</td>
                  <td className="py-1.5 text-right" data-testid="po-items-subtotal">{inr(subTotal)}</td>
                </tr>
                {gstType === "igst" ? (
                  <tr className="text-sm">
                    <td colSpan={8} className="py-1 pr-2 text-right text-muted-foreground">IGST</td>
                    <td className="py-1 text-right" data-testid="po-items-igst">{inr(gstTotal)}</td>
                  </tr>
                ) : (
                  <>
                    <tr className="text-sm">
                      <td colSpan={8} className="py-1 pr-2 text-right text-muted-foreground">CGST</td>
                      <td className="py-1 text-right" data-testid="po-items-cgst">{inr(gstTotal / 2)}</td>
                    </tr>
                    <tr className="text-sm">
                      <td colSpan={8} className="py-1 pr-2 text-right text-muted-foreground">SGST</td>
                      <td className="py-1 text-right" data-testid="po-items-sgst">{inr(gstTotal / 2)}</td>
                    </tr>
                  </>
                )}
                <tr className="font-semibold">
                  <td colSpan={8} className="py-1.5 pr-2 text-right">Grand Total</td>
                  <td className="py-1.5 text-right" data-testid="po-items-grand-total">{inr(subTotal + gstTotal)}</td>
                </tr>
                {[["advance_pct", "Advance", subTotal + gstTotal], ["tds_pct", "TDS (on basic)", subTotal], ["retention_pct", "Retention", subTotal + gstTotal]].map(([k, label, base]) => {
                  const p = Number(pcts[k] || 0);
                  if (!p) return null;
                  return (
                    <tr key={k} className="text-xs text-muted-foreground">
                      <td colSpan={8} className="py-0.5 pr-2 text-right">{label} @ {p}%</td>
                      <td className="py-0.5 text-right" data-testid={`po-items-${k.replace("_pct", "")}-amount`}>{inr(base * p / 100)}</td>
                    </tr>
                  );
                })}
              </tfoot>
            </table>
          </div>
        )}

        <div className="grid sm:grid-cols-3 gap-3">
          {[["delivery_terms", "Delivery Terms"], ["special_terms", "Special Terms"], ["other_terms", "Other Terms"]].map(([k, label]) => (
            <div key={k}>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">{label}</div>
              {editable ? (
                <Textarea rows={2} value={terms[k]} onChange={(e) => setTerms((t) => ({ ...t, [k]: e.target.value }))} className="rounded-sm text-sm" data-testid={`po-${k.replace("_", "-")}-input`} />
              ) : <div className="text-sm text-muted-foreground whitespace-pre-wrap">{po[k] || "—"}</div>}
            </div>
          ))}
        </div>

        {(po.amendments || []).length > 0 && (
          <div className="border rounded-sm p-2 bg-amber-50/50" data-testid="po-amendment-history">
            <div className="text-[11px] uppercase tracking-wide text-amber-800 mb-1">Amendment History</div>
            {po.amendments.map((a, i) => (
              <div key={i} className="text-xs text-muted-foreground">Rev {a.revision}: {a.reason} — {a.amended_by}, {String(a.at || "").slice(0, 10)}</div>
            ))}
          </div>
        )}

        {editable && (
          <div className="flex justify-between items-center gap-2 pt-1">
            {rows.length > 0 ? (
              <Button size="sm" variant="outline" className="rounded-sm" onClick={addRow} data-testid="po-add-item-btn">
                <Plus className="h-3.5 w-3.5 mr-1" /> Add Item
              </Button>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="outline" className="rounded-sm" onClick={() => onClose(false)} data-testid="po-items-cancel-btn">Cancel</Button>
              <Button className="rounded-sm" onClick={save} disabled={saving || rows.length === 0} data-testid="po-items-save-btn">
                {saving && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Save & Recalculate
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default POItemsDialog;
