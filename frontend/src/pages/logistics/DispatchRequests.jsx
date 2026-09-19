/**
 * Dispatch Requests (Phase 1) — basic register with type/project/from-to,
 * status lifecycle (draft → pending_approval → approved → allocated →
 * in_transit → delivered → closed). Full lifecycle in Phase 2.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Truck, Plus, RefreshCcw, Pencil, ExternalLink } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const STATUSES = ["draft", "pending_approval", "approved", "allocated", "in_transit", "delivered", "closed", "cancelled", "rejected"];
const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  allocated: "bg-blue-100 text-blue-800",
  in_transit: "bg-amber-100 text-amber-800",
  delivered: "bg-emerald-100 text-emerald-800",
  closed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-red-100 text-red-800",
  rejected: "bg-red-100 text-red-800",
};
const PRIORITIES = ["low", "normal", "high", "urgent"];

const EMPTY = {
  dispatch_type: "material",
  project_id: "", project_code: "",
  from_point_id: "", from_point_name: "",
  to_point_id: "", to_point_name: "",
  route_id: "",
  required_date: "",
  material_summary: "",
  approx_weight_mt: "",
  approx_qty: "",
  vehicle_type_preferred: "",
  priority: "normal",
  requested_by: "",
  remarks: "",
  status: "draft",
};

export default function DispatchRequests() {
  const [rows, setRows] = useState([]);
  const [types, setTypes] = useState([]);
  const [projects, setProjects] = useState([]);
  const [points, setPoints] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [statusFilter, setStatusFilter] = useState("");

  const load = async () => {
    try {
      const q = statusFilter ? `?status=${statusFilter}` : "";
      const [a, b, c, d, e] = await Promise.all([
        api.get(`/logistics/dispatch-requests${q}`),
        api.get("/logistics/dispatch-types"),
        lookupGet("/projects"),
        api.get("/logistics/loading-points"),
        api.get("/logistics/routes"),
      ]);
      setRows(a.data || []); setTypes(b.data || []); setProjects(c.data || []);
      setPoints(d.data || []); setRoutes(e.data || []);
    } catch (err) { toast.error(err.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [statusFilter]);

  const save = async () => {
    try {
      const payload = { ...form };
      if (payload.approx_weight_mt === "") delete payload.approx_weight_mt;
      else payload.approx_weight_mt = Number(payload.approx_weight_mt);
      if (!payload.required_date) delete payload.required_date;
      if (editing?.id) await api.put(`/logistics/dispatch-requests/${editing.id}`, payload);
      else await api.post(`/logistics/dispatch-requests`, payload);
      toast.success(editing?.id ? "Updated" : "Created");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="dispatch-requests-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Logistics · Phase 1</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Truck className="h-6 w-6 text-blue-600" /> Dispatch Requests
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Material · Manpower · Equipment · Return movement dispatch register. Approved dispatches cannot be hard-deleted.
          </p>
        </div>
        <div className="flex gap-2">
          <select className="border rounded h-10 px-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="dr-filter">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="dr-new">
            <Plus className="h-4 w-4 mr-1" /> New Request
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">DR #</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Project</th>
                <th className="text-left px-3 py-2">From → To</th>
                <th className="text-left px-3 py-2">Required</th>
                <th className="text-left px-3 py-2">Priority</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={8} className="text-center py-8 text-slate-400">No dispatch requests yet.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`dr-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono text-xs">{r.dr_no}</td>
                  <td className="px-3 py-2 capitalize">{r.dispatch_type}</td>
                  <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.from_point_name || "—"} <span className="text-slate-400">→</span> {r.to_point_name || "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">{r.required_date || "—"}</td>
                  <td className="px-3 py-2 text-xs capitalize">{r.priority}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[r.status] || "bg-slate-100"}`}>
                      {(r.status || "").replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <a href={`/app/logistics/dispatch-requests/${r.id}`} data-testid={`dr-open-${r.id}`}>
                      <Button size="sm" variant="outline"><ExternalLink className="h-3 w-3 mr-1" />Open</Button>
                    </a>
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`dr-edit-${r.id}`}>
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
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Dispatch Request</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Dispatch Type</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.dispatch_type} onChange={(e) => setForm({ ...form, dispatch_type: e.target.value })} data-testid="dr-type">
                {["material", "manpower", "equipment", "return", "other"].map((t) => <option key={t} value={t}>{t}</option>)}
                {types.filter((tt) => !["material", "manpower", "equipment", "return", "other"].includes(tt.category)).map((t) => (
                  <option key={t.id} value={t.category}>{t.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label>Priority</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }}>
                <option value="">— None —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Required Date</Label>
              <Input type="date" value={form.required_date} onChange={(e) => setForm({ ...form, required_date: e.target.value })} />
            </div>
            <div>
              <Label>From (Loading Point)</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.from_point_id} onChange={(e) => {
                const p = points.find((x) => x.id === e.target.value);
                setForm({ ...form, from_point_id: e.target.value, from_point_name: p?.name || "" });
              }}>
                <option value="">—</option>
                {points.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>To (Unloading Point)</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.to_point_id} onChange={(e) => {
                const p = points.find((x) => x.id === e.target.value);
                setForm({ ...form, to_point_id: e.target.value, to_point_name: p?.name || "" });
              }}>
                <option value="">—</option>
                {points.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Route (Optional)</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.route_id} onChange={(e) => setForm({ ...form, route_id: e.target.value })}>
                <option value="">—</option>
                {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Preferred Vehicle Type</Label>
              <Input value={form.vehicle_type_preferred} onChange={(e) => setForm({ ...form, vehicle_type_preferred: e.target.value })} placeholder="truck / hydra / …" />
            </div>
            <div><Label>Approx. Weight (MT)</Label><Input type="number" value={form.approx_weight_mt} onChange={(e) => setForm({ ...form, approx_weight_mt: e.target.value })} /></div>
            <div><Label>Approx. Quantity</Label><Input value={form.approx_qty} onChange={(e) => setForm({ ...form, approx_qty: e.target.value })} placeholder="e.g. 500 pipes" /></div>
            <div className="col-span-2"><Label>Material / Manpower Summary</Label><Textarea rows={2} value={form.material_summary} onChange={(e) => setForm({ ...form, material_summary: e.target.value })} /></div>
            <div><Label>Requested By</Label><Input value={form.requested_by} onChange={(e) => setForm({ ...form, requested_by: e.target.value })} /></div>
            <div>
              <Label>Status</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="dr-status">
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div className="col-span-2"><Label>Remarks</Label><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="dr-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
