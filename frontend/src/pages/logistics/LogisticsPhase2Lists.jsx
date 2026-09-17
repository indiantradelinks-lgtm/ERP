/**
 * Phase 2 Logistics list pages — In-Transit, Deliveries, Transit Exceptions.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Truck, PackageCheck, AlertOctagon, RefreshCcw, ChevronRight } from "lucide-react";
import { fmtDT } from "@/lib/datetime";

// ------------------------------------------------------------
// In-Transit Tracking
// ------------------------------------------------------------
export function InTransitTracking() {
  const [rows, setRows] = useState([]);
  const nav = useNavigate();
  const load = async () => {
    try { const r = await api.get("/logistics/in-transit"); setRows(r.data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="in-transit-page">
      <Header title="In-Transit Tracking" subtitle="Live view of all dispatches currently on the road." icon={<Truck className="h-6 w-6 text-blue-600" />} onRefresh={load} />
      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">DR #</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Vehicle</th>
              <th className="text-left px-3 py-2">Driver</th>
              <th className="text-left px-3 py-2">From → To</th>
              <th className="text-left px-3 py-2">Updated</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No dispatches in transit.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40 cursor-pointer" onClick={() => nav(`/app/logistics/dispatch-requests/${r.id}`)} data-testid={`it-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.dr_no}</td>
                <td className="px-3 py-2 capitalize">{r.dispatch_type}</td>
                <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.vehicle_number || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.driver_name || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.from_point_name || "?"} → {r.to_point_name || "?"}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{fmtDT(r.updated_at)}</td>
                <td className="px-3 py-2 text-right"><ChevronRight className="h-3 w-3 inline" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Delivery Confirmations
// ------------------------------------------------------------
export function DeliveryConfirmations() {
  const [rows, setRows] = useState([]);
  const nav = useNavigate();
  const load = async () => {
    try { const r = await api.get("/logistics/deliveries"); setRows(r.data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="deliveries-page">
      <Header title="Delivery Confirmations" subtitle="Proof of delivery register — quantities, condition, and shortages captured on site." icon={<PackageCheck className="h-6 w-6 text-blue-600" />} onRefresh={load} />
      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">POD #</th>
              <th className="text-left px-3 py-2">DR #</th>
              <th className="text-right px-3 py-2">Delivered</th>
              <th className="text-right px-3 py-2">Short</th>
              <th className="text-right px-3 py-2">Damaged</th>
              <th className="text-left px-3 py-2">Received By</th>
              <th className="text-left px-3 py-2">At</th>
              <th className="text-left px-3 py-2">Condition</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No deliveries yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40 cursor-pointer" onClick={() => nav(`/app/logistics/dispatch-requests/${r.dr_id}`)} data-testid={`dv-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.delivery_no}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.dr_no}</td>
                <td className="px-3 py-2 text-right">{r.delivered_qty ?? "—"}</td>
                <td className="px-3 py-2 text-right">{r.short_qty || 0}</td>
                <td className="px-3 py-2 text-right">{r.damaged_qty || 0}</td>
                <td className="px-3 py-2 text-xs">{r.received_by || "—"}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{fmtDT(r.delivered_at)}</td>
                <td className="px-3 py-2 text-xs">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${r.is_partial ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                    {r.is_partial ? "Partial" : "Full"} · {r.material_condition || "—"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Transit Exceptions
// ------------------------------------------------------------
export function TransitExceptions() {
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const nav = useNavigate();

  const load = async () => {
    try {
      const q = statusFilter ? `?status=${statusFilter}` : "";
      const r = await api.get(`/logistics/exceptions${q}`);
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [statusFilter]);

  const update = async (id, patch) => {
    try { await api.put(`/logistics/exceptions/${id}`, patch); toast.success("Updated"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Update failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="exceptions-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 2</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <AlertOctagon className="h-6 w-6 text-red-600" /> Transit Shortage / Damage Register
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Every shortage / damage / rejection captured against a dispatch, with responsible party and recovery flag.
          </p>
        </div>
        <div className="flex gap-2">
          <select className="border rounded h-10 px-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="exc-filter">
            <option value="">All statuses</option>
            {["open", "verified", "approved", "closed", "rejected"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Exception #</th>
              <th className="text-left px-3 py-2">DR #</th>
              <th className="text-left px-3 py-2">Kind</th>
              <th className="text-left px-3 py-2">Responsible</th>
              <th className="text-right px-3 py-2">Value</th>
              <th className="text-right px-3 py-2">Recovery</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No exceptions.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`exc-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.exception_no}</td>
                <td className="px-3 py-2 font-mono text-xs cursor-pointer text-blue-700 hover:underline" onClick={() => nav(`/app/logistics/dispatch-requests/${r.dr_id}`)}>{r.dr_no}</td>
                <td className="px-3 py-2 text-xs capitalize">{r.kind}</td>
                <td className="px-3 py-2 text-xs capitalize">{(r.responsible_party || "").replace(/_/g, " ")}</td>
                <td className="px-3 py-2 text-right text-xs">{r.approx_value ? `₹${r.approx_value}` : "—"}</td>
                <td className="px-3 py-2 text-right text-xs">{r.recovery_applicable ? `₹${r.recovery_amount || 0}` : "—"}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${r.status === "closed" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{r.status}</span>
                </td>
                <td className="px-3 py-2 text-right space-x-1 text-xs">
                  {r.status === "open" && <Button size="sm" variant="outline" onClick={() => update(r.id, { status: "verified", verified_by: "Me" })} data-testid={`exc-verify-${r.id}`}>Verify</Button>}
                  {r.status === "verified" && <Button size="sm" variant="outline" onClick={() => update(r.id, { status: "approved", approved_by: "Me" })} data-testid={`exc-approve-${r.id}`}>Approve</Button>}
                  {["approved", "verified"].includes(r.status) && <Button size="sm" onClick={() => update(r.id, { status: "closed" })} data-testid={`exc-close-${r.id}`}>Close</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Header({ title, subtitle, icon, onRefresh }) {
  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 2</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">{icon} {title}</h1>
        <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
      </div>
      <Button variant="outline" onClick={onRefresh}><RefreshCcw className="h-3.5 w-3.5" /></Button>
    </div>
  );
}
