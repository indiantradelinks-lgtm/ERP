import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const GST_PRESETS = [0, 5, 12, 18, 28];

export const POItemsDialog = ({ po, canWrite, onClose }) => {
  const [items, setItems] = useState(() => (po.items || []).map((it) => ({ ...it, gst_pct: it.gst_pct ?? po.gst_pct ?? 18 })));
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

  const setGst = (idx, val) => setItems((arr) => arr.map((it, i) => (i === idx ? { ...it, gst_pct: val } : it)));

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/procurement/pos/${po.id}/items`, { items: items.map((it) => ({ ...it, gst_pct: Number(it.gst_pct || 0) })) });
      toast.success("PO items updated — totals recalculated");
      onClose(true);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to update PO items"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-5xl rounded-sm" data-testid="po-items-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">PO Line Items — {po.po_number}</DialogTitle>
          <DialogDescription>
            {canWrite ? "Edit GST % per item. Amounts, GST and grand total recalculate automatically." : "Item-wise breakup with GST."}
          </DialogDescription>
        </DialogHeader>
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground py-6 text-center" data-testid="po-items-empty">
            No line items on this PO (created manually without items).
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="po-items-table">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-2">#</th>
                  <th className="py-2 pr-2">Item</th>
                  <th className="py-2 pr-2 text-right">Qty</th>
                  <th className="py-2 pr-2">Unit</th>
                  <th className="py-2 pr-2 text-right">Rate</th>
                  <th className="py-2 pr-2 text-right">Amount</th>
                  <th className="py-2 pr-2 text-right">GST %</th>
                  <th className="py-2 pr-2 text-right">GST Amt</th>
                  <th className="py-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={idx} className="border-b last:border-0" data-testid={`po-item-row-${idx}`}>
                    <td className="py-2 pr-2 text-muted-foreground">{idx + 1}</td>
                    <td className="py-2 pr-2 font-medium">{r.name}{r.hsn_sac ? <div className="text-[11px] text-muted-foreground font-normal">HSN: {r.hsn_sac}</div> : null}</td>
                    <td className="py-2 pr-2 text-right">{r.qty.toLocaleString("en-IN")}</td>
                    <td className="py-2 pr-2">{r.unit || "Nos"}</td>
                    <td className="py-2 pr-2 text-right">{inr(r.rate)}</td>
                    <td className="py-2 pr-2 text-right">{inr(r.amount)}</td>
                    <td className="py-2 pr-2 text-right">
                      {canWrite ? (
                        <div className="flex items-center justify-end gap-1">
                          <Input type="number" min="0" max="100" step="0.1" value={r.gst_pct}
                            onChange={(e) => setGst(idx, e.target.value)}
                            className="h-7 w-20 text-right rounded-sm"
                            data-testid={`po-item-gst-input-${idx}`} />
                          <select value={GST_PRESETS.includes(Number(r.gst_pct)) ? Number(r.gst_pct) : ""}
                            onChange={(e) => e.target.value !== "" && setGst(idx, Number(e.target.value))}
                            className="h-7 rounded-sm border bg-background text-xs px-1"
                            data-testid={`po-item-gst-preset-${idx}`}>
                            <option value="">%</option>
                            {GST_PRESETS.map((p) => <option key={p} value={p}>{p}%</option>)}
                          </select>
                        </div>
                      ) : `${Number(r.gst_pct || 0)}%`}
                    </td>
                    <td className="py-2 pr-2 text-right" data-testid={`po-item-gst-amt-${idx}`}>{inr(r.gstAmt)}</td>
                    <td className="py-2 text-right font-medium" data-testid={`po-item-total-${idx}`}>{inr(r.lineTotal)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="text-sm border-t">
                  <td colSpan={8} className="py-1.5 pr-2 text-right text-muted-foreground">Sub-total</td>
                  <td className="py-1.5 text-right" data-testid="po-items-subtotal">{inr(subTotal)}</td>
                </tr>
                <tr className="text-sm">
                  <td colSpan={8} className="py-1.5 pr-2 text-right text-muted-foreground">Total GST</td>
                  <td className="py-1.5 text-right" data-testid="po-items-gst-total">{inr(gstTotal)}</td>
                </tr>
                <tr className="font-semibold">
                  <td colSpan={8} className="py-1.5 pr-2 text-right">Grand Total</td>
                  <td className="py-1.5 text-right" data-testid="po-items-grand-total">{inr(subTotal + gstTotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
        {canWrite && rows.length > 0 && (
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" className="rounded-sm" onClick={() => onClose(false)} data-testid="po-items-cancel-btn">Cancel</Button>
            <Button className="rounded-sm" onClick={save} disabled={saving} data-testid="po-items-save-btn">
              {saving && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Save & Recalculate
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default POItemsDialog;
