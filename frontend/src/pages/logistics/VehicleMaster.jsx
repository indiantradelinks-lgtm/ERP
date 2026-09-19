/**
 * Vehicle Master (Phase 1) — 22-field vehicle record with fitness/insurance/permit
 * expiry tracking, driver assignment, vendor linkage.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Truck, Plus, RefreshCcw, Pencil, AlertTriangle } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const VEHICLE_TYPES = ["truck", "trailer", "pickup", "crane", "hydra", "forklift", "tempo", "car", "bus", "two_wheeler", "other"];
const OWNERSHIP = ["own", "hired", "vendor"];
const STATUSES = ["available", "allocated", "in_transit", "maintenance", "inactive"];
const STATUS_TONE = {
  available: "bg-emerald-100 text-emerald-800",
  allocated: "bg-blue-100 text-blue-800",
  in_transit: "bg-amber-100 text-amber-800",
  maintenance: "bg-red-100 text-red-800",
  inactive: "bg-slate-100 text-slate-600",
};

const EMPTY = {
  vehicle_number: "", vehicle_type: "truck", ownership_type: "own",
  capacity_mt: "", volume_cbm: "", length_m: "", width_m: "", height_m: "",
  fitness_no: "", fitness_expiry: "",
  insurance_no: "", insurance_expiry: "",
  pollution_expiry: "", permit_valid_till: "",
  gps_installed: false, status: "available",
  assigned_driver_id: "", transport_vendor_id: "",
  remarks: "", attachment_url: "",
};

const today = () => new Date().toISOString().slice(0, 10);
const isExpired = (d) => d && d.slice(0, 10) < today();

export default function VehicleMaster() {
  const [rows, setRows] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([
        api.get("/logistics/vehicles"),
        api.get("/logistics/drivers"),
        lookupGet("/vendors"),
      ]);
      setRows(a.data || []); setDrivers(b.data || []); setVendors(c.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const payload = { ...form };
      ["capacity_mt", "volume_cbm", "length_m", "width_m", "height_m"].forEach((k) => {
        if (payload[k] === "" || payload[k] === null) delete payload[k];
        else payload[k] = Number(payload[k]);
      });
      ["fitness_expiry", "insurance_expiry", "pollution_expiry", "permit_valid_till"].forEach((k) => {
        if (!payload[k]) delete payload[k];
      });
      if (editing?.id) await api.put(`/logistics/vehicles/${editing.id}`, payload);
      else await api.post(`/logistics/vehicles`, payload);
      toast.success(editing?.id ? "Updated" : "Created");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="vehicle-master-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Truck className="h-6 w-6 text-blue-600" /> Vehicle Master
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Fleet register with fitness · insurance · permit compliance tracking. Duplicate vehicle numbers are blocked.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="veh-new">
            <Plus className="h-4 w-4 mr-1" /> New Vehicle
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Code</th>
                <th className="text-left px-3 py-2">Vehicle #</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Ownership</th>
                <th className="text-right px-3 py-2">Capacity (MT)</th>
                <th className="text-left px-3 py-2">Driver</th>
                <th className="text-left px-3 py-2">Fitness</th>
                <th className="text-left px-3 py-2">Insurance</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={10} className="text-center py-8 text-slate-400">No vehicles yet.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`veh-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono text-xs">{r.vehicle_code || "—"}</td>
                  <td className="px-3 py-2 font-semibold">{r.vehicle_number || r.reg_number}</td>
                  <td className="px-3 py-2 capitalize">{(r.vehicle_type || r.type || "").replace(/_/g, " ")}</td>
                  <td className="px-3 py-2 capitalize">{r.ownership_type || "—"}</td>
                  <td className="px-3 py-2 text-right">{r.capacity_mt ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{r.assigned_driver_name || r.driver || "—"}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.fitness_expiry ? (
                      <span className={isExpired(r.fitness_expiry) ? "text-red-700 font-semibold" : ""}>
                        {isExpired(r.fitness_expiry) && <AlertTriangle className="h-3 w-3 inline mr-0.5" />}
                        {r.fitness_expiry}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.insurance_expiry ? (
                      <span className={isExpired(r.insurance_expiry) ? "text-red-700 font-semibold" : ""}>
                        {r.insurance_expiry}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>
                      {(r.status || "").replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`veh-edit-${r.id}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Vehicle</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Vehicle Number *</Label><Input value={form.vehicle_number} onChange={(e) => setForm({ ...form, vehicle_number: e.target.value })} data-testid="veh-number" /></div>
            <div>
              <Label>Vehicle Type</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.vehicle_type} onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })} data-testid="veh-type">
                {VEHICLE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <Label>Ownership</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.ownership_type} onChange={(e) => setForm({ ...form, ownership_type: e.target.value })}>
                {OWNERSHIP.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div><Label>Capacity (MT)</Label><Input type="number" value={form.capacity_mt} onChange={(e) => setForm({ ...form, capacity_mt: e.target.value })} /></div>
            <div><Label>Volume (CBM)</Label><Input type="number" value={form.volume_cbm} onChange={(e) => setForm({ ...form, volume_cbm: e.target.value })} /></div>
            <div><Label>Length (m)</Label><Input type="number" value={form.length_m} onChange={(e) => setForm({ ...form, length_m: e.target.value })} /></div>
            <div><Label>Width (m)</Label><Input type="number" value={form.width_m} onChange={(e) => setForm({ ...form, width_m: e.target.value })} /></div>
            <div><Label>Height (m)</Label><Input type="number" value={form.height_m} onChange={(e) => setForm({ ...form, height_m: e.target.value })} /></div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.gps_installed} onChange={(e) => setForm({ ...form, gps_installed: e.target.checked })} />
                <span>GPS Installed</span>
              </label>
            </div>
            <div><Label>Fitness No.</Label><Input value={form.fitness_no} onChange={(e) => setForm({ ...form, fitness_no: e.target.value })} /></div>
            <div><Label>Fitness Expiry</Label><Input type="date" value={form.fitness_expiry} onChange={(e) => setForm({ ...form, fitness_expiry: e.target.value })} /></div>
            <div><Label>Insurance No.</Label><Input value={form.insurance_no} onChange={(e) => setForm({ ...form, insurance_no: e.target.value })} /></div>
            <div><Label>Insurance Expiry</Label><Input type="date" value={form.insurance_expiry} onChange={(e) => setForm({ ...form, insurance_expiry: e.target.value })} /></div>
            <div><Label>PUC Expiry</Label><Input type="date" value={form.pollution_expiry} onChange={(e) => setForm({ ...form, pollution_expiry: e.target.value })} /></div>
            <div><Label>Permit Valid Till</Label><Input type="date" value={form.permit_valid_till} onChange={(e) => setForm({ ...form, permit_valid_till: e.target.value })} /></div>
            <div>
              <Label>Status</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="veh-status">
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <Label>Assigned Driver</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.assigned_driver_id} onChange={(e) => setForm({ ...form, assigned_driver_id: e.target.value })}>
                <option value="">—</option>
                {drivers.map((d) => <option key={d.id} value={d.id}>{d.driver_name}{isExpired(d.license_expiry) ? " (licence expired)" : ""}</option>)}
              </select>
            </div>
            <div>
              <Label>Transport Vendor</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.transport_vendor_id} onChange={(e) => setForm({ ...form, transport_vendor_id: e.target.value })}>
                <option value="">—</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
            <div className="col-span-3"><Label>Remarks</Label><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="veh-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
