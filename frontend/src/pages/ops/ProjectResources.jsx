/**
 * Project Resource Plan · P&O Phase 2 (Round 2)
 *
 * Unified resource planning UI with four tabs: Manpower, Material, Tools,
 * Sub-contract. Each row stored in `db.project_resources` with a
 * `resource_type` discriminator. Pickers are wired:
 *   • Manpower   → HR designations (/api/hr1/designations)
 *   • Material   → Procurement items (/api/procurement/master/items)
 *   • Sub-contract → Vendors        (/api/vendors)
 * Backend: /api/proj-phase2/resources/{project_id}
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Users, Package, Wrench, Briefcase, Plus, Pencil, Trash2, RefreshCcw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const EMPTY = {
  resource_type: "manpower",
  wbs_id: "", activity_id: "", required_by_date: "", remarks: "",
  // manpower
  designation_id: "", designation_name: "", count_required: 0, mandays: 0, daily_rate: 0,
  // material
  item_id: "", item_code: "", item_name: "", uom: "", quantity: 0, unit_rate: 0, source: "stock",
  // tools
  tool_name: "", tool_owned_or_rented: "owned", days: 0,
  // subcontract
  vendor_id: "", vendor_code: "", vendor_name: "", scope: "", basis: "lumpsum", value: 0,
};

const SOURCES = ["stock", "purchase", "client_supply"];
const TOOL_OOR = ["owned", "rented"];
const SUB_BASIS = ["lumpsum", "unit_rate"];

export default function ProjectResources() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [active, setActive]       = useState("manpower");
  const [rows, setRows]           = useState([]);
  const [summary, setSummary]     = useState({});
  const [wbsNodes, setWbsNodes]   = useState([]);
  const [activities, setActivities] = useState([]);
  // pickers
  const [designations, setDesignations] = useState([]);
  const [items, setItems]               = useState([]);
  const [vendors, setVendors]           = useState([]);
  // edit
  const [editing, setEditing] = useState(null);
  const [form, setForm]       = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
    api.get("/hr1/designations").then((r) => setDesignations(r.data || [])).catch(() => setDesignations([]));
    api.get("/procurement/master/items").then((r) => setItems(r.data || [])).catch(() => setItems([]));
    api.get("/vendors").then((r) => setVendors(r.data || [])).catch(() => setVendors([]));
  }, []);

  useEffect(() => {
    if (!projectId) { setRows([]); setSummary({}); setWbsNodes([]); setActivities([]); return; }
    load();
  }, [projectId, active]);

  const load = async () => {
    try {
      const [r, s, w, a] = await Promise.all([
        api.get(`/proj-phase2/resources/${projectId}`, { params: { type: active } }),
        api.get(`/proj-phase2/resources/${projectId}/summary`),
        api.get(`/proj-phase2/wbs/${projectId}`),
        api.get(`/proj-phase2/activities/${projectId}`),
      ]);
      setRows(r.data || []);
      setSummary(s.data || {});
      setWbsNodes(w.data || []);
      setActivities(a.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const openNew = () => { setEditing({}); setForm({ ...EMPTY, resource_type: active }); };
  const openEdit = (r) => { setEditing(r); setForm({ ...EMPTY, ...r, wbs_id: r.wbs_id || "", activity_id: r.activity_id || "" }); };

  const save = async () => {
    if (!projectId) { toast.error("Pick a project"); return; }
    const ok = validate(form);
    if (ok !== true) { toast.error(ok); return; }
    try {
      const payload = {
        ...form,
        resource_type: active,
        wbs_id: form.wbs_id || null,
        activity_id: form.activity_id || null,
        designation_id: form.designation_id || null,
        item_id: form.item_id || null,
        vendor_id: form.vendor_id || null,
        count_required: Number(form.count_required) || 0,
        mandays: Number(form.mandays) || 0,
        daily_rate: Number(form.daily_rate) || 0,
        quantity: Number(form.quantity) || 0,
        unit_rate: Number(form.unit_rate) || 0,
        days: Number(form.days) || 0,
        value: Number(form.value) || 0,
      };
      if (editing?.id) {
        await api.put(`/proj-phase2/resources/${editing.id}`, payload);
        toast.success("Resource updated");
      } else {
        await api.post(`/proj-phase2/resources/${projectId}`, payload);
        toast.success("Resource added");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm("Delete this resource line?")) return;
    try {
      await api.delete(`/proj-phase2/resources/${r.id}`);
      toast.success("Deleted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const wbsMap = useMemo(() => Object.fromEntries(wbsNodes.map((w) => [w.id, w])), [wbsNodes]);
  const actMap = useMemo(() => Object.fromEntries(activities.map((a) => [a.id, a])), [activities]);

  return (
    <div className="p-6 space-y-4" data-testid="page-project-resources">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="h-6 w-6 text-primary" /> Resource Planning
          </h1>
          <p className="text-sm text-muted-foreground">Plan manpower, materials, tools and sub-contractor work per project. Links to HR designations · Inventory items · Vendors.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm min-w-[260px]" data-testid="rp-project-select">
            <option value="">— select project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={!projectId}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
        </div>
      </div>

      {projectId && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard label="Manpower"  count={summary.manpower_count || 0}   amount={summary.manpower || 0}   tone="bg-blue-50 border-blue-200 text-blue-700" />
          <SummaryCard label="Material"  count={summary.material_count || 0}   amount={summary.material || 0}   tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
          <SummaryCard label="Tools"     count={summary.tools_count || 0}      amount={summary.tools || 0}      tone="bg-amber-50 border-amber-200 text-amber-700" />
          <SummaryCard label="Sub-Contract" count={summary.subcontract_count || 0} amount={summary.subcontract || 0} tone="bg-purple-50 border-purple-200 text-purple-700" />
          <SummaryCard label="Grand Total" count="" amount={summary.grand_total || 0} tone="bg-primary/5 border-primary/30 text-primary" highlight />
        </div>
      )}

      <Tabs value={active} onValueChange={setActive}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="manpower" data-testid="rp-tab-manpower"><Users className="h-3.5 w-3.5 mr-1" />Manpower</TabsTrigger>
            <TabsTrigger value="material" data-testid="rp-tab-material"><Package className="h-3.5 w-3.5 mr-1" />Material</TabsTrigger>
            <TabsTrigger value="tools" data-testid="rp-tab-tools"><Wrench className="h-3.5 w-3.5 mr-1" />Tools</TabsTrigger>
            <TabsTrigger value="subcontract" data-testid="rp-tab-subcontract"><Briefcase className="h-3.5 w-3.5 mr-1" />Sub-Contract</TabsTrigger>
          </TabsList>
          {canEdit && projectId && (
            <Button onClick={openNew} data-testid="rp-new"><Plus className="h-4 w-4 mr-1" /> Add {labelOf(active)}</Button>
          )}
        </div>

        <TabsContent value={active}>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">{labelOf(active)} Plan <span className="text-xs text-slate-400">({rows.length})</span></CardTitle></CardHeader>
            <CardContent>
              {!projectId ? (
                <div className="text-center py-10 text-slate-400">Select a project to view resource plan</div>
              ) : rows.length === 0 ? (
                <div className="text-center py-10 text-slate-400">No {active} entries — add the first row.</div>
              ) : (
                <div className="overflow-x-auto">
                  <ResourceTable
                    type={active} rows={rows} wbsMap={wbsMap} actMap={actMap}
                    canEdit={canEdit}
                    onEdit={openEdit} onRemove={remove}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "Add"} {labelOf(active)} Resource</DialogTitle></DialogHeader>
          <ResourceForm
            type={active} form={form} setForm={setForm}
            wbsNodes={wbsNodes} activities={activities}
            designations={designations} items={items} vendors={vendors}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="rp-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ──────────────────────────────── Sub-components ────────────────────────────────
function ResourceTable({ type, rows, wbsMap, actMap, canEdit, onEdit, onRemove }) {
  return (
    <table className="w-full text-sm">
      <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
        {type === "manpower" && (
          <>
            <th className="px-2 py-2">Designation</th>
            <th className="px-2 py-2 text-right">Count</th>
            <th className="px-2 py-2 text-right">Mandays</th>
            <th className="px-2 py-2 text-right">Daily Rate</th>
          </>
        )}
        {type === "material" && (
          <>
            <th className="px-2 py-2">Item</th>
            <th className="px-2 py-2">UOM</th>
            <th className="px-2 py-2 text-right">Qty</th>
            <th className="px-2 py-2 text-right">Rate</th>
            <th className="px-2 py-2">Source</th>
          </>
        )}
        {type === "tools" && (
          <>
            <th className="px-2 py-2">Tool</th>
            <th className="px-2 py-2">Type</th>
            <th className="px-2 py-2 text-right">Count</th>
            <th className="px-2 py-2 text-right">Days</th>
            <th className="px-2 py-2 text-right">Daily Rate</th>
          </>
        )}
        {type === "subcontract" && (
          <>
            <th className="px-2 py-2">Vendor</th>
            <th className="px-2 py-2">Scope</th>
            <th className="px-2 py-2">Basis</th>
            <th className="px-2 py-2 text-right">Value</th>
          </>
        )}
        <th className="px-2 py-2">WBS / Activity</th>
        <th className="px-2 py-2">By Date</th>
        <th className="px-2 py-2 text-right">Total Cost</th>
        <th className="px-2 py-2 text-right w-24"></th>
      </tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-b hover:bg-slate-50/50" data-testid={`rp-row-${r.id}`}>
            {type === "manpower" && (
              <>
                <td className="px-2 py-1">{r.designation_name || "—"}</td>
                <td className="px-2 py-1 text-right font-mono">{r.count_required || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{r.mandays || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.daily_rate || 0).toLocaleString("en-IN")}</td>
              </>
            )}
            {type === "material" && (
              <>
                <td className="px-2 py-1"><span className="font-mono text-xs text-primary mr-1">{r.item_code || ""}</span>{r.item_name || "—"}</td>
                <td className="px-2 py-1 text-xs">{r.uom || "—"}</td>
                <td className="px-2 py-1 text-right font-mono">{r.quantity || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.unit_rate || 0).toLocaleString("en-IN")}</td>
                <td className="px-2 py-1 text-xs">{r.source || "stock"}</td>
              </>
            )}
            {type === "tools" && (
              <>
                <td className="px-2 py-1">{r.tool_name || "—"}</td>
                <td className="px-2 py-1 text-xs">{r.tool_owned_or_rented || "—"}</td>
                <td className="px-2 py-1 text-right font-mono">{r.count_required || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{r.days || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.daily_rate || 0).toLocaleString("en-IN")}</td>
              </>
            )}
            {type === "subcontract" && (
              <>
                <td className="px-2 py-1"><span className="font-mono text-xs text-primary mr-1">{r.vendor_code || ""}</span>{r.vendor_name || "—"}</td>
                <td className="px-2 py-1">{r.scope || "—"}</td>
                <td className="px-2 py-1 text-xs">{r.basis || "—"}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.value || 0).toLocaleString("en-IN")}</td>
              </>
            )}
            <td className="px-2 py-1 text-xs">
              {r.wbs_id && wbsMap[r.wbs_id] ? <span className="font-mono">{wbsMap[r.wbs_id].code}</span> : ""}
              {r.activity_id && actMap[r.activity_id] ? <span className="ml-1 text-slate-500">/ {actMap[r.activity_id].code}</span> : ""}
              {(!r.wbs_id && !r.activity_id) && "—"}
            </td>
            <td className="px-2 py-1 text-xs">{r.required_by_date || "—"}</td>
            <td className="px-2 py-1 text-right font-mono font-semibold">{Number(r.total_cost || 0).toLocaleString("en-IN")}</td>
            <td className="px-2 py-1 text-right">
              {canEdit && (
                <div className="flex justify-end gap-1">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onEdit(r)} data-testid={`rp-edit-${r.id}`}><Pencil className="h-3.5 w-3.5"/></Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => onRemove(r)} data-testid={`rp-del-${r.id}`}><Trash2 className="h-3.5 w-3.5"/></Button>
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ResourceForm({ type, form, setForm, wbsNodes, activities, designations, items, vendors }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {type === "manpower" && (
        <>
          <F label="Designation *">
            <select value={form.designation_id || ""} onChange={(e) => {
              const id = e.target.value;
              const d = designations.find((x) => x.id === id);
              setForm({ ...form, designation_id: id, designation_name: d?.name || "" });
            }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-designation">
              <option value="">— select —</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
            </select>
          </F>
          <F label="Count Required"><Input type="number" value={form.count_required} onChange={(e) => setForm({ ...form, count_required: e.target.value })} /></F>
          <F label="Mandays"><Input type="number" value={form.mandays} onChange={(e) => setForm({ ...form, mandays: e.target.value })} /></F>
          <F label="Daily Rate (₹)"><Input type="number" value={form.daily_rate} onChange={(e) => setForm({ ...form, daily_rate: e.target.value })} data-testid="rp-form-daily-rate" /></F>
        </>
      )}
      {type === "material" && (
        <>
          <F label="Item *" full>
            <select value={form.item_id || ""} onChange={(e) => {
              const id = e.target.value;
              const it = items.find((x) => x.id === id);
              setForm({
                ...form, item_id: id,
                item_code: it?.code || "", item_name: it?.name || "",
                uom: it?.unit || form.uom,
                unit_rate: it?.last_rate || form.unit_rate,
              });
            }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-item">
              <option value="">— select item —</option>
              {items.map((i) => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}
            </select>
          </F>
          <F label="UOM"><Input value={form.uom} onChange={(e) => setForm({ ...form, uom: e.target.value })} /></F>
          <F label="Source">
            <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
              {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          <F label="Quantity"><Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} data-testid="rp-form-qty" /></F>
          <F label="Unit Rate (₹)"><Input type="number" value={form.unit_rate} onChange={(e) => setForm({ ...form, unit_rate: e.target.value })} /></F>
        </>
      )}
      {type === "tools" && (
        <>
          <F label="Tool / Equipment *" full><Input value={form.tool_name} onChange={(e) => setForm({ ...form, tool_name: e.target.value })} placeholder="Welding Machine / Scaffold Frame …" data-testid="rp-form-tool" /></F>
          <F label="Owned / Rented">
            <select value={form.tool_owned_or_rented} onChange={(e) => setForm({ ...form, tool_owned_or_rented: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
              {TOOL_OOR.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          <F label="Count"><Input type="number" value={form.count_required} onChange={(e) => setForm({ ...form, count_required: e.target.value })} /></F>
          <F label="Days"><Input type="number" value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} /></F>
          <F label="Daily Rate (₹)"><Input type="number" value={form.daily_rate} onChange={(e) => setForm({ ...form, daily_rate: e.target.value })} /></F>
        </>
      )}
      {type === "subcontract" && (
        <>
          <F label="Vendor *">
            <select value={form.vendor_id || ""} onChange={(e) => {
              const id = e.target.value;
              const v = vendors.find((x) => x.id === id);
              setForm({ ...form, vendor_id: id, vendor_code: v?.vendor_code || "", vendor_name: v?.name || "" });
            }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-vendor">
              <option value="">— select vendor —</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.vendor_code} · {v.name}</option>)}
            </select>
          </F>
          <F label="Basis">
            <select value={form.basis} onChange={(e) => setForm({ ...form, basis: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
              {SUB_BASIS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          <F label="Scope of Work" full><Textarea rows={2} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} /></F>
          <F label="Value (₹)"><Input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} data-testid="rp-form-value" /></F>
        </>
      )}

      <F label="WBS Node">
        <select value={form.wbs_id || ""} onChange={(e) => setForm({ ...form, wbs_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
          <option value="">— none —</option>
          {wbsNodes.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
        </select>
      </F>
      <F label="Activity">
        <select value={form.activity_id || ""} onChange={(e) => setForm({ ...form, activity_id: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
          <option value="">— none —</option>
          {activities.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}
        </select>
      </F>
      <F label="Required By"><Input type="date" value={form.required_by_date || ""} onChange={(e) => setForm({ ...form, required_by_date: e.target.value })} /></F>
      <F label="Remarks" full><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
    </div>
  );
}

function SummaryCard({ label, count, amount, tone, highlight }) {
  return (
    <div className={`border rounded-sm p-3 ${tone}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-80">{label}</div>
      <div className={`${highlight ? "text-xl" : "text-lg"} font-bold truncate`}>₹ {Number(amount || 0).toLocaleString("en-IN")}</div>
      {count !== "" && <div className="text-[10px] opacity-70">{count} line{count === 1 ? "" : "s"}</div>}
    </div>
  );
}

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function labelOf(t) {
  return ({ manpower: "Manpower", material: "Material", tools: "Tools", subcontract: "Sub-Contract" })[t] || t;
}
function validate(f) {
  if (f.resource_type === "manpower" && !f.designation_id) return "Pick a designation";
  if (f.resource_type === "material" && !f.item_id) return "Pick a material item";
  if (f.resource_type === "tools" && !f.tool_name?.trim()) return "Tool name is required";
  if (f.resource_type === "subcontract" && !f.vendor_id) return "Pick a vendor";
  return true;
}
