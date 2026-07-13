/**
 * Logistics Phase 5 — Reports Center, Trip Closure, Advanced Dashboard.
 *
 * Exports:
 *   LogisticsReportsCenter, TripClosurePanel, LogisticsAdvancedDashboard
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  FileBarChart, Download, RefreshCcw, CheckCircle2, XCircle,
  ClipboardList, TrendingUp, AlertTriangle, LockOpen,
} from "lucide-react";

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

// ═══════════════════════════════════════════════════════════════════════════
// Reports Center — 30 reports · filters · Excel export
// ═══════════════════════════════════════════════════════════════════════════
export function LogisticsReportsCenter() {
  const [catalog, setCatalog] = useState([]);
  const [reportKey, setReportKey] = useState("");
  const [filters, setFilters] = useState({
    from: "", to: "", project_code: "", vehicle_id: "", vendor_id: "", status: "", category: "",
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/logistics/reports/list")
      .then((r) => { setCatalog(r.data || []); if ((r.data || []).length) setReportKey(r.data[0].key); })
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load reports"));
  }, []);

  const load = async () => {
    if (!reportKey) return;
    setLoading(true);
    try {
      const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
      const r = await api.get(`/logistics/reports/${reportKey}${qs ? "?" + qs : ""}`);
      setData(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Load failed");
    } finally { setLoading(false); }
  };

  useEffect(() => { if (reportKey) load(); }, [reportKey]);  // eslint-disable-line react-hooks/exhaustive-deps

  const exportXlsx = async () => {
    try {
      const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
      const r = await api.get(`/logistics/reports/${reportKey}/export.xlsx${qs ? "?" + qs : ""}`,
        { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${reportKey}-${new Date().toISOString().slice(0, 10)}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("Export failed"); }
  };

  const currentMeta = useMemo(() => catalog.find((c) => c.key === reportKey), [catalog, reportKey]);

  return (
    <div className="p-6 space-y-4" data-testid="logistics-reports-center">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 5</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <FileBarChart className="h-6 w-6 text-amber-600" /> Logistics Reports Center
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {catalog.length} reports · Excel export · role & data-scope filtered.
          </p>
        </div>
      </div>

      {/* Report picker + filters */}
      <div className="border rounded-sm bg-card p-3 space-y-3">
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <label className="text-[10px] uppercase font-bold text-slate-500">Report</label>
            <select
              className="w-full border rounded h-10 px-2 text-sm"
              value={reportKey}
              onChange={(e) => setReportKey(e.target.value)}
              data-testid="report-picker"
            >
              {catalog.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase font-bold text-slate-500">From</label>
            <Input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} data-testid="filter-from" />
          </div>
          <div>
            <label className="text-[10px] uppercase font-bold text-slate-500">To</label>
            <Input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} data-testid="filter-to" />
          </div>
          <div>
            <label className="text-[10px] uppercase font-bold text-slate-500">Project Code</label>
            <Input value={filters.project_code} onChange={(e) => setFilters({ ...filters, project_code: e.target.value })} placeholder="e.g. PRJ-001" data-testid="filter-project" />
          </div>
          <div>
            <label className="text-[10px] uppercase font-bold text-slate-500">Status</label>
            <Input value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} placeholder="status" data-testid="filter-status" />
          </div>
          <Button onClick={load} variant="outline" data-testid="btn-run-report">
            <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Run
          </Button>
          <Button onClick={exportXlsx} data-testid="btn-export-xlsx">
            <Download className="h-3.5 w-3.5 mr-1" /> Excel
          </Button>
        </div>
      </div>

      {/* Result table */}
      <div className="border rounded-sm bg-card overflow-hidden">
        <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider flex items-center justify-between">
          <span>{currentMeta?.label || "—"}</span>
          <span className="font-normal">{data?.count || 0} rows</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>{(currentMeta?.columns || []).map((c) => <th key={c} className="text-left px-3 py-2">{c}</th>)}</tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={(currentMeta?.columns || []).length || 1} className="text-center py-8 text-slate-400">Loading…</td></tr>}
              {!loading && (!data?.rows || data.rows.length === 0) && (
                <tr><td colSpan={(currentMeta?.columns || []).length || 1} className="text-center py-8 text-slate-400">No rows.</td></tr>
              )}
              {!loading && (data?.rows || []).map((r, i) => (
                <tr key={r.id || i} className="border-t hover:bg-slate-50/40" data-testid={`report-row-${i}`}>
                  {(currentMeta?.columns || []).map((c) => (
                    <td key={c} className="px-3 py-1.5">
                      {Array.isArray(r[c]) ? r[c].join(", ") : (r[c] === true ? "✓" : r[c] === false ? "—" : (r[c] ?? "—")).toString().slice(0, 60)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// Trip Closure Panel — 15-point checklist + close / reopen
// ═══════════════════════════════════════════════════════════════════════════
export function TripClosurePanel() {
  const { id: drId } = useParams();
  const nav = useNavigate();
  const [check, setCheck] = useState(null);
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/logistics/dispatch-requests/${drId}/closure-checklist`);
      setCheck(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load checklist"); }
  };
  useEffect(() => { if (drId) load(); }, [drId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const close = async () => {
    setBusy(true);
    try {
      await api.post(`/logistics/dispatch-requests/${drId}/close`, {
        reason, override_exceptions: override,
      });
      toast.success("Trip closed");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Closure failed"); }
    finally { setBusy(false); }
  };

  const reopen = async () => {
    if (!reason.trim()) { toast.error("Reason required to reopen"); return; }
    setBusy(true);
    try {
      await api.post(`/logistics/dispatch-requests/${drId}/reopen`, { reason });
      toast.success("Trip reopened");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Reopen failed"); }
    finally { setBusy(false); }
  };

  if (!check) return <div className="p-6 text-slate-400">Loading…</div>;
  const doneCount = check.checklist.filter((i) => i.done).length;
  const isClosed = check.status === "closed";

  return (
    <div className="p-6 space-y-4 max-w-3xl mx-auto" data-testid="trip-closure-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 5</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <ClipboardList className="h-6 w-6 text-amber-600" /> Trip Closure — {check.dr_no}
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Status: <span className="font-mono">{check.status}</span> · {doneCount}/{check.checklist.length} items complete
          {isClosed && <span className="ml-2 text-emerald-700">· Closed</span>}
        </p>
      </div>

      <div className="border rounded-sm bg-card">
        <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider flex justify-between">
          <span>Closure Checklist</span>
          <span>{check.can_close ? <span className="text-emerald-700">Ready to close</span> : <span className="text-amber-700">Not ready</span>}</span>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {check.checklist.map((it, i) => (
              <tr key={it.key} className="border-t" data-testid={`chk-${it.key}`}>
                <td className="px-3 py-2 w-6 text-center">
                  {it.done
                    ? <CheckCircle2 className="h-4 w-4 text-emerald-600 inline" />
                    : <XCircle className="h-4 w-4 text-slate-300 inline" />}
                </td>
                <td className="px-3 py-2">{i + 1}. {it.label}</td>
                <td className="px-3 py-2 text-xs text-right text-slate-500">
                  {it.done ? "Done" : "Pending"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Actions */}
      <div className="border rounded-sm bg-card p-3 space-y-3">
        <div>
          <label className="text-[10px] uppercase font-bold text-slate-500">Reason / Note</label>
          <Input value={reason} onChange={(e) => setReason(e.target.value)}
                 placeholder={isClosed ? "Reopen reason (required)" : "Closure remarks (optional)"}
                 data-testid="closure-reason" />
        </div>
        {!isClosed && (
          <label className="text-xs flex items-center gap-2">
            <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)}
                   data-testid="closure-override" />
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
            Override open shortage/damage exceptions (needs Logistics Head or higher)
          </label>
        )}
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => nav(-1)}>Back</Button>
          {!isClosed && (
            <Button onClick={close} disabled={busy} data-testid="btn-close-trip">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Close Trip
            </Button>
          )}
          {isClosed && (
            <Button onClick={reopen} disabled={busy} variant="destructive" data-testid="btn-reopen-trip">
              <LockOpen className="h-3.5 w-3.5 mr-1" /> Reopen Trip
            </Button>
          )}
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// Advanced Dashboard — 27 cards + top projects + cost trend
// ═══════════════════════════════════════════════════════════════════════════
const CARD_META = [
  { key: "total_vehicles",                label: "Total Vehicles",         tone: "slate",   link: "/app/logistics/vehicles" },
  { key: "vehicles_available",            label: "Vehicles Available",     tone: "emerald", link: "/app/logistics/vehicle-availability" },
  { key: "vehicles_in_transit",           label: "Vehicles In Transit",    tone: "amber",   link: "/app/logistics/in-transit" },
  { key: "vehicles_maintenance",          label: "Under Maintenance",      tone: "red",     link: "/app/logistics/maintenance" },
  { key: "drivers_available",             label: "Drivers Available",      tone: "emerald", link: "/app/logistics/driver-availability" },
  { key: "drivers_on_trip",               label: "Drivers On Trip",        tone: "amber",   link: "/app/logistics/drivers" },
  { key: "total_drivers",                 label: "Total Drivers",          tone: "slate",   link: "/app/logistics/drivers" },
  { key: "dispatch_requests_pending",     label: "Dispatch Pending",       tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "vehicle_allocation_pending",    label: "Allocation Pending",     tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "material_dispatches_today",     label: "Dispatches Today",       tone: "slate",   link: "/app/logistics/dispatch-requests" },
  { key: "in_transit_material",           label: "In-Transit Material",    tone: "amber",   link: "/app/logistics/in-transit" },
  { key: "delivery_confirmations_pending", label: "Delivery Pending",      tone: "amber",   link: "/app/logistics/deliveries" },
  { key: "overdue_deliveries",            label: "Overdue Deliveries",     tone: "red",     link: "/app/logistics/dispatch-requests" },
  { key: "transit_shortage_damage",       label: "Shortage / Damage",      tone: "red",     link: "/app/logistics/exceptions" },
  { key: "manpower_mobilization_pending", label: "Mobilization Pending",   tone: "amber",   link: "/app/logistics/mobilizations" },
  { key: "demobilization_pending",        label: "Demobilization Pending", tone: "amber",   link: "/app/logistics/demobilizations" },
  { key: "travel_arrangements_pending",   label: "Travel Pending",         tone: "amber",   link: "/app/logistics/travel" },
  { key: "accommodation_pending",         label: "Accommodation Pending",  tone: "amber",   link: "/app/logistics/accommodations" },
  { key: "fuel_cost_this_month",          label: "Fuel Cost (Month)",      tone: "slate",   link: "/app/logistics/fuel",           money: true },
  { key: "vehicle_expense_this_month",    label: "Vehicle Expense (Month)", tone: "slate",  link: "/app/logistics/vehicle-expenses", money: true },
  { key: "vendor_bills_pending",          label: "Vendor Bills Pending",   tone: "amber",   link: "/app/logistics/vendor-bills" },
  { key: "freight_cost_this_month",       label: "Freight Cost (Month)",   tone: "slate",   link: "/app/logistics/cost-summary",   money: true },
  { key: "high_value_approvals_pending",  label: "HV Approvals Pending",   tone: "red",     link: "/app/logistics/finance-approvals" },
  { key: "vehicles_fitness_expiring_soon", label: "Fitness Expiring",      tone: "amber",   link: "/app/logistics/vehicles" },
  { key: "drivers_license_expiring_soon", label: "Licence Expiring",       tone: "amber",   link: "/app/logistics/drivers" },
  { key: "open_exceptions",               label: "Open Exceptions",        tone: "red",     link: "/app/logistics/exceptions" },
  { key: "dispatches_pending_closure",    label: "Pending Closure",        tone: "amber",   link: "/app/logistics/dispatch-requests" },
];
const TONE_CLS = {
  red:     "border-red-200 hover:border-red-400 hover:bg-red-50/40",
  amber:   "border-amber-200 hover:border-amber-400 hover:bg-amber-50/40",
  emerald: "border-emerald-200 hover:border-emerald-400 hover:bg-emerald-50/40",
  slate:   "border-slate-200 hover:border-slate-400 hover:bg-slate-50/40",
};
const VAL_CLS = { red: "text-red-700", amber: "text-amber-700", emerald: "text-emerald-700", slate: "text-slate-900" };

export function LogisticsAdvancedDashboard() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const load = async () => {
    try { const r = await api.get("/logistics/dashboard-v2"); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  if (!data) return <div className="p-6 text-slate-400">Loading dashboard…</div>;
  const c = data.cards || {};

  return (
    <div className="p-6 space-y-4" data-testid="logistics-advanced-dashboard">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 5</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-amber-600" /> Advanced Logistics Dashboard
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {Object.keys(c).length} real-time KPIs · click any card to drill down.
          </p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {CARD_META.map((m) => (
          <button
            key={m.key}
            onClick={() => nav(m.link)}
            data-testid={`card-${m.key}`}
            className={`border rounded-sm p-3 text-left transition-colors bg-card ${TONE_CLS[m.tone]}`}
          >
            <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider truncate">{m.label}</div>
            <div className={`text-2xl font-black ${VAL_CLS[m.tone]}`}>
              {m.money ? inr(c[m.key]) : (c[m.key] ?? 0)}
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">Top 5 Projects by Logistics Cost</div>
          <table className="w-full text-sm">
            <tbody>
              {(data.project_cost_top5 || []).length === 0
                && <tr><td className="px-3 py-4 text-center text-slate-400">No cost data yet.</td></tr>}
              {(data.project_cost_top5 || []).map((p) => (
                <tr key={p.project_code} className="border-t">
                  <td className="px-3 py-1.5 font-mono">{p.project_code}</td>
                  <td className="px-3 py-1.5 text-right font-semibold">{inr(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">Cost Trend (last 6 months)</div>
          <table className="w-full text-sm">
            <tbody>
              {(data.cost_trend || []).length === 0
                && <tr><td className="px-3 py-4 text-center text-slate-400">No trend data yet.</td></tr>}
              {(data.cost_trend || []).map((t) => (
                <tr key={t.month} className="border-t">
                  <td className="px-3 py-1.5 font-mono">{t.month}</td>
                  <td className="px-3 py-1.5 text-right">{inr(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
