/**
 * Logistics Dashboard (Phase 1) — 20 real-time KPIs with drill-down.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Truck, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

const TILES = [
  { key: "total_vehicles",           label: "Total Vehicles",          tone: "slate",   link: "/app/logistics/vehicles" },
  { key: "vehicles_available",       label: "Vehicles Available",      tone: "emerald", link: "/app/logistics/vehicles" },
  { key: "vehicles_in_transit",      label: "Vehicles In Transit",     tone: "amber",   link: "/app/logistics/vehicles" },
  { key: "vehicles_maintenance",     label: "Under Maintenance",       tone: "red",     link: "/app/logistics/vehicles" },
  { key: "total_drivers",            label: "Total Drivers",           tone: "slate",   link: "/app/logistics/drivers" },
  { key: "drivers_available",        label: "Drivers Available",       tone: "emerald", link: "/app/logistics/drivers" },
  { key: "drivers_on_trip",          label: "Drivers On Trip",         tone: "amber",   link: "/app/logistics/drivers" },
  { key: "dispatch_pending",         label: "Dispatch Pending",        tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "dispatch_approved",        label: "Dispatch Approved",       tone: "emerald", link: "/app/logistics/dispatch-requests" },
  { key: "dispatch_in_transit",      label: "Dispatch In Transit",     tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "delivery_pending",         label: "Deliveries Pending",      tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "return_transport_pending", label: "Return Transport Pending", tone: "amber",  link: "/app/logistics/dispatch-requests" },
  { key: "manpower_mobilization",    label: "Manpower Mobilization",   tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "material_movement",        label: "Material Movement",       tone: "amber",   link: "/app/logistics/dispatch-requests" },
  { key: "overdue_deliveries",       label: "Overdue Deliveries",      tone: "red",     link: "/app/logistics/dispatch-requests" },
  { key: "fitness_expired",          label: "Fitness Expired",         tone: "red",     link: "/app/logistics/vehicles" },
  { key: "insurance_expired",        label: "Insurance Expired",       tone: "red",     link: "/app/logistics/vehicles" },
  { key: "driver_license_expired",   label: "Driver Licence Expired",  tone: "red",     link: "/app/logistics/drivers" },
  { key: "fuel_entries_this_month",  label: "Fuel Entries (Month)",    tone: "slate",   link: "/app/logistics" },
  { key: "vehicle_expense_this_month", label: "Vehicle Expense (Month)", tone: "slate", link: "/app/logistics" },
];

const TONE_CLS = {
  red: "border-red-200 hover:border-red-400 hover:bg-red-50/40",
  amber: "border-amber-200 hover:border-amber-400 hover:bg-amber-50/40",
  emerald: "border-emerald-200 hover:border-emerald-400 hover:bg-emerald-50/40",
  slate: "border-slate-200 hover:border-slate-400 hover:bg-slate-50/40",
};
const VAL_CLS = { red: "text-red-700", amber: "text-amber-700", emerald: "text-emerald-700", slate: "text-slate-900" };

export default function LogisticsDashboard() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    try { const r = await api.get("/logistics/dashboard"); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading Logistics Dashboard…</div>;
  const k = data.kpis || {};
  const recent = data.recent_dispatches || [];

  return (
    <div className="p-6 space-y-5" data-testid="logistics-dashboard">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
            <Truck className="h-7 w-7 text-blue-600" /> Logistics Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Real-time fleet, driver, dispatch and compliance snapshot. Click any tile to drill down.
          </p>
        </div>
        <Button variant="outline" onClick={load} data-testid="logi-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        {TILES.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => navigate(t.link)}
            className={`bg-card border rounded-sm p-3 text-left transition-colors cursor-pointer ${TONE_CLS[t.tone]}`}
            data-testid={`kpi-${t.key}`}
          >
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground leading-tight">
              {t.label}
            </div>
            <div className={`mt-1 text-2xl font-black ${VAL_CLS[t.tone]}`}>
              {k[t.key] ?? 0}
            </div>
          </button>
        ))}
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <div className="px-3 py-2 border-b bg-slate-50">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-700">Recent Dispatches</div>
        </div>
        <table className="w-full text-xs">
          <tbody>
            {recent.length === 0 && (
              <tr><td colSpan={4} className="text-center py-6 text-slate-400">No dispatch requests yet.</td></tr>
            )}
            {recent.map((r) => (
              <tr key={r.dr_no} className="border-t hover:bg-slate-50/40 cursor-pointer" onClick={() => navigate("/app/logistics/dispatch-requests")} data-testid={`recent-${r.dr_no}`}>
                <td className="px-3 py-1.5 font-mono">{r.dr_no}</td>
                <td className="px-3 py-1.5 capitalize">{r.dispatch_type}</td>
                <td className="px-3 py-1.5 text-slate-600">{r.project_code || "—"}</td>
                <td className="px-3 py-1.5"><span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 bg-slate-100 rounded">{r.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
