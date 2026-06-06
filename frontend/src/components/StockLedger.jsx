import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { BookOpenCheck, Download } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const KIND_COLOR = {
  inward: "bg-emerald-100 text-emerald-700",
  outward: "bg-rose-100 text-rose-700",
  transfer: "bg-blue-100 text-blue-700",
  "return": "bg-amber-100 text-amber-700",
  scrap: "bg-slate-200 text-slate-700",
};

export default function StockLedger({ itemId, itemName, open, onOpenChange }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!itemId) return;
    setBusy(true);
    const params = new URLSearchParams();
    if (from) params.set("from_date", from);
    if (to) params.set("to_date", to);
    try {
      const { data } = await api.get(`/store/ledger/${itemId}?${params}`);
      setData(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (open && itemId) load(); /* eslint-disable-line */ }, [open, itemId]);

  const exportCsv = () => {
    if (!data?.rows?.length) { toast.error("No rows"); return; }
    const keys = ["at", "txn_no", "txn_type", "qty", "balance_after", "received_from", "issued_to", "project", "by", "ref_no"];
    const lines = [keys.join(","), ...data.rows.map((r) => keys.map((k) => (r[k] ?? "")).join(","))];
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `ledger-${itemName || itemId}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="stock-ledger">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpenCheck className="h-5 w-5 text-primary" />
            Stock Ledger — {itemName || itemId}
          </DialogTitle>
          <DialogDescription>Opening · receipt · issue · return · closing for the selected date window.</DialogDescription>
        </DialogHeader>

        <div className="flex items-end gap-3 flex-wrap mb-3">
          <div><label className="text-xs">From</label><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-36" /></div>
          <div><label className="text-xs">To</label><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-36" /></div>
          <Button onClick={load} disabled={busy} variant="outline">Apply</Button>
          <Button onClick={exportCsv} variant="outline"><Download className="h-4 w-4 mr-1.5" /> CSV</Button>
        </div>

        {data && (
          <>
            <div className="grid grid-cols-6 gap-2 mb-4">
              <Tile label="Opening" value={data.opening} />
              <Tile label="Receipts" value={data.totals.receipt} tone="bg-emerald-50 border-emerald-200" />
              <Tile label="Issues" value={data.totals.issue} tone="bg-rose-50 border-rose-200" />
              <Tile label="Returns" value={data.totals.return} tone="bg-amber-50 border-amber-200" />
              <Tile label="Transfers" value={data.totals.transfer} tone="bg-blue-50 border-blue-200" />
              <Tile label="Closing" value={data.closing} tone="bg-primary/10 border-primary/30 font-bold" />
            </div>
            <div className="border rounded-sm overflow-x-auto max-h-[50vh]">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr>
                    <th className="text-left p-2">Date</th>
                    <th className="text-left p-2">Txn #</th>
                    <th className="text-left p-2">Type</th>
                    <th className="text-right p-2">Qty</th>
                    <th className="text-right p-2">Balance</th>
                    <th className="text-left p-2">Counter-party / Project</th>
                    <th className="text-left p-2">By</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.length === 0 && (
                    <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">No transactions in this window.</td></tr>
                  )}
                  {data.rows.map((r, i) => (
                    <tr key={i} className="border-t hover:bg-slate-50">
                      <td className="p-2 font-mono">{(r.at || "").slice(0, 16).replace("T", " ")}</td>
                      <td className="p-2 font-mono">{r.txn_no || "—"}</td>
                      <td className="p-2"><Badge className={KIND_COLOR[r.txn_type] || "bg-slate-100"}>{r.txn_type}</Badge></td>
                      <td className="p-2 text-right font-mono">{r.delta > 0 ? `+${r.qty}` : `-${r.qty}`}</td>
                      <td className="p-2 text-right font-mono font-semibold">{r.balance_after}</td>
                      <td className="p-2 text-xs">{r.received_from || r.issued_to || r.project || "—"}</td>
                      <td className="p-2 text-xs">{r.by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Tile({ label, value, tone = "bg-slate-50 border-slate-200" }) {
  return (
    <div className={`p-2 border rounded-sm ${tone}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-lg font-mono">{value}</div>
    </div>
  );
}
