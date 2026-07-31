import { useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, BookOpenText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";

const fmtW = (kg) => Number(kg || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 });

export default function ScaffoldingLedger({ bump, locations, items }) {
  const [locId, setLocId] = useState("");
  const [statement, setStatement] = useState(null);
  const [ledgerItem, setLedgerItem] = useState("");
  const [ledger, setLedger] = useState(null);

  useEffect(() => {
    if (!locId) { setStatement(null); return; }
    api.get("/scaffolding/location-statement", { params: { location_id: locId } })
      .then((r) => setStatement(r.data)).catch(() => toast.error("Failed to load statement"));
  }, [locId, bump]);

  useEffect(() => {
    if (!ledgerItem) { setLedger(null); return; }
    const params = { item_id: ledgerItem };
    if (locId) params.location_id = locId;
    api.get("/scaffolding/item-ledger", { params })
      .then((r) => setLedger(r.data)).catch(() => toast.error("Failed to load ledger"));
  }, [ledgerItem, locId, bump]);

  return (
    <div className="space-y-4" data-testid="scaf-ledger-tab">
      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-2">
            <BookOpenText className="h-3 w-3" /> Location Material Statement (challan-based)
          </div>
          <select value={locId} onChange={(e) => { setLocId(e.target.value); setLedgerItem(""); }}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs ml-auto" data-testid="scaf-ledger-location">
            <option value="">— select location / project —</option>
            {locations.filter((l) => l.type === "project").map((l) => <option key={l.id} value={l.id}>🏗 {l.name}</option>)}
            {locations.filter((l) => l.type === "store").map((l) => <option key={l.id} value={l.id}>🏬 {l.name}</option>)}
          </select>
        </div>
        {!locId && <div className="p-8 text-center text-sm text-muted-foreground">Pick a location to see its challan-wise material In / Out summary and current holding.</div>}
        {locId && statement && (
          <Table>
            <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-[10px] uppercase tracking-wider">Component</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">In (Received)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">Out (Dispatched)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">Current Stock</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">Stock Wt (kg)</TableHead>
              <TableHead className="text-right"></TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {statement.items.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No challan movements or stock at this location yet.</TableCell></TableRow>
              )}
              {statement.items.map((b) => (
                <TableRow key={b.item_id} data-testid={`scaf-statement-row-${b.item_id}`}
                  className={ledgerItem === b.item_id ? "bg-primary/5" : ""}>
                  <TableCell>
                    <div className="font-semibold text-sm">{b.item_name}</div>
                    <div className="text-[10px] text-muted-foreground font-mono-data">{b.item_code} · {b.unit}{b.unit_weight_kg ? ` · ${b.unit_weight_kg} kg/u` : ""}</div>
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm text-emerald-700">
                    {b.in_qty || "—"}{b.in_challans ? <span className="text-[10px] text-muted-foreground"> ({b.in_challans} ch)</span> : null}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm text-rose-700">
                    {b.out_qty || "—"}{b.out_challans ? <span className="text-[10px] text-muted-foreground"> ({b.out_challans} ch)</span> : null}
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold">{b.current_stock}</TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm">{b.stock_weight_kg ? fmtW(b.stock_weight_kg) : "—"}</TableCell>
                  <TableCell className="text-right">
                    <button className="text-xs text-primary underline underline-offset-2"
                      onClick={() => setLedgerItem(ledgerItem === b.item_id ? "" : b.item_id)}
                      data-testid={`scaf-statement-ledger-${b.item_id}`}>
                      {ledgerItem === b.item_id ? "Hide Ledger" : "Challan Ledger"}
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {statement.items.length > 0 && (
                <TableRow className="bg-muted/40 hover:bg-muted/40 font-bold" data-testid="scaf-statement-totals">
                  <TableCell className="text-[10px] uppercase tracking-wider">Totals</TableCell>
                  <TableCell className="text-right font-mono-data tabular">{statement.totals.in_qty}</TableCell>
                  <TableCell className="text-right font-mono-data tabular">{statement.totals.out_qty}</TableCell>
                  <TableCell className="text-right font-mono-data tabular">{statement.totals.current_stock}</TableCell>
                  <TableCell className="text-right font-mono-data tabular">{fmtW(statement.totals.stock_weight_kg)}</TableCell>
                  <TableCell></TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Component Challan-wise In / Out Ledger</div>
          <select value={ledgerItem} onChange={(e) => setLedgerItem(e.target.value)}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs ml-auto" data-testid="scaf-ledger-item">
            <option value="">— select component —</option>
            {items.map((i) => <option key={i.id} value={i.id}>{i.name}{i.size ? ` (${i.size})` : ""} · {i.code}</option>)}
          </select>
        </div>
        {!ledgerItem && <div className="p-8 text-center text-sm text-muted-foreground">Pick a component (or click "Challan Ledger" above) to see its movement history. Location filter applies if selected.</div>}
        {ledgerItem && ledger && (
          <Table>
            <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Out Challan</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">In Challan</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Route</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-right">Qty</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Direction</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {ledger.rows.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No challan movements for this component{locId ? " at the selected location" : ""}.</TableCell></TableRow>
              )}
              {ledger.rows.map((r) => (
                <TableRow key={`${r.challan_no}-${r.date}`} data-testid={`scaf-ledger-row-${r.challan_no}`}>
                  <TableCell className="text-xs">{r.date}</TableCell>
                  <TableCell className="font-mono-data text-xs font-bold">{r.challan_no}</TableCell>
                  <TableCell className="font-mono-data text-xs text-emerald-700">{r.in_challan_no || "—"}</TableCell>
                  <TableCell className="text-xs">{r.from_location} → {r.to_location}</TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold">{r.quantity} {r.unit}</TableCell>
                  <TableCell>
                    {r.direction === "in" && <Badge variant="outline" className="rounded-sm border-emerald-300 text-emerald-800 bg-emerald-50"><ArrowDownToLine className="h-3 w-3 mr-1" /> IN</Badge>}
                    {r.direction === "out" && <Badge variant="outline" className="rounded-sm border-rose-300 text-rose-800 bg-rose-50"><ArrowUpFromLine className="h-3 w-3 mr-1" /> OUT</Badge>}
                    {r.direction === "in_transit" && <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">IN TRANSIT</Badge>}
                    {!r.direction && "—"}
                  </TableCell>
                  <TableCell className="text-xs uppercase">{r.status}</TableCell>
                </TableRow>
              ))}
              {ledger.rows.length > 0 && (
                <TableRow className="bg-muted/40 hover:bg-muted/40 font-bold">
                  <TableCell colSpan={4} className="text-[10px] uppercase tracking-wider">Total moved ({ledger.rows.length} challans)</TableCell>
                  <TableCell className="text-right font-mono-data tabular">{ledger.total_moved}</TableCell>
                  <TableCell colSpan={2}></TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
