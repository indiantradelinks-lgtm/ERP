import { useEffect, useMemo, useState } from "react";
import { Plus, Send, Search, X, Briefcase, Package, HardHat, Users, Building2, Car, UserCog, ClipboardList, Wrench, MoreHorizontal, CheckCircle2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { toast } from "sonner";
import { SiteLocationSelect } from "@/components/MasterSelect";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import SubmitWithDocsDialog from "@/components/SubmitWithDocsDialog";
import ApprovalDocsGate, { validateApprovalDocs, emptyApprovalDocs } from "@/components/ApprovalDocsGate";
import { lookupGet } from "@/lib/lookups";

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
const MATERIAL_TYPES = ["asset", "consumable", "ppe", "tool"];
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
  const [creating, setCreating] = useState(false);
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
    lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const filtered = useMemo(() => (rows || []).filter((r) => {
    if (filterStatus !== "all" && r.status !== filterStatus) return false;
    if (filterType !== "all" && r.resource_type !== filterType) return false;
    if (q) {
      const s = q.toLowerCase();
      return (r.rr_no || "").toLowerCase().includes(s)
        || (r.item_name || "").toLowerCase().includes(s)
        || (r.category || "").toLowerCase().includes(s)
        || (r.designation || "").toLowerCase().includes(s)
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
          <p className="text-sm text-slate-600 mt-1">Raise multiple requests at once — category-wise for materials & assets, designation-wise for manpower.</p>
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
            <Button onClick={() => setCreating(true)} data-testid="rr-new-btn">
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
              <th className="text-left px-3 py-2">Item / Designation</th>
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
              const sub = r.resource_type === "manpower" ? (r.designation && r.designation !== r.item_name ? r.designation : null) : r.category;
              return (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`rr-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono-data text-xs">{r.rr_no}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border ${meta?.tone}`}>
                      <Icon className="h-3 w-3" />{meta?.label}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{r.item_name}</div>
                    {sub && <div className="text-xs text-blue-700">{sub}</div>}
                    {r.justification && <div className="text-xs text-slate-500 truncate max-w-md">{r.justification}</div>}
                  </td>
                  <td className="px-3 py-2 text-xs">{r.project_name}</td>
                  <td className="px-3 py-2 text-right tabular">{r.quantity} <span className="text-slate-500">{r.unit}</span></td>
                  <td className="px-3 py-2 text-xs">{r.required_date || "—"}</td>
                  <td className="px-3 py-2 text-xs">{r.priority}</td>
                  <td className="px-3 py-2"><span className={`inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[r.status]}`}>{r.status?.replaceAll("_", " ")}</span></td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {(r.status === "draft" || r.status === "rejected") && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => setEditing(r)} data-testid={`rr-edit-${r.id}`}>Edit</Button>
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

      {creating && (
        <MultiRRDialog projects={projects} onClose={() => setCreating(false)} onSaved={() => { load(); setCreating(false); }} />
      )}
      {editing && (
        <EditRRDialog initial={editing} onClose={() => setEditing(null)} onSaved={() => { load(); setEditing(null); }} />
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


function emptyLine() {
  return { resource_type: "asset", category: "", item_name: "", custom_item: false, designation_id: "", quantity: 1, unit: "Nos" };
}

function MultiRRDialog({ projects, onClose, onSaved }) {
  const [head, setHead] = useState({ project_id: "", required_date: "", site_location: "", priority: "medium", justification: "", submit: true });
  const [docs, setDocs] = useState(emptyApprovalDocs());
  const [lines, setLines] = useState([emptyLine()]);
  const [cats, setCats] = useState([]);
  const [items, setItems] = useState([]);
  const [desigs, setDesigs] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/procurement/master/categories", { params: { active_only: true } }).then((r) => setCats(r.data || [])).catch(() => {});
    api.get("/procurement/master/items", { params: { active_only: true } }).then((r) => setItems(r.data || [])).catch(() => {});
    api.get("/ops/resource-requests/meta/designations").then((r) => setDesigs(r.data || [])).catch(() => {});
  }, []);

  const itemsByCat = useMemo(() => {
    const m = {};
    for (const it of items) { const k = it.category_name || ""; (m[k] = m[k] || []).push(it); }
    return m;
  }, [items]);

  const setHeadF = (k, v) => setHead((h) => ({ ...h, [k]: v }));
  const setLine = (i, patch) => setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, emptyLine()]);
  const removeLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));

  const onTypeChange = (i, t) => {
    setLine(i, {
      resource_type: t, category: "", item_name: "", custom_item: false, designation_id: "",
      unit: t === "manpower" ? "Persons" : "Nos",
    });
  };
  const onItemPick = (i, val, line) => {
    if (val === "__custom__") { setLine(i, { item_name: "", custom_item: true }); return; }
    const it = (itemsByCat[line.category] || []).find((x) => x.name === val);
    setLine(i, { item_name: val, custom_item: false, unit: it?.unit || line.unit });
  };

  const save = async () => {
    if (!head.project_id) { toast.error("Select a project"); return; }
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.resource_type === "manpower") {
        if (!l.designation_id) { toast.error(`Line ${i + 1}: select a designation`); return; }
      } else if (MATERIAL_TYPES.includes(l.resource_type)) {
        if (!l.category) { toast.error(`Line ${i + 1}: select a category`); return; }
        if (!l.item_name?.trim()) { toast.error(`Line ${i + 1}: select or enter an item`); return; }
      } else if (!l.item_name?.trim()) { toast.error(`Line ${i + 1}: enter the resource name`); return; }
      if (!(Number(l.quantity) > 0)) { toast.error(`Line ${i + 1}: quantity must be > 0`); return; }
    }
    if (head.submit) {
      const err = validateApprovalDocs(docs);
      if (err) { toast.error(err); return; }
    }
    setSaving(true);
    try {
      const payload = {
        project_id: head.project_id,
        required_date: head.required_date || null,
        site_location: head.site_location || null,
        priority: head.priority,
        justification: head.justification || null,
        submit: head.submit,
        ...(head.submit ? docs : {}),
        lines: lines.map((l) => ({
          resource_type: l.resource_type,
          item_name: l.item_name?.trim() || null,
          category: MATERIAL_TYPES.includes(l.resource_type) ? l.category || null : null,
          designation_id: l.resource_type === "manpower" ? l.designation_id || null : null,
          designation: l.resource_type === "manpower" ? (desigs.find((d) => d.id === l.designation_id)?.name || null) : null,
          quantity: Number(l.quantity),
          unit: l.unit || "Nos",
        })),
      };
      const r = await api.post("/ops/resource-requests/bulk", payload);
      const d = r.data;
      toast.success(`Created ${d.count} request${d.count > 1 ? "s" : ""}${d.submitted ? ` · ${d.submitted} submitted for approval` : " (draft)"}`);
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Resource Requests</DialogTitle>
          <DialogDescription>Add multiple lines — materials & assets by category, manpower by designation.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-4 gap-3">
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">Project *</Label>
            <select value={head.project_id} onChange={(e) => setHeadF("project_id", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-form-project">
              <option value="">— select project —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Required Date</Label>
            <Input type="date" value={head.required_date} onChange={(e) => setHeadF("required_date", e.target.value)} className="h-9 mt-1" data-testid="rr-form-date" />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Priority</Label>
            <select value={head.priority} onChange={(e) => setHeadF("priority", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-form-priority">
              {PRIO.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="col-span-2">
            <SiteLocationSelect label="Site Location" value={head.site_location}
              onChange={(v) => setHeadF("site_location", v)} testid="rr-form-site" />
          </div>
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">Justification / Remarks</Label>
            <Input value={head.justification} onChange={(e) => setHeadF("justification", e.target.value)} className="h-9 mt-1" data-testid="rr-form-justification" />
          </div>
        </div>

        <div className="mt-2">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-600">Request Lines ({lines.length})</div>
            <Button size="sm" variant="outline" onClick={addLine} data-testid="rr-add-line">
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Line
            </Button>
          </div>
          <div className="space-y-2">
            {lines.map((l, i) => {
              const isMat = MATERIAL_TYPES.includes(l.resource_type);
              const isMp = l.resource_type === "manpower";
              const catItems = itemsByCat[l.category] || [];
              return (
                <div key={i} className="border rounded-md bg-slate-50/60 px-3 py-2" data-testid={`rr-line-${i}`}>
                  <div className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-2">
                      <Label className="text-[10px] uppercase tracking-wider">Type</Label>
                      <select value={l.resource_type} onChange={(e) => onTypeChange(i, e.target.value)}
                               className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`rr-line-${i}-type`}>
                        {Object.entries(TYPE_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                      </select>
                    </div>

                    {isMat && (
                      <>
                        <div className="col-span-3">
                          <Label className="text-[10px] uppercase tracking-wider">Category *</Label>
                          <select value={l.category} onChange={(e) => setLine(i, { category: e.target.value, item_name: "", custom_item: false })}
                                   className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`rr-line-${i}-category`}>
                            <option value="">— category —</option>
                            {cats.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                          </select>
                        </div>
                        <div className="col-span-4">
                          <Label className="text-[10px] uppercase tracking-wider">Item *</Label>
                          {l.custom_item ? (
                            <div className="flex gap-1 mt-1">
                              <Input value={l.item_name} onChange={(e) => setLine(i, { item_name: e.target.value })}
                                      placeholder="Type custom item name" className="h-9" data-testid={`rr-line-${i}-custom-item`} autoFocus />
                              <Button size="sm" variant="ghost" className="h-9 px-2" title="Back to list"
                                       onClick={() => setLine(i, { custom_item: false, item_name: "" })}><X className="h-3.5 w-3.5" /></Button>
                            </div>
                          ) : (
                            <select value={l.item_name} onChange={(e) => onItemPick(i, e.target.value, l)} disabled={!l.category}
                                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50" data-testid={`rr-line-${i}-item`}>
                              <option value="">{l.category ? "— select item —" : "select category first"}</option>
                              {catItems.map((it) => <option key={it.id} value={it.name}>{it.name}</option>)}
                              <option value="__custom__">✎ Other / custom item…</option>
                            </select>
                          )}
                        </div>
                      </>
                    )}

                    {isMp && (
                      <div className="col-span-7">
                        <Label className="text-[10px] uppercase tracking-wider">Designation *</Label>
                        <select value={l.designation_id} onChange={(e) => setLine(i, { designation_id: e.target.value })}
                                 className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`rr-line-${i}-designation`}>
                          <option value="">— select designation —</option>
                          {desigs.map((d) => <option key={d.id} value={d.id}>{d.name}{d.code ? ` (${d.code})` : ""}</option>)}
                        </select>
                      </div>
                    )}

                    {!isMat && !isMp && (
                      <div className="col-span-7">
                        <Label className="text-[10px] uppercase tracking-wider">Resource / Requirement *</Label>
                        <Input value={l.item_name} onChange={(e) => setLine(i, { item_name: e.target.value })} className="h-9 mt-1" data-testid={`rr-line-${i}-name`} />
                      </div>
                    )}

                    <div className="col-span-1">
                      <Label className="text-[10px] uppercase tracking-wider">Qty *</Label>
                      <Input type="number" min="0" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} className="h-9 mt-1" data-testid={`rr-line-${i}-qty`} />
                    </div>
                    <div className="col-span-1">
                      <Label className="text-[10px] uppercase tracking-wider">Unit</Label>
                      <Input value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} className="h-9 mt-1" data-testid={`rr-line-${i}-unit`} />
                    </div>
                    <div className="col-span-1 flex justify-end">
                      <Button size="sm" variant="ghost" className="h-9 px-2" onClick={() => removeLine(i)} disabled={lines.length === 1}
                               data-testid={`rr-line-${i}-remove`}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {head.submit && (
          <div className="mt-3">
            <ApprovalDocsGate parentType="resource_requests" value={docs} onChange={setDocs} testidPrefix="rr-bulk-docs" />
          </div>
        )}

        <DialogFooter className="mt-4 flex items-center sm:justify-between gap-3">
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <Checkbox checked={head.submit} onCheckedChange={(v) => setHeadF("submit", !!v)} data-testid="rr-form-autosubmit" />
            Submit all for approval immediately
          </label>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Close</Button>
            <Button onClick={save} disabled={saving} data-testid="rr-save">
              <Send className="h-4 w-4 mr-1" />{saving ? "Saving…" : head.submit ? `Create & Submit ${lines.length} Request${lines.length > 1 ? "s" : ""}` : `Save ${lines.length} Draft${lines.length > 1 ? "s" : ""}`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function EditRRDialog({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({ ...initial });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    try {
      await api.put(`/ops/resource-requests/${form.id}`, {
        item_name: form.item_name, quantity: Number(form.quantity || 1), unit: form.unit,
        required_date: form.required_date || null, site_location: form.site_location || null,
        priority: form.priority, justification: form.justification || null,
      });
      toast.success("Updated");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit — {form.rr_no}</DialogTitle>
          <DialogDescription className="sr-only">Resource request</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 text-sm bg-blue-50 border border-blue-200 rounded px-3 py-2">
            {TYPE_META[form.resource_type]?.label} · {form.project_name}
            {form.category ? ` · ${form.category}` : ""}{form.designation ? ` · ${form.designation}` : ""}
          </div>
          <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Item / Resource Name *</Label>
            <Input value={form.item_name} onChange={(e) => set("item_name", e.target.value)} className="h-9 mt-1" data-testid="rr-form-item" />
          </div>
          <div><Label className="text-[10px] uppercase tracking-wider">Quantity</Label><Input type="number" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} className="h-9 mt-1" data-testid="rr-form-qty" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Unit</Label><Input value={form.unit} onChange={(e) => set("unit", e.target.value)} className="h-9 mt-1" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Required Date</Label><Input type="date" value={form.required_date || ""} onChange={(e) => set("required_date", e.target.value)} className="h-9 mt-1" /></div>
          <div><SiteLocationSelect label="Site Location" value={form.site_location || ""} onChange={(v) => set("site_location", v)} testid="rr-edit-site" /></div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Priority</Label>
            <select value={form.priority} onChange={(e) => set("priority", e.target.value)}
                     className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm">
              {PRIO.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Justification / Remarks</Label>
            <Textarea rows={3} value={form.justification || ""} onChange={(e) => set("justification", e.target.value)} className="mt-1" />
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button onClick={save} data-testid="rr-save"><Send className="h-4 w-4 mr-1" />Save</Button>
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
