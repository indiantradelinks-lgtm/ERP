/**
 * Driver Master (Phase 1) — driver register with licence-expiry alert.
 * Expired licence blocks vehicle assignment (backend-enforced).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { User2, Plus, RefreshCcw, Pencil, AlertTriangle } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const STATUSES = ["available", "assigned", "on_trip", "on_leave", "inactive"];
const STATUS_TONE = {
  available: "bg-emerald-100 text-emerald-800",
  assigned: "bg-blue-100 text-blue-800",
  on_trip: "bg-amber-100 text-amber-800",
  on_leave: "bg-slate-100 text-slate-700",
  inactive: "bg-slate-200 text-slate-500",
};
const EMPTY = {
  driver_name: "", mobile: "", alt_mobile: "", license_no: "", license_type: "LMV",
  license_expiry: "", id_proof: "", address: "", vendor_id: "", vendor_name: "",
  emergency_contact: "", status: "available", remarks: "", attachment_url: "",
};

const today = () => new Date().toISOString().slice(0, 10);
const isExpired = (d) => d && d.slice(0, 10) < today();

export default function DriverMaster() {
  const [rows, setRows] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [statusFilter, setStatusFilter] = useState("");

  const load = async () => {
    try {
      const q = statusFilter ? `?status=${statusFilter}` : "";
      const [a, b] = await Promise.all([api.get(`/logistics/drivers${q}`), lookupGet("/vendors")]);
      setRows(a.data || []); setVendors(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [statusFilter]);

  const save = async () => {
    try {
      const payload = { ...form };
      if (!payload.license_expiry) delete payload.license_expiry;
      if (editing?.id) await api.put(`/logistics/drivers/${editing.id}`, payload);
      else await api.post(`/logistics/drivers`, payload);
      toast.success(editing?.id ? "Updated" : "Created");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="driver-master-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <User2 className="h-6 w-6 text-blue-600" /> Driver Master
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Driver register with licence-expiry monitoring. Expired licences block vehicle assignment.
          </p>
        </div>
        <div className="flex gap-2">
          <select className="border rounded h-10 px-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="drv-filter">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="drv-new">
            <Plus className="h-4 w-4 mr-1" /> New Driver
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Code</th>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">Mobile</th>
              <th className="text-left px-3 py-2">Licence</th>
              <th className="text-left px-3 py-2">Expiry</th>
              <th className="text-left px-3 py-2">Vendor</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={8} className="text-center py-8 text-slate-400">No drivers yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`drv-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.driver_code}</td>
                <td className="px-3 py-2 font-semibold">{r.driver_name}</td>
                <td className="px-3 py-2 text-xs">{r.mobile || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.license_no} <span className="text-slate-500">({r.license_type})</span></td>
                <td className="px-3 py-2 text-xs">
                  {r.license_expiry ? (
                    <span className={isExpired(r.license_expiry) ? "text-red-700 font-semibold" : ""}>
                      {isExpired(r.license_expiry) && <AlertTriangle className="h-3 w-3 inline mr-0.5" />}
                      {r.license_expiry}
                    </span>
                  ) : "—"}
                </td>
                <td className="px-3 py-2 text-xs">{r.vendor_name || "—"}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>
                    {(r.status || "").replace(/_/g, " ")}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`drv-edit-${r.id}`}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Driver</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Driver Name *</Label><Input value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} data-testid="drv-name" /></div>
            <div><Label>Mobile</Label><Input value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></div>
            <div><Label>Alternate Mobile</Label><Input value={form.alt_mobile} onChange={(e) => setForm({ ...form, alt_mobile: e.target.value })} /></div>
            <div><Label>Licence No *</Label><Input value={form.license_no} onChange={(e) => setForm({ ...form, license_no: e.target.value })} data-testid="drv-license" /></div>
            <div><Label>Licence Type</Label><Input value={form.license_type} onChange={(e) => setForm({ ...form, license_type: e.target.value })} placeholder="LMV / HMV / HGV" /></div>
            <div><Label>Licence Expiry</Label><Input type="date" value={form.license_expiry} onChange={(e) => setForm({ ...form, license_expiry: e.target.value })} data-testid="drv-expiry" /></div>
            <div><Label>ID Proof</Label><Input value={form.id_proof} onChange={(e) => setForm({ ...form, id_proof: e.target.value })} /></div>
            <div><Label>Emergency Contact</Label><Input value={form.emergency_contact} onChange={(e) => setForm({ ...form, emergency_contact: e.target.value })} /></div>
            <div>
              <Label>Vendor (if vendor driver)</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.vendor_id} onChange={(e) => {
                const v = vendors.find((x) => x.id === e.target.value);
                setForm({ ...form, vendor_id: e.target.value, vendor_name: v?.name || "" });
              }}>
                <option value="">— Own driver —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Status</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div className="col-span-2"><Label>Address</Label><Textarea rows={2} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
            <div className="col-span-2"><Label>Remarks</Label><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="drv-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
