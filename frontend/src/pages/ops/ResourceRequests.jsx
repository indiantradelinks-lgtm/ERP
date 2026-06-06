import { useEffect, useMemo, useState } from "react";
import { Plus, Send, Search, X, Briefcase, Package, HardHat, ShieldAlert, Users, Building2, Car, UserCog, ClipboardList, Wrench, MoreHorizontal, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import SubmitWithDocsDialog from "@/components/SubmitWithDocsDialog";

const TYPE_META = {
  asset:         { label: "Asset",         icon: Package,       tone: "bg-purple-100 text-purple-800 border-purple-300" },
  consumable:    { label: "Consumable",    icon: Package,       tone: "bg-blue-100 text-blue-800 border-blue-300" },
  ppe:           { label: "PPE",           icon: HardHat,       tone: "bg-yellow-100 text-yellow-800 border-yellow-300" },
  manpower:      { label: "Manpower",      icon: Users,         tone: "bg-green-100 text-green-800 border-green-300" },
  accommodation: { label: "Accommodation", icon: Building2,     tone: "bg-indigo-100 text-indigo-800 border-indigo-300" },
  vehicle:       { label: "Vehicle",       icon: Car,           tone: "bg-cyan-100 text-cyan-800 border-cyan-300" },
  admin:         { label: "Admin Support", icon: ClipboardList, tone: "bg-orange-100 text-orange-800 border-orange-300" },
  driver:        { label: "Driver",        icon: UserCog,       tone: "bg-amber-100 text-amber-800 border-amber-300" },
  tool:          { label: "Tools",         icon: Wrench,        tone: "bg-slate-100 text-slate-800 border-slate-300" },
  other:         { label: "Other",         icon: MoreHorizontal,tone: "bg-zinc-100 text-zinc-800 border-zinc-300" },
};
const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  submitted: "bg-amber-100 text-amber-800 border-amber-300",
  pending_approval: "bg-amber-100 text-amber-800 border-amber-300",
  approved: "bg-green-100 text-green-800 border-green-300",
  rejected: "bg-red-100 text-red-700 border-red-300",
  in_progress: "bg-blue-100 text-blue-800 border-blue-300",
  completed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  cancelled: "bg-zinc-100 text-zinc-600 border-zinc-300",
};
const PRIO = ["low", "medium", "high", "critical"];

function empty() {
  return { project_id: "", resource_type: "asset", item_name: "", quantity: 1, unit: "Nos",
    required_date: "", site_location: "", priority: "medium", justification: "", attachments: [] };
}

const SERVICE_OWNER_ROLES = {
  asset: "store_incharge", consumable: "store_incharge", ppe: "store_incharge", tool: "store_incharge",
  manpower: "hr_executive",
  accommodation: "admin_executive", vehicle: "admin_executive", admin: "admin_executive",
  driver: "admin_executive", other: "admin_executive",
};

export default function ResourceRequests() {
  const { user } = useAuth();
  const role = user?.role;
  const isPM = ["project_manager", "project_coordinator", "super_admin", "director", "general_manager", "dept_head"].includes(role);

  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [q, setQ] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterType, setFilterType] = useState("all");
  const [editing, setEditing] = useState(null);
  const [svcFor, setSvcFor] = useState(null);
  const [submitFor, setSubmitFor] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/ops/resource-requests");
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => {
    load();
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const filtered = useMemo(() => (rows || []).filter((r) => {
    if (filterStatus !== "all" && r.status !== filterStatus) return false;
    if (filterType !== "all" && r.resource_type !== filterType) return false;
    if (q) {
      const s = q.toLowerCase();
      return (r.rr_no || "").toLowerCase().includes(s)
        || (r.item_name || "").toLowerCase().includes(s)
        || (r.project_name || "").toLowerCase().includes(s);
    }
    return true;
  }), [rows, q, filterStatus, filterType]);

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.rr_no}?`)) return;
    try { await api.delete(`/ops/resource-requests/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const submit = async (r) => { setSubmitFor(r); };
  const cancel = async (r) => {
    if (!window.confirm(`Cancel ${r.rr_no}?`)) return;
    try { await api.post(`/ops/resource-requests/${r.id}/cancel`); toast.success("Cancelled"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Cancel failed"); }
  };
  const canService = (r) => {
    const owner = SERVICE_OWNER_ROLES[r.resource_type];
    return ["super_admin", "director", "general_manager", "dept_head", owner].includes(role);
  };

  return (
    <div className="p-6 space-y-4" data-testid="rr-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
          <h1 className="font-display font-black text-3xl tracking-tight">Resource Requests</h1>
          <p className="text-sm text-slate-600 mt-1">Project Managers raise requests for assets, consumables, PPE, manpower, vehicles & admin support.</p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-40"><SelectValue placeholder="Type" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              {Object.entries(TYPE_META).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-40"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.keys(STATUS_TONE).map((s) => <SelectItem key={s} value={s}>{s.replaceAll("_", " ")}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input placeholder="No. / item / project" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8 w-64" data-testid="rr-search" />
          </div>
          {isPM && (
            <Button onClick={() => setEditing({ open: true, mode: "create", data: empty() })} data-testid="rr-new-btn">
              <Plus className="h-4 w-4 mr-1" /> New Request
            </Button>
          )}
        </div>
      </div>

      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">No.</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Item</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-left px-3 py-2">Required</th>
              <th className="text-left px-3 py-2">Priority</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="text-center py-8 text-slate-500 text-sm">No resource requests yet.</td></tr>
            )}
            {filtered.map((r) => {
              const meta = TYPE_META[r.resource_type];
              const Icon = meta?.icon || Briefcase;
              return (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`rr-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono-data text-xs">{r.rr_no}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border ${meta?.tone}`}>
                      <Icon className="h-3 w-3" />{meta?.label}
                    </span>
                  </td>
                  <td className="px-3 py-2"><div className="font-medium">{r.item_name}</div>{r.justification && <div className="text-xs text-slate-500 truncate max-w-md">{r.justification}</div>}</td>
                  <td className="px-3 py-2 text-xs">{r.project_name}</td>
                  <td className="px-3 py-2 text-right tabular">{r.quantity} <span className="text-slate-500">{r.unit}</span></td>
                  <td className="px-3 py-2 text-xs">{r.required_date || "—"}</td>
                  <td className="px-3 py-2 text-xs">{r.priority}</td>
                  <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[r.status]}`}>{r.status?.replaceAll("_", " ")}</span></td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {(r.status === "draft" || r.status === "rejected") && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => setEditing({ open: true, mode: "edit", data: r })} data-testid={`rr-edit-${r.id}`}>Edit</Button>
                          <Button size="sm" onClick={() => submit(r)} data-testid={`rr-submit-${r.id}`}><Send className="h-3 w-3 mr-1" /> Submit</Button>
                        </>
                      )}
                      {(r.status === "approved" || r.status === "in_progress") && canService(r) && (
                        <Button size="sm" onClick={() => setSvcFor(r)} data-testid={`rr-service-${r.id}`}><CheckCircle2 className="h-3 w-3 mr-1" /> {r.status === "approved" ? "Start" : "Complete"}</Button>
                      )}
                      {!["completed", "cancelled"].includes(r.status) && (
                        <Button size="sm" variant="ghost" onClick={() => cancel(r)} title="Cancel"><X className="h-3.5 w-3.5" /></Button>
                      )}
                      {r.status === "draft" && (
                        <Button size="sm" variant="ghost" onClick={() => remove(r)}><X className="h-3.5 w-3.5 text-red-600" /></Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editing?.open && (
        <RRDialog mode={editing.mode} initial={editing.data} projects={projects}
                   onClose={() => setEditing(null)} onSaved={() => { load(); setEditing(null); }} />
      )}
      {svcFor && (
        <ServiceDialog rr={svcFor} onClose={() => setSvcFor(null)} onSaved={() => { load(); setSvcFor(null); }} />
      )}

      <SubmitWithDocsDialog
        open={!!submitFor}
        onOpenChange={(o) => !o && setSubmitFor(null)}
        title="Submit Resource Request for Approval"
        description={submitFor && `${submitFor.rr_no} · ${submitFor.resource_type} · ${submitFor.item_name || ""}`}
        endpoint={submitFor ? `/ops/resource-requests/${submitFor.id}/submit` : null}
        parentType="resource_requests"
        parentId={submitFor?.id}
        ctaLabel="Submit RR"
        onSuccess={() => { setSubmitFor(null); load(); }}
        testidPrefix="rr-submit-docs"
      />
    </div>
  );
}


function RRDialog({ mode, initial, projects, onClose, onSaved }) {
  const isNew = mode === "create";
  const [form, setForm] = useState({ ...empty(), ...initial });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    try {
      const payload = { ...form };
      delete payload.id; delete payload.rr_no; delete payload.status;
      delete payload.created_at; delete payload.updated_at; delete payload.requested_by;
      delete payload.requested_by_id; delete payload.project_name;
      delete payload.project_manager_id; delete payload.project_coordinator_id;
      delete payload.approval_id;
      payload.quantity = Number(payload.quantity || 1);
      if (isNew) {
        const r = await api.post("/ops/resource-requests", payload);
        toast.success(`Created ${r.data.rr_no}`);
      } else {
        await api.put(`/ops/resource-requests/${form.id}`, payload);
        toast.success("Updated");
      }
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isNew ? "New Resource Request" : `Edit — ${form.rr_no}`}</DialogTitle>
          <DialogDescription className="sr-only">Resource request</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Project *</Label>
            <select value={form.project_id} onChange={(e) => set("project_id", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-form-project">
              <option value="">— select project —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Resource Type *</Label>
            <select value={form.resource_type} onChange={(e) => set("resource_type", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-form-type">
              {Object.entries(TYPE_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Item / Resource Name *</Label>
            <Input value={form.item_name} onChange={(e) => set("item_name", e.target.value)} className="h-9 mt-1" data-testid="rr-form-item" />
          </div>
          <div><Label className="text-[10px] uppercase tracking-wider">Quantity</Label><Input type="number" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} className="h-9 mt-1" data-testid="rr-form-qty" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Unit</Label><Input value={form.unit} onChange={(e) => set("unit", e.target.value)} className="h-9 mt-1" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Required Date</Label><Input type="date" value={form.required_date} onChange={(e) => set("required_date", e.target.value)} className="h-9 mt-1" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Site Location</Label><Input value={form.site_location} onChange={(e) => set("site_location", e.target.value)} className="h-9 mt-1" /></div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Priority</Label>
            <select value={form.priority} onChange={(e) => set("priority", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm">
              {PRIO.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Justification / Remarks</Label>
            <Textarea rows={3} value={form.justification} onChange={(e) => set("justification", e.target.value)} className="mt-1" />
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button onClick={save} data-testid="rr-save"><Send className="h-4 w-4 mr-1" />Save Draft</Button>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function ServiceDialog({ rr, onClose, onSaved }) {
  const [form, setForm] = useState({ status: rr.status === "approved" ? "in_progress" : "completed", actual_quantity: rr.actual_quantity || rr.quantity, cost: rr.actual_cost || 0, remarks: "" });
  const submit = async () => {
    try {
      await api.post(`/ops/resource-requests/${rr.id}/service`, { ...form, actual_quantity: Number(form.actual_quantity || 0), cost: Number(form.cost || 0) });
      toast.success("Updated");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Service Request — {rr.rr_no}</DialogTitle>
          <DialogDescription className="sr-only">Update service status</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-sm bg-blue-50 border border-blue-200 rounded px-3 py-2">{rr.item_name} · {rr.quantity} {rr.unit} · {rr.project_name}</div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Action</Label>
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="svc-status">
              <option value="in_progress">Mark In Progress</option>
              <option value="completed">Mark Completed</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">Actual Quantity</Label><Input type="number" value={form.actual_quantity} onChange={(e) => setForm({ ...form, actual_quantity: e.target.value })} className="h-9 mt-1" data-testid="svc-qty" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Actual Cost (₹)</Label><Input type="number" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} className="h-9 mt-1" data-testid="svc-cost" /></div>
          </div>
          <div><Label className="text-[10px] uppercase tracking-wider">Remarks</Label><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="mt-1" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button onClick={submit} data-testid="svc-submit"><CheckCircle2 className="h-4 w-4 mr-1" />Save</Button>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
