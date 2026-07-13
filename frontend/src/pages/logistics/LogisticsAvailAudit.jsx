/**
 * Logistics Availability & Audit Trail (Phase 1) — three lightweight pages
 * combined for compactness: VehicleAvailability, DriverAvailability, AuditTrail.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Truck, User2, History, RefreshCcw } from "lucide-react";

// ------------------------------------------------------------
// Vehicle Availability
// ------------------------------------------------------------
export function VehicleAvailability() {
  const [snap, setSnap] = useState(null);
  const load = async () => {
    try { const r = await api.get("/logistics/vehicles/availability"); setSnap(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  if (!snap) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="p-6 space-y-4" data-testid="vehicle-availability-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <Truck className="h-6 w-6 text-blue-600" /> Vehicle Availability
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">Fleet snapshot by status · fitness / insurance expiry alerts.</p>
      </div>
      <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Vehicles" value={snap.total} tone="slate" />
        {Object.entries(snap.by_status || {}).map(([k, v]) => (
          <StatCard key={k} label={k.replace(/_/g, " ")} value={v} tone={statusTone(k)} testid={`vavl-${k}`} />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatCard label="Fitness Expired" value={snap.fitness_expired} tone="red" />
        <StatCard label="Insurance Expired" value={snap.insurance_expired} tone="red" />
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Driver Availability
// ------------------------------------------------------------
export function DriverAvailability() {
  const [snap, setSnap] = useState(null);
  const load = async () => {
    try { const r = await api.get("/logistics/drivers/availability"); setSnap(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  if (!snap) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="p-6 space-y-4" data-testid="driver-availability-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <User2 className="h-6 w-6 text-blue-600" /> Driver Availability
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">Driver pool snapshot by status · licence expiry alerts.</p>
      </div>
      <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Drivers" value={snap.total} tone="slate" />
        {Object.entries(snap.by_status || {}).map(([k, v]) => (
          <StatCard key={k} label={k.replace(/_/g, " ")} value={v} tone={statusTone(k)} testid={`davl-${k}`} />
        ))}
      </div>
      <StatCard label="Licence Expired" value={snap.license_expired} tone="red" />
    </div>
  );
}

function StatCard({ label, value, tone = "slate", testid }) {
  const cls = {
    red: "border-red-200 bg-red-50/40 text-red-700",
    amber: "border-amber-200 bg-amber-50/40 text-amber-700",
    emerald: "border-emerald-200 bg-emerald-50/40 text-emerald-700",
    blue: "border-blue-200 bg-blue-50/40 text-blue-700",
    slate: "border-slate-200 bg-white text-slate-900",
  }[tone];
  return (
    <div className={`border rounded-sm p-3 ${cls}`} data-testid={testid}>
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-2xl font-black mt-1">{value}</div>
    </div>
  );
}
function statusTone(k) {
  if (["available"].includes(k)) return "emerald";
  if (["allocated", "assigned", "on_trip", "in_transit"].includes(k)) return "amber";
  if (["maintenance", "inactive"].includes(k)) return "red";
  return "slate";
}

// ------------------------------------------------------------
// Logistics Audit Trail
// ------------------------------------------------------------
export function LogisticsAuditTrail() {
  const [kinds, setKinds] = useState([]);
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [filters, setFilters] = useState({ record_kind: "", action: "", from: "", to: "", limit: 500 });

  const load = async () => {
    try {
      const q = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
      const [a, b] = await Promise.all([
        api.get(`/logistics/audit-log?${q.toString()}`),
        api.get("/logistics/audit-log/kinds"),
      ]);
      setRows(a.data.rows || []); setCount(a.data.count || 0); setKinds(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="logistics-audit-trail-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <History className="h-6 w-6 text-blue-600" /> Logistics Audit Trail
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Immutable log of every logistics state change. No hard-delete for approved dispatches.
          </p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <div>
          <Label className="text-[10px] uppercase">Kind</Label>
          <select className="w-full border rounded h-8 px-1 text-xs" value={filters.record_kind} onChange={(e) => setFilters({ ...filters, record_kind: e.target.value })} data-testid="lat-kind">
            <option value="">All</option>
            {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase">Action contains</Label>
          <Input className="h-8 text-xs" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} />
        </div>
        <div><Label className="text-[10px] uppercase">From</Label><Input type="date" className="h-8 text-xs" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} /></div>
        <div><Label className="text-[10px] uppercase">To</Label><Input type="date" className="h-8 text-xs" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} /></div>
        <div className="flex items-end"><Button className="w-full h-8" onClick={load} data-testid="lat-apply">Apply</Button></div>
      </div>

      <div className="text-xs text-slate-500">{count} entries</div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <div className="max-h-[70vh] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">At</th>
                <th className="text-left px-3 py-2">Record</th>
                <th className="text-left px-3 py-2">Action</th>
                <th className="text-left px-3 py-2">By</th>
                <th className="text-left px-3 py-2">Meta</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={5} className="text-center py-8 text-slate-400">No entries.</td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={i} className="border-t hover:bg-slate-50/40" data-testid={`lat-row-${i}`}>
                  <td className="px-3 py-1.5 font-mono">{(r.at || "").slice(0, 19).replace("T", " ")}</td>
                  <td className="px-3 py-1.5">
                    <div className="font-semibold">{r.record_kind}</div>
                    <div className="text-slate-500 text-[10px] font-mono">{r.record_no || r.record_id?.slice(0, 8) || "—"}</div>
                  </td>
                  <td className="px-3 py-1.5"><span className="inline-block px-1.5 py-0.5 bg-slate-100 rounded font-mono text-[10px]">{r.action}</span></td>
                  <td className="px-3 py-1.5">{r.by_name || "—"}</td>
                  <td className="px-3 py-1.5 text-[10px] text-slate-500 max-w-md truncate" title={JSON.stringify(r.meta || {})}>
                    {r.meta && Object.keys(r.meta).length ? JSON.stringify(r.meta) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
