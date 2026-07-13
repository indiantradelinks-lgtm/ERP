/**
 * Store & Inventory · Phase 2 views
 * ==================================
 * Procurement / Accounts / Finance integration tiles + reports.
 * All endpoints under /api/inv2/*.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  RefreshCcw, Send, FileDown, AlertOctagon, CheckCircle2, XCircle, Clock,
  Truck, ClipboardList, FileText, IndianRupee, ArrowRight, ShoppingCart, ScrollText,
} from "lucide-react";

const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const exportCSV = (rows, filename) => {
  if (!rows?.length) { toast.error("No data to export"); return; }
  const cols = Object.keys(rows[0]).filter(k => typeof rows[0][k] !== "object");
  const esc = v => v == null ? "" : (s => /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s)(String(v));
  const csv = [cols.join(","), ...rows.map(r => cols.map(c => esc(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
  toast.success(`${filename} downloaded`);
};

/* ═══════════════════ 1. PR from Stock Shortage ═══════════════════ */
export function PRFromStockView() {
  const [suggestions, setSuggestions] = useState([]);
  const [selected, setSelected] = useState({});
  const [priority, setPriority] = useState("normal");
  const [reason, setReason] = useState("stock_below_reorder");
  const [requiredDate, setRequiredDate] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get("/inv2/stock-shortage-suggestions");
      setSuggestions(r.data.rows);
      const sel = {};
      r.data.rows.forEach(s => { sel[s.item_id] = { selected: false, qty: s.suggested_qty || 1 }; });
      setSelected(sel);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const selectedItems = useMemo(() =>
    suggestions.filter(s => selected[s.item_id]?.selected).map(s => ({
      ...s, required_qty: Number(selected[s.item_id]?.qty || s.suggested_qty || 1),
    })), [suggestions, selected]);

  const totalValue = selectedItems.reduce((a, s) => a + s.required_qty * (s.rate || 0), 0);

  const submit = async () => {
    if (!selectedItems.length) { toast.error("Select at least one item"); return; }
    setBusy(true);
    try {
      const r = await api.post("/inv2/pr-from-stock", {
        priority, reason, required_date: requiredDate || null,
        lines: selectedItems.map(s => ({
          item_id: s.item_id, required_qty: s.required_qty,
          suggested_vendor: s.vendor_name || null,
        })),
      });
      toast.success(`PR ${r.data.pr_number} created (${r.data.priority})`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "PR creation failed");
    } finally { setBusy(false); }
  };

  return (
    <Card data-testid="prfs-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Purchase Requisition from Stock Shortage</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-4 gap-2">
          <div><Label className="text-xs">Priority</Label>
            <select className="w-full h-9 px-2 border rounded-md text-sm" value={priority} onChange={e => setPriority(e.target.value)} data-testid="prfs-priority">
              <option value="normal">Normal</option><option value="urgent">Urgent</option><option value="emergency">Emergency</option>
            </select></div>
          <div><Label className="text-xs">Reason</Label>
            <select className="w-full h-9 px-2 border rounded-md text-sm" value={reason} onChange={e => setReason(e.target.value)}>
              <option value="stock_below_reorder">Below Reorder Level</option>
              <option value="reorder_level">At Reorder Level</option>
              <option value="project_requirement">Project Requirement</option>
              <option value="emergency">Emergency at Site</option>
              <option value="replacement">Damaged/Lost Replacement</option>
            </select></div>
          <div><Label className="text-xs">Required By</Label>
            <Input type="date" value={requiredDate} onChange={e => setRequiredDate(e.target.value)} /></div>
          <div className="flex items-end justify-end">
            <Button size="sm" onClick={submit} disabled={busy || !selectedItems.length} data-testid="prfs-submit">
              <Send className="h-3.5 w-3.5 mr-1" />Create PR ({selectedItems.length})
            </Button>
          </div>
        </div>

        <div className="text-xs text-slate-600">
          {suggestions.length === 0 ? <span className="text-emerald-600">All items above reorder level.</span> :
            <>{suggestions.length} item(s) below reorder · Selected value: <span className="font-semibold">{fmt(totalValue)}</span></>}
        </div>

        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-center px-2 py-1 w-8">
                <input type="checkbox" onChange={e => {
                  const sel = {};
                  suggestions.forEach(s => sel[s.item_id] = { selected: e.target.checked, qty: selected[s.item_id]?.qty || s.suggested_qty || 1 });
                  setSelected(sel);
                }} data-testid="prfs-select-all" />
              </th>
              <th className="text-left px-2 py-1">Item</th>
              <th className="text-left px-2 py-1">Category</th>
              <th className="text-right px-2 py-1">Available</th>
              <th className="text-right px-2 py-1">Min / Reorder</th>
              <th className="text-right px-2 py-1">Required Qty</th>
              <th className="text-right px-2 py-1">Rate</th>
              <th className="text-left px-2 py-1">Suggested Vendor</th>
              <th className="text-center px-2 py-1">Trigger</th>
            </tr></thead>
            <tbody>
              {suggestions.map(s => (
                <tr key={s.item_id} className={`border-t hover:bg-slate-50 ${s.trigger === "below_min" ? "bg-rose-50/30" : ""}`} data-testid={`prfs-row-${s.item_id}`}>
                  <td className="px-2 py-1 text-center">
                    <input type="checkbox" checked={!!selected[s.item_id]?.selected}
                            onChange={e => setSelected(p => ({ ...p, [s.item_id]: { ...p[s.item_id], selected: e.target.checked } }))} />
                  </td>
                  <td className="px-2 py-1"><span className="font-mono text-[10px] text-slate-400">{s.item_code}</span> · {s.item_name}</td>
                  <td className="px-2 py-1 text-[10px] text-slate-500">{s.category}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{s.available_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{s.min_stock} / {s.reorder_level}</td>
                  <td className="px-2 py-1 text-right">
                    <Input className="h-6 text-right w-20 inline-block" type="number"
                          value={selected[s.item_id]?.qty ?? s.suggested_qty}
                          onChange={e => setSelected(p => ({ ...p, [s.item_id]: { ...p[s.item_id], qty: e.target.value } }))} />
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(s.rate)}</td>
                  <td className="px-2 py-1 text-[10px]">{s.vendor_name || "—"}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${s.trigger === "below_min" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{s.trigger.replace("_", " ")}</span>
                  </td>
                </tr>
              ))}
              {!suggestions.length && <tr><td colSpan={9} className="text-center py-6 text-emerald-600">All items above reorder level. Nothing to procure.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 2. Pending POs for GRN ═══════════════════ */
export function PendingPOsView() {
  const [data, setData] = useState({ rows: [], count: 0, total_pending_value: 0 });

  const load = async () => {
    try {
      const r = await api.get("/inv2/pending-pos-for-grn");
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <Card data-testid="pending-pos-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Pending POs for GRN · <span className="text-xs text-slate-500">{data.count} POs · {fmt(data.total_pending_value)} pending value</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => exportCSV(data.rows.map(r => ({
            po_number: r.po_number, vendor: r.vendor_name, project: r.project, status: r.status,
            pending_lines: r.pending_lines, pending_qty_total: r.pending_qty_total, pending_value_total: r.pending_value_total,
          })), "pending_pos_for_grn.csv")} data-testid="pending-pos-csv"><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {data.rows.map(po => (
            <div key={po.po_id} className="border rounded-md p-2.5" data-testid={`pending-po-${po.po_id}`}>
              <div className="flex justify-between items-center mb-1">
                <div>
                  <span className="font-mono font-semibold">{po.po_number}</span>
                  <span className="text-slate-500 text-xs ml-2">· {po.po_date}</span>
                  <span className="mx-2 text-slate-300">|</span>
                  <span className="font-medium">{po.vendor_name || "—"}</span>
                  {po.project && <span className="text-xs text-slate-500 ml-2">· {po.project}</span>}
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${po.status === "partially_received" ? "bg-amber-100 text-amber-800" : "bg-blue-100 text-blue-800"}`}>{po.status?.replace("_", " ")}</span>
                  <span className="text-sm font-semibold">{fmt(po.pending_value_total)}</span>
                </div>
              </div>
              <table className="w-full text-xs mt-1">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-2 py-1">Item</th>
                  <th className="text-right px-2 py-1">Ordered</th>
                  <th className="text-right px-2 py-1">Received</th>
                  <th className="text-right px-2 py-1">Pending</th>
                  <th className="text-right px-2 py-1">Rate</th>
                  <th className="text-right px-2 py-1">Pending Value</th>
                </tr></thead>
                <tbody>
                  {po.lines.map((ln, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1">{ln.item_name}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{ln.ordered_qty}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{ln.received_qty}</td>
                      <td className="px-2 py-1 text-right tabular-nums font-semibold text-amber-700">{ln.pending_qty}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(ln.rate)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(ln.pending_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {!data.rows.length && <div className="text-center text-slate-400 py-12">No pending POs — all material has been received.</div>}
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 3. Stock Inward Report ═══════════════════ */
export function StockInwardReportView() {
  const [df, setDf] = useState("");
  const [dt, setDt] = useState("");
  const [data, setData] = useState({ rows: [], count: 0, total_value: 0, by_type: {} });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (df) params.set("date_from", df);
      if (dt) params.set("date_to", dt);
      const r = await api.get(`/inv2/stock-inward-report?${params}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <Card data-testid="inward-report-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Stock Inward Report · <span className="text-xs text-slate-500">{data.count} txns · {fmt(data.total_value)}</span></CardTitle>
        <div className="flex gap-2 items-center">
          <Label className="text-xs">From</Label><Input type="date" className="h-8" value={df} onChange={e => setDf(e.target.value)} />
          <Label className="text-xs">To</Label><Input type="date" className="h-8" value={dt} onChange={e => setDt(e.target.value)} />
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
          <Button size="sm" variant="outline" onClick={() => exportCSV(data.rows, "stock_inward.csv")} data-testid="inward-csv"><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-2 mb-3">
          {Object.entries(data.by_type || {}).map(([k, v]) => (
            <div key={k} className="p-2 border rounded-md bg-slate-50">
              <div className="text-[10px] uppercase text-slate-500">{k.replace("_", " ")}</div>
              <div className="font-bold">{v}</div>
            </div>
          ))}
        </div>
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">Type</th>
              <th className="text-left px-2 py-1">Item</th>
              <th className="text-right px-2 py-1">Qty</th>
              <th className="text-left px-2 py-1">Vendor</th>
              <th className="text-left px-2 py-1">PO</th>
              <th className="text-left px-2 py-1">GRN / Ref</th>
              <th className="text-left px-2 py-1">By</th>
            </tr></thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{(r.created_at || "").slice(0, 10)}</td>
                  <td className="px-2 py-1"><span className="px-1 py-0.5 rounded text-[10px] bg-blue-50">{r.txn_type}</span></td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.quantity}</td>
                  <td className="px-2 py-1">{r.vendor_name || "—"}</td>
                  <td className="px-2 py-1 font-mono text-[10px]">{r.po_number || "—"}</td>
                  <td className="px-2 py-1 font-mono text-[10px]">{r.ref_no || "—"}</td>
                  <td className="px-2 py-1">{r.created_by_name || r.received_by || "—"}</td>
                </tr>
              ))}
              {!data.rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No inward transactions in this range.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 4. GRN Pending Invoice (Accounts) ═══════════════════ */
export function GRNPendingInvoiceView() {
  const [data, setData] = useState({ rows: [], count: 0, matched_count: 0, total_count: 0, total_estimated_value: 0 });

  const load = async () => {
    try {
      const r = await api.get("/inv2/grn-pending-invoice");
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <Card data-testid="grn-pending-inv-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GRN Pending Invoice · <span className="text-xs text-slate-500">{data.count} GRNs · {data.matched_count}/{data.total_count} already matched · {fmt(data.total_estimated_value)} pending</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => exportCSV(data.rows, "grn_pending_invoice.csv")} data-testid="grn-pending-inv-csv"><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">GRN</th>
              <th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">PO</th>
              <th className="text-left px-2 py-1">Vendor</th>
              <th className="text-right px-2 py-1">Accepted</th>
              <th className="text-right px-2 py-1">Est. Value</th>
              <th className="text-left px-2 py-1">Vendor Inv #</th>
              <th className="text-right px-2 py-1">Days Pending</th>
            </tr></thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.grn_id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.grn_number}</td>
                  <td className="px-2 py-1 font-mono">{r.grn_date}</td>
                  <td className="px-2 py-1 font-mono">{r.po_number}</td>
                  <td className="px-2 py-1">{r.vendor_name}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.total_accepted}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold">{fmt(r.estimated_value)}</td>
                  <td className="px-2 py-1 font-mono">{r.vendor_invoice_no || "—"}</td>
                  <td className="px-2 py-1 text-right">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.days_pending > 30 ? "bg-rose-100 text-rose-800" : r.days_pending > 14 ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{r.days_pending}d</span>
                  </td>
                </tr>
              ))}
              {!data.rows.length && <tr><td colSpan={8} className="text-center py-6 text-emerald-600">All GRNs matched to vendor invoices.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 5. Accounts GRN Visibility ═══════════════════ */
export function AccountsGRNVisibilityView() {
  const [data, setData] = useState({ rows: [] });
  const [poFilter, setPoFilter] = useState("");

  const load = async () => {
    try {
      const r = await api.get(`/inv2/accounts-grn-visibility${poFilter ? `?po_number=${poFilter}` : ""}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <Card data-testid="accounts-grn-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Accounts GRN Visibility (3-way match feed)</CardTitle>
        <div className="flex gap-2 items-center">
          <Input className="h-8 w-40" placeholder="PO Number filter" value={poFilter} onChange={e => setPoFilter(e.target.value)} />
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">GRN</th>
              <th className="text-left px-2 py-1">PO</th>
              <th className="text-left px-2 py-1">Vendor</th>
              <th className="text-right px-2 py-1">PO Value</th>
              <th className="text-right px-2 py-1">GRN Value</th>
              <th className="text-left px-2 py-1">Vendor Inv #</th>
              <th className="text-left px-2 py-1">Bill #</th>
              <th className="text-right px-2 py-1">Bill Amount</th>
              <th className="text-center px-2 py-1">3-Way</th>
            </tr></thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.grn_id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.grn_number}</td>
                  <td className="px-2 py-1 font-mono">{r.po_number}</td>
                  <td className="px-2 py-1">{r.vendor_name}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.po_value)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.estimated_grn_value)}</td>
                  <td className="px-2 py-1 font-mono">{r.vendor_invoice_no || "—"}</td>
                  <td className="px-2 py-1 font-mono">{r.bill_number || "—"}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.bill_amount ? fmt(r.bill_amount) : "—"}</td>
                  <td className="px-2 py-1 text-center">
                    {r.three_way_match ? <CheckCircle2 className="h-4 w-4 inline text-emerald-600" /> :
                     r.bill_number ? <AlertOctagon className="h-4 w-4 inline text-amber-600" /> :
                     <XCircle className="h-4 w-4 inline text-rose-500" />}
                  </td>
                </tr>
              ))}
              {!data.rows.length && <tr><td colSpan={9} className="text-center py-6 text-slate-400">No GRNs found.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 6. Inspection Hold ═══════════════════ */
export function InspectionHoldView() {
  const [data, setData] = useState({ rows: [], count: 0 });

  const load = async () => {
    try {
      const r = await api.get("/inv2/inspection-hold");
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <Card data-testid="inspection-hold-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Inspection Hold · <span className="text-xs text-slate-500">{data.count} items awaiting inspection</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">GRN</th>
              <th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">PO</th>
              <th className="text-left px-2 py-1">Vendor</th>
              <th className="text-left px-2 py-1">Item</th>
              <th className="text-right px-2 py-1">Received</th>
              <th className="text-right px-2 py-1">Accepted</th>
              <th className="text-right px-2 py-1">Rejected</th>
              <th className="text-right px-2 py-1">Hold</th>
              <th className="text-center px-2 py-1">Status</th>
            </tr></thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.grn_number}</td>
                  <td className="px-2 py-1 font-mono">{r.grn_date}</td>
                  <td className="px-2 py-1 font-mono">{r.po_number}</td>
                  <td className="px-2 py-1">{r.vendor_name}</td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.received_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-emerald-700">{r.accepted_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-rose-700">{r.rejected_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold text-amber-700">{r.hold_qty}</td>
                  <td className="px-2 py-1 text-center">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-800">{r.inspection_status}</span>
                  </td>
                </tr>
              ))}
              {!data.rows.length && <tr><td colSpan={10} className="text-center py-6 text-emerald-600">No items on inspection hold.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 7. Procurement Pipeline (Finance) ═══════════════════ */
export function ProcurementPipelineView() {
  const [d, setD] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/inv2/procurement-pipeline");
      setD(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  if (!d) return <div className="p-4 text-sm text-slate-500">Loading procurement pipeline…</div>;

  const stages = [
    { label: "PR Pending", count: d.pr_pending_count, value: d.pr_pending_value, icon: ClipboardList, color: "blue" },
    { label: "PO Pending Receipt", count: d.po_pending_count, value: d.po_pending_value, icon: ShoppingCart, color: "amber" },
    { label: "GRN Received (30d)", count: d.grn_30d_count, value: d.grn_30d_value, icon: Truck, color: "emerald" },
    { label: "Emergency PRs", count: d.emergency_pr_count, value: 0, icon: AlertOctagon, color: "rose" },
  ];

  return (
    <Card data-testid="proc-pipeline-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Procurement Pipeline (Finance View)</CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-3">
          {stages.map((s, i) => {
            const Icon = s.icon;
            const palette = {
              blue: "bg-blue-50 border-blue-200",
              amber: "bg-amber-50 border-amber-200",
              emerald: "bg-emerald-50 border-emerald-200",
              rose: "bg-rose-50 border-rose-200",
            }[s.color];
            return (
              <div key={i} className={`p-4 border rounded-md ${palette}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] uppercase tracking-wider font-semibold">{s.label}</span>
                  <Icon className="h-4 w-4 opacity-60" />
                </div>
                <div className="text-2xl font-bold tabular-nums">{s.count}</div>
                {s.value > 0 && <div className="text-sm text-slate-600 mt-1">{fmt(s.value)}</div>}
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex items-center justify-center gap-3 text-xs text-slate-500">
          <span>PR</span><ArrowRight className="h-3 w-3" /><span>RFQ</span><ArrowRight className="h-3 w-3" /><span>PO</span><ArrowRight className="h-3 w-3" /><span>GRN</span><ArrowRight className="h-3 w-3" /><span>Inspection</span><ArrowRight className="h-3 w-3" /><span>Vendor Bill</span><ArrowRight className="h-3 w-3" /><span>Payment</span>
        </div>
      </CardContent>
    </Card>
  );
}
