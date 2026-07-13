/**
 * Store & Inventory · Phase 5 views
 * ==================================
 * Stock Valuation, Physical Stock Count, Consolidated Dashboard, Reconciliation Check.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, RefreshCcw, AlertTriangle, CheckCircle2, FileDown, Calculator, ScrollText, IndianRupee } from "lucide-react";

const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const today = () => new Date().toISOString().slice(0, 10);

const exportCSV = (rows, filename) => {
  if (!rows?.length) { toast.error("No data"); return; }
  const cols = Object.keys(rows[0]).filter(k => typeof rows[0][k] !== "object");
  const esc = v => v == null ? "" : (s => /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s)(String(v));
  const csv = [cols.join(","), ...rows.map(r => cols.map(c => esc(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
  toast.success(`${filename} downloaded`);
};

/* ═══ Stock Valuation ═══ */
export function StockValuationView() {
  const [d, setD] = useState(null);
  const [method, setMethod] = useState("weighted_average");

  const load = async () => {
    try { const r = await api.get(`/inv5/valuation?method=${method}`); setD(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [method]);

  if (!d) return <div className="p-4 text-sm text-slate-500">Loading…</div>;

  return (
    <Card data-testid="valuation-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Stock Valuation · <span className="text-xs text-slate-500">{d.method}</span></CardTitle>
        <div className="flex gap-2 items-center">
          <select className="h-8 px-2 border rounded-md text-sm" value={method} onChange={e => setMethod(e.target.value)} data-testid="valuation-method">
            <option value="weighted_average">Weighted Average</option>
            <option value="last_purchase">Last Purchase</option>
            <option value="standard">Standard Rate</option>
          </select>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => exportCSV(d.rows, `valuation_${method}.csv`)} data-testid="valuation-csv"><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-6 gap-2">
          {[
            { label: "Items", value: d.summary.total_items },
            { label: "Total Stock Value", value: fmt(d.summary.total_value), accent: true },
            { label: "Damaged", value: fmt(d.summary.damaged_value) },
            { label: "Scrap", value: fmt(d.summary.scrap_value) },
            { label: "In-Transit", value: fmt(d.summary.in_transit_value) },
            { label: "Grand Total", value: fmt(d.summary.grand_total), accent: true },
          ].map((t, i) => (
            <div key={i} className={`p-2 rounded-md border ${t.accent ? "bg-emerald-50 border-emerald-200" : "bg-white"}`}>
              <div className="text-[10px] uppercase text-slate-500">{t.label}</div>
              <div className="text-sm font-bold tabular-nums">{t.value}</div>
            </div>
          ))}
        </div>
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">Code</th><th className="text-left px-2 py-1">Name</th>
              <th className="text-left px-2 py-1">Category</th><th className="text-right px-2 py-1">Qty</th>
              <th className="text-right px-2 py-1">Avg Rate</th><th className="text-right px-2 py-1">Last Purchase</th>
              <th className="text-right px-2 py-1">Standard</th><th className="text-right px-2 py-1">Rate Used</th>
              <th className="text-right px-2 py-1">Value</th>
            </tr></thead>
            <tbody>
              {d.rows.map(r => (
                <tr key={r.item_id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.item_code || "—"}</td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-[10px] text-slate-500">{r.category}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.quantity}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.average_rate}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.last_purchase_rate}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.standard_rate}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold">{r.rate_used}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold">{fmt(r.stock_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══ Physical Stock Count ═══ */
export function PhysicalStockCountView() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    count_date: today(), store_id: "", attachment_url: "", remarks: "",
    lines: [{ item_id: "", physical_qty: 0, reason: "" }],
  });

  const load = async () => {
    try {
      const [r, i] = await Promise.all([api.get("/inv5/stock-counts"), api.get("/inventory")]);
      setRows(r.data); setItems(i.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    const valid = form.lines.filter(l => l.item_id);
    if (!valid.length) { toast.error("Add at least one line"); return; }
    setBusy(true);
    try {
      const r = await api.post("/inv5/stock-counts", {
        ...form,
        lines: valid.map(l => ({ item_id: l.item_id, physical_qty: Number(l.physical_qty) || 0, reason: l.reason || null })),
      });
      toast.success(`${r.data.count_no} submitted · variance ${fmt(r.data.total_variance_value)}${r.data.needs_finance_approval ? " (Finance approval)" : ""}`);
      setShowForm(false);
      setForm({ count_date: today(), store_id: "", attachment_url: "", remarks: "",
                 lines: [{ item_id: "", physical_qty: 0, reason: "" }] });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const approve = async (id) => {
    try { await api.post(`/inv5/stock-counts/${id}/approve`); toast.success("Approved — stock adjusted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
  };

  return (
    <Card data-testid="stock-count-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Physical Stock Count ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="sc-new"><Plus className="h-3.5 w-3.5 mr-1" />New Count</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="sc-form">
            <div className="grid grid-cols-3 gap-2">
              <div><Label className="text-xs">Count Date</Label><Input type="date" value={form.count_date} onChange={e => setForm({ ...form, count_date: e.target.value })} /></div>
              <div className="col-span-2"><Label className="text-xs">Attachment URL</Label><Input value={form.attachment_url} onChange={e => setForm({ ...form, attachment_url: e.target.value })} /></div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <Label className="text-xs">Lines (system qty auto-fetched on submit)</Label>
                <Button size="sm" variant="outline" onClick={() => setForm(f => ({ ...f, lines: [...f.lines, { item_id: "", physical_qty: 0, reason: "" }] }))}><Plus className="h-3 w-3 mr-1" />Add</Button>
              </div>
              <table className="w-full text-xs border rounded">
                <thead className="bg-white"><tr>
                  <th className="text-left px-1 py-1">Item</th>
                  <th className="text-right px-1 py-1">Physical Qty</th>
                  <th className="text-left px-1 py-1">Reason</th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-1 py-1">
                        <select className="w-full h-7 px-1 border rounded text-xs" value={l.item_id} onChange={e => setForm(f => ({ ...f, lines: f.lines.map((x, j) => j === i ? { ...x, item_id: e.target.value } : x) }))} data-testid={`sc-line-${i}-item`}>
                          <option value="">—</option>{items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name} (sys: {it.quantity})</option>)}
                        </select>
                      </td>
                      <td className="px-1 py-1 w-24"><Input className="h-7 text-right" type="number" value={l.physical_qty} onChange={e => setForm(f => ({ ...f, lines: f.lines.map((x, j) => j === i ? { ...x, physical_qty: e.target.value } : x) }))} data-testid={`sc-line-${i}-qty`} /></td>
                      <td className="px-1 py-1"><Input className="h-7" value={l.reason} onChange={e => setForm(f => ({ ...f, lines: f.lines.map((x, j) => j === i ? { ...x, reason: e.target.value } : x) }))} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="sc-save">Submit</Button>
            </div>
          </div>
        )}
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">No</th><th className="text-left px-2 py-1">Date</th>
              <th className="text-right px-2 py-1">Lines</th><th className="text-right px-2 py-1">Variance Value</th>
              <th className="text-center px-2 py-1">Status</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.count_no}</td>
                  <td className="px-2 py-1 font-mono">{r.count_date}</td>
                  <td className="px-2 py-1 text-right">{r.line_count}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold">{fmt(r.total_variance_value)}{r.needs_finance_approval && <span className="ml-1 text-rose-600">⚠</span>}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.status === "approved" ? "bg-emerald-100 text-emerald-800" : r.status === "rejected" ? "bg-rose-100 text-rose-800" : "bg-violet-100 text-violet-800"}`}>{r.status}</span>
                  </td>
                  <td className="px-2 py-1 text-right">{r.status === "submitted" && <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => approve(r.id)} data-testid={`sc-approve-${r.id}`}>Approve</Button>}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={6} className="text-center py-6 text-slate-400">No physical counts yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══ Phase 5 Consolidated Dashboard ═══ */
export function FinalDashboardView() {
  const [d, setD] = useState(null);
  const load = async () => {
    try { const r = await api.get("/inv5/dashboard"); setD(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  if (!d) return <div className="p-4 text-sm text-slate-500">Loading dashboard…</div>;

  const tiles = [
    ["Total Stock Value", fmt(d.total_stock_value), "emerald"],
    ["Items", d.total_items], ["Stores", d.stores_count], ["Site Stores", d.site_stores_count],
    ["Low Stock", d.low_stock_count, "amber"], ["Reorder", d.reorder_count, "amber"],
    ["Out of Stock", d.out_of_stock_count, "rose"],
    ["Pending MRs", d.pending_mr_count], ["Pending GRNs", d.pending_grn_count],
    ["Pending Inspections", d.pending_inspection_count, "amber"],
    ["In-Transit", d.pending_transfer_count, "blue"], ["Pending Opening Stock", d.pending_opening_count],
    ["Pending Damage/Loss", d.pending_damage_loss_count, "amber"],
    ["Pending Scrap", d.pending_scrap_count], ["Pending Stock Counts", d.pending_stock_count_count],
    ["In-Transit Value", fmt(d.in_transit_value)],
    ["Damaged Value", fmt(d.damaged_value), "rose"], ["Scrap Value", fmt(d.scrap_value), "slate"],
    ["Tools Issued", d.tools_issued_count], ["PPE Issued", d.ppe_issued_count],
    ["PPE Expiring (30d)", d.expiring_ppe_30d_count, "amber"],
    ["Pending Recovery", fmt(d.pending_recovery_value), "rose"],
    ["Consumption This Month", fmt(d.consumption_month_value), "blue"],
    ["High-Value Movements", d.high_value_movements_month, "amber"],
  ];

  return (
    <div className="space-y-4" data-testid="final-dashboard">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Store &amp; Inventory · Final Dashboard</h2>
          <p className="text-xs text-slate-500">{d.as_of?.slice(0, 16)} · powered by 5-phase Phase ladder</p>
        </div>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </div>
      <div className="grid grid-cols-6 gap-2">
        {tiles.map(([label, value, accent], i) => {
          const cls = {
            emerald: "bg-emerald-50 border-emerald-200 text-emerald-900",
            amber: "bg-amber-50 border-amber-200 text-amber-900",
            rose: "bg-rose-50 border-rose-200 text-rose-900",
            blue: "bg-blue-50 border-blue-200 text-blue-900",
            slate: "bg-slate-50 border-slate-200",
          }[accent] || "bg-white border-slate-200";
          return (
            <div key={i} className={`p-2 rounded-md border ${cls}`}>
              <div className="text-[10px] uppercase text-slate-500">{label}</div>
              <div className="text-base font-bold tabular-nums">{value}</div>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Top Consumed (30d)</CardTitle></CardHeader><CardContent>
          <ul className="text-xs space-y-1.5">
            {(d.top_consumed || []).map((t, i) => (
              <li key={i} className="flex justify-between border-b pb-1"><span>{t.name}</span><span className="font-semibold">{t.total}</span></li>
            ))}
            {!d.top_consumed?.length && <li className="text-slate-400">No outward txns this month.</li>}
          </ul></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Recent Transactions</CardTitle></CardHeader><CardContent>
          <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto">
            {(d.recent_transactions || []).map(t => (
              <li key={t.id} className="flex justify-between border-b pb-1">
                <span><span className="capitalize">{t.txn_type}</span> · {t.item_name}</span>
                <span className="text-slate-500">{t.quantity} · {(t.created_at || "").slice(5, 10)}</span>
              </li>
            ))}
            {!d.recent_transactions?.length && <li className="text-slate-400">No recent activity.</li>}
          </ul></CardContent></Card>
      </div>
    </div>
  );
}

/* ═══ Reconciliation Check (auditor) ═══ */
export function ReconcileCheckView() {
  const [d, setD] = useState(null);
  const load = async () => {
    try { const r = await api.get("/inv5/reconcile-check"); setD(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  if (!d) return <div className="p-4 text-sm text-slate-500">Running reconciliation…</div>;

  return (
    <Card data-testid="reconcile-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Stock Ledger ⇄ Balance Reconciliation</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Re-run</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className={`p-4 border rounded-md ${d.drift_count === 0 ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`}>
          <div className="flex items-center gap-2">
            {d.drift_count === 0 ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <AlertTriangle className="h-5 w-5 text-rose-600" />}
            <span className="font-semibold">
              {d.drift_count === 0
                ? `All ${d.checked_items} items reconcile — stock ledger and balance match.`
                : `${d.drift_count} item(s) drift detected out of ${d.checked_items} checked. Investigate immediately.`}
            </span>
          </div>
        </div>
        {d.drifts?.length > 0 && (
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-50"><tr>
                <th className="text-left px-2 py-1">Code</th><th className="text-left px-2 py-1">Item</th>
                <th className="text-right px-2 py-1">Ledger Sum</th><th className="text-right px-2 py-1">Inventory Qty</th>
                <th className="text-right px-2 py-1">Drift</th>
              </tr></thead>
              <tbody>
                {d.drifts.map(r => (
                  <tr key={r.item_id} className="border-t bg-rose-50/30">
                    <td className="px-2 py-1 font-mono">{r.item_code}</td>
                    <td className="px-2 py-1">{r.item_name}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.ledger_sum}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.inventory_qty}</td>
                    <td className="px-2 py-1 text-right tabular-nums text-rose-700 font-semibold">{r.drift}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
