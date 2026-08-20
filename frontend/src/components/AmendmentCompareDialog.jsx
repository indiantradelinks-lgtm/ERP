import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const inr = (n) => (n == null ? "—" : "₹ " + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const eq = (a, b) => {
  const na = Number(a), nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb) && a !== "" && b !== "" && a != null && b != null) return Math.abs(na - nb) < 1e-6;
  return (a || "") === (b || "");
};

const DiffCell = ({ oldVal, newVal, fmt }) => {
  const changed = !eq(oldVal, newVal);
  const f = fmt || ((v) => (v == null || v === "" ? "—" : String(v)));
  if (!changed) return <span className="text-muted-foreground">{f(newVal)}</span>;
  return (
    <span className="inline-flex items-center gap-1">
      <span className="line-through text-red-500/80">{f(oldVal)}</span>
      <span>→</span>
      <span className="font-semibold text-emerald-700 bg-emerald-50 px-1 rounded-sm">{f(newVal)}</span>
    </span>
  );
};

export const AmendmentCompareDialog = ({ po, onClose }) => {
  const versions = useMemo(() => {
    const list = (po.amendments || []).filter((a) => a.before).map((a) => ({
      label: `Rev ${a.revision} — ${a.reason || "amendment"}`,
      before: a.before, after: a.after || {}, meta: a,
    }));
    if (po.status === "amendment_in_progress" && po.pre_amendment_snapshot) {
      const cur = {};
      ["items", "amount", "gst_amount", "total", "gst_type", "delivery_terms", "special_terms", "other_terms"].forEach((k) => { cur[k] = po[k]; });
      list.push({ label: `In-progress edit (Rev ${(Number(po.revision) || 0) + 1} draft)`, before: po.pre_amendment_snapshot, after: cur, meta: { reason: po.amendment_reason } });
    }
    return list;
  }, [po]);
  const [sel, setSel] = useState(versions.length - 1);
  const v = versions[sel];

  if (!v) {
    return (
      <Dialog open onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-md rounded-sm" data-testid="po-compare-dialog">
          <DialogHeader><DialogTitle className="font-display">Amendment Compare — {po.po_number}</DialogTitle>
            <DialogDescription>No before/after snapshot is available for this PO's amendments.</DialogDescription></DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  const bItems = v.before.items || [];
  const aItems = v.after.items || [];
  const rowCount = Math.max(bItems.length, aItems.length);
  const headerFields = [
    ["gst_type", "GST Type", (x) => (x === "igst" ? "IGST" : x ? "CGST + SGST" : "—")],
    ["delivery_terms", "Delivery Terms", null],
    ["special_terms", "Special Terms", null],
    ["other_terms", "Other Terms", null],
    ["amount", "Sub-total", inr],
    ["gst_amount", "Total GST", inr],
    ["total", "Grand Total", inr],
  ];

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="po-compare-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Amendment Compare — {po.po_number}</DialogTitle>
          <DialogDescription>Old vs new values. <span className="line-through text-red-500/80">old</span> → <span className="text-emerald-700 font-medium">new</span>; unchanged values shown in grey.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3 text-sm">
          {versions.length > 1 && (
            <select value={sel} onChange={(e) => setSel(Number(e.target.value))} className="h-8 rounded-sm border bg-background px-2 text-sm" data-testid="po-compare-rev-select">
              {versions.map((x, i) => <option key={i} value={i}>{x.label}</option>)}
            </select>
          )}
          {versions.length === 1 && <span className="font-medium">{v.label}</span>}
          {v.meta?.amended_by && <span className="text-xs text-muted-foreground">by {v.meta.amended_by} · {String(v.meta.at || "").slice(0, 10)}</span>}
        </div>
        {v.meta?.reason && <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-sm px-2 py-1.5" data-testid="po-compare-reason"><b>Reason:</b> {v.meta.reason}</div>}

        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="po-compare-items-table">
            <thead>
              <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-2">#</th><th className="py-2 pr-2">Item</th>
                <th className="py-2 pr-2 text-right">Qty</th><th className="py-2 pr-2 text-right">Rate</th>
                <th className="py-2 pr-2 text-right">GST %</th><th className="py-2 pr-2">Make / Specs</th>
                <th className="py-2 text-right">Line Total</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rowCount }).map((_, i) => {
                const b = bItems[i], a = aItems[i];
                if (!b) return (
                  <tr key={i} className="border-b bg-emerald-50/50" data-testid={`po-compare-row-${i}`}>
                    <td className="py-2 pr-2">{i + 1}</td>
                    <td className="py-2 pr-2 font-medium">{a.name} <span className="text-[10px] uppercase bg-emerald-100 text-emerald-700 px-1 rounded-sm">Added</span></td>
                    <td className="py-2 pr-2 text-right">{a.quantity}</td><td className="py-2 pr-2 text-right">{inr(a.rate)}</td>
                    <td className="py-2 pr-2 text-right">{a.gst_pct}%</td><td className="py-2 pr-2">{[a.make, a.technical_specs].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="py-2 text-right">{inr(a.line_total)}</td>
                  </tr>
                );
                if (!a) return (
                  <tr key={i} className="border-b bg-red-50/50 opacity-70" data-testid={`po-compare-row-${i}`}>
                    <td className="py-2 pr-2">{i + 1}</td>
                    <td className="py-2 pr-2 font-medium line-through">{b.name} <span className="text-[10px] uppercase bg-red-100 text-red-700 px-1 rounded-sm no-underline">Removed</span></td>
                    <td className="py-2 pr-2 text-right">{b.quantity}</td><td className="py-2 pr-2 text-right">{inr(b.rate)}</td>
                    <td className="py-2 pr-2 text-right">{b.gst_pct}%</td><td className="py-2 pr-2">{[b.make, b.technical_specs].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="py-2 text-right">{inr(b.line_total)}</td>
                  </tr>
                );
                return (
                  <tr key={i} className="border-b last:border-0" data-testid={`po-compare-row-${i}`}>
                    <td className="py-2 pr-2 text-muted-foreground">{i + 1}</td>
                    <td className="py-2 pr-2 font-medium"><DiffCell oldVal={b.name} newVal={a.name} /></td>
                    <td className="py-2 pr-2 text-right"><DiffCell oldVal={b.quantity} newVal={a.quantity} /></td>
                    <td className="py-2 pr-2 text-right"><DiffCell oldVal={b.rate} newVal={a.rate} fmt={inr} /></td>
                    <td className="py-2 pr-2 text-right"><DiffCell oldVal={b.gst_pct} newVal={a.gst_pct} fmt={(x) => `${x ?? "—"}%`} /></td>
                    <td className="py-2 pr-2"><DiffCell oldVal={[b.make, b.technical_specs].filter(Boolean).join(" · ")} newVal={[a.make, a.technical_specs].filter(Boolean).join(" · ")} /></td>
                    <td className="py-2 text-right"><DiffCell oldVal={b.line_total} newVal={a.line_total} fmt={inr} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1 text-sm border-t pt-3" data-testid="po-compare-header-fields">
          {headerFields.map(([k, label, fmt]) => (
            <div key={k} className="flex justify-between gap-3 py-0.5">
              <span className="text-muted-foreground">{label}</span>
              <span className="text-right"><DiffCell oldVal={v.before[k]} newVal={v.after[k]} fmt={fmt || undefined} /></span>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AmendmentCompareDialog;
