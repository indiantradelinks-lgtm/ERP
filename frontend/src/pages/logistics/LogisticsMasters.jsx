/**
 * Logistics Masters (Phase 1) — thin CRUD pages for Route, Loading Point,
 * Dispatch Type and Transport Vendor Profile. Each is exported separately.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Route as RouteIcon, MapPin, Package, Truck, Plus, RefreshCcw, Pencil, Trash2 } from "lucide-react";

// ------------------------------------------------------------
// Shared CRUD list shell
// ------------------------------------------------------------
function MasterShell({ testId, title, subtitle, icon, columns, endpoint, empty, formFields, onEnrich, extraPreload = [] }) {
  const [rows, setRows] = useState([]);
  const [preloads, setPreloads] = useState({});
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);

  const load = async () => {
    try {
      const promises = [api.get(endpoint), ...extraPreload.map((ep) => api.get(ep.path))];
      const res = await Promise.all(promises);
      let data = res[0].data || [];
      if (onEnrich) data = await onEnrich(data);
      setRows(data);
      const preMap = {};
      extraPreload.forEach((ep, i) => { preMap[ep.key] = res[i + 1].data || []; });
      setPreloads(preMap);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      if (editing?.id) await api.put(`${endpoint}/${editing.id}`, form);
      else await api.post(endpoint, form);
      toast.success("Saved");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const del = async (id) => {
    if (!window.confirm("Delete this record?")) return;
    try { await api.delete(`${endpoint}/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid={testId}>
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            {icon} {title}
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(empty); }} data-testid={`${testId}-new`}>
            <Plus className="h-4 w-4 mr-1" /> New
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right" : "text-left"}`}>{c.label}</th>
              ))}
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={columns.length + 1} className="text-center py-8 text-slate-400">No entries.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`${testId}-row-${r.id}`}>
                {columns.map((c) => (
                  <td key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right" : ""} ${c.className || ""}`}>
                    {c.render ? c.render(r) : (r[c.key] ?? "—")}
                  </td>
                ))}
                <td className="px-3 py-2 text-right space-x-1">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setForm({ ...empty, ...r }); }} data-testid={`${testId}-edit-${r.id}`}><Pencil className="h-3 w-3" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => del(r.id)}><Trash2 className="h-3 w-3 text-red-600" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} · {title}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            {formFields.map((f) => (
              <div key={f.key} className={f.full ? "col-span-2" : ""}>
                <Label>{f.label}</Label>
                {f.type === "textarea" ? (
                  <Textarea rows={f.rows || 2} value={form[f.key] || ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                ) : f.type === "select" ? (
                  <select className="w-full border rounded h-10 px-2 text-sm" value={form[f.key] || ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                    {(f.options || []).map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                  </select>
                ) : f.type === "select-preload" ? (
                  <select className="w-full border rounded h-10 px-2 text-sm" value={form[f.key] || ""} onChange={(e) => {
                    const sel = (preloads[f.preloadKey] || []).find((x) => x.id === e.target.value);
                    const patch = { [f.key]: e.target.value };
                    if (f.mirrorNameTo && sel) patch[f.mirrorNameTo] = sel.name || sel.driver_name || "";
                    setForm({ ...form, ...patch });
                  }}>
                    <option value="">—</option>
                    {(preloads[f.preloadKey] || []).map((o) => <option key={o.id} value={o.id}>{o.name || o.driver_name || o.id}</option>)}
                  </select>
                ) : f.type === "checkbox" ? (
                  <label className="flex items-center gap-2 text-sm h-10">
                    <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} />
                    <span>{f.hint}</span>
                  </label>
                ) : (
                  <Input type={f.type || "text"} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid={`${testId}-save`}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------
// Route Master
// ------------------------------------------------------------
export function RouteMaster() {
  return (
    <MasterShell
      testId="route-master-page"
      title="Route Master"
      subtitle="Predefined origin → destination routes with distance & time estimates."
      icon={<RouteIcon className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/routes"
      empty={{ name: "", origin: "", destination: "", distance_km: "", est_hours: "", toll_estimate: "", remarks: "", active: true }}
      columns={[
        { key: "route_code", label: "Code", className: "font-mono text-xs" },
        { key: "name", label: "Name" },
        { key: "origin", label: "Origin" },
        { key: "destination", label: "Destination" },
        { key: "distance_km", label: "Distance (km)", align: "right" },
        { key: "est_hours", label: "Est. Hours", align: "right" },
      ]}
      formFields={[
        { key: "name", label: "Route Name *", full: true },
        { key: "origin", label: "Origin *" },
        { key: "destination", label: "Destination *" },
        { key: "distance_km", label: "Distance (km)", type: "number" },
        { key: "est_hours", label: "Est. Hours", type: "number" },
        { key: "toll_estimate", label: "Toll Estimate (₹)", type: "number" },
        { key: "active", label: "Active?", type: "checkbox", hint: "Route is active" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

// ------------------------------------------------------------
// Loading / Unloading Points
// ------------------------------------------------------------
export function LoadingUnloadingPoints() {
  return (
    <MasterShell
      testId="loading-points-page"
      title="Loading / Unloading Points"
      subtitle="Registered loading and unloading points with contact information."
      icon={<MapPin className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/loading-points"
      empty={{ name: "", kind: "both", address: "", contact_person: "", contact_no: "", site_location: "", remarks: "", active: true }}
      columns={[
        { key: "name", label: "Name" },
        { key: "kind", label: "Kind" },
        { key: "contact_person", label: "Contact" },
        { key: "contact_no", label: "Phone" },
        { key: "site_location", label: "Site" },
      ]}
      formFields={[
        { key: "name", label: "Point Name *", full: true },
        { key: "kind", label: "Kind", type: "select", options: ["loading", "unloading", "both"] },
        { key: "site_location", label: "Site Location" },
        { key: "contact_person", label: "Contact Person" },
        { key: "contact_no", label: "Contact No." },
        { key: "address", label: "Address", type: "textarea", full: true },
        { key: "active", label: "Active?", type: "checkbox", hint: "Point is active" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

// ------------------------------------------------------------
// Dispatch Types
// ------------------------------------------------------------
export function DispatchTypes() {
  return (
    <MasterShell
      testId="dispatch-types-page"
      title="Dispatch Types"
      subtitle="Material / Manpower / Equipment / Return categories used when raising a dispatch."
      icon={<Package className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/dispatch-types"
      empty={{ name: "", category: "material", description: "", active: true }}
      columns={[
        { key: "name", label: "Name" },
        { key: "category", label: "Category" },
        { key: "description", label: "Description" },
      ]}
      formFields={[
        { key: "name", label: "Name *", full: true },
        { key: "category", label: "Category", type: "select", options: ["material", "manpower", "equipment", "return", "other"] },
        { key: "active", label: "Active?", type: "checkbox", hint: "Type is active" },
        { key: "description", label: "Description", type: "textarea", full: true },
      ]}
    />
  );
}

// ------------------------------------------------------------
// Transport Vendor Profiles (overlay on procurement vendor)
// ------------------------------------------------------------
export function TransportVendorProfiles() {
  return (
    <MasterShell
      testId="vendor-profile-page"
      title="Transport Vendor Profiles"
      subtitle="Overlay on procurement vendors with logistics-specific fields (rate agreement, vehicle types, service areas)."
      icon={<Truck className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/vendor-profiles"
      extraPreload={[{ key: "vendors", path: "/vendors" }]}
      empty={{ vendor_id: "", vendor_kind: "transporter", rate_agreement_ref: "", rate_agreement_valid_till: "", insurance_valid_till: "", remarks: "", active: true }}
      columns={[
        { key: "vendor_name", label: "Vendor" },
        { key: "vendor_kind", label: "Kind" },
        { key: "rate_agreement_ref", label: "Rate Agreement" },
        { key: "rate_agreement_valid_till", label: "Rate Valid Till" },
        { key: "insurance_valid_till", label: "Insurance Till" },
      ]}
      formFields={[
        { key: "vendor_id", label: "Vendor *", type: "select-preload", preloadKey: "vendors" },
        { key: "vendor_kind", label: "Kind", type: "select", options: ["transporter", "crane_vendor", "loading_unloading", "equipment_rental"] },
        { key: "rate_agreement_ref", label: "Rate Agreement Ref" },
        { key: "rate_agreement_valid_till", label: "Rate Valid Till", type: "date" },
        { key: "insurance_valid_till", label: "Insurance Valid Till", type: "date" },
        { key: "active", label: "Active?", type: "checkbox", hint: "Profile is active" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}
