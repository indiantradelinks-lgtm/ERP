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
import { SiteLocationSelect } from "@/components/MasterSelect";
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
import { Users, Package, Wrench, Briefcase, Plus, Pencil, Trash2, RefreshCcw, Send, FileSpreadsheet, FileText } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import ApprovalDocsGate, { validateApprovalDocs, emptyApprovalDocs } from "@/components/ApprovalDocsGate";
import { BulkUploadDialog, QuickQtyDialog } from "./ResourcePlanBulkDialogs";
import { useAuth } from "@/contexts/AuthContext";
import { fmtD } from "@/lib/datetime";

const EMPTY = {
  resource_type: "manpower",
  wbs_id: "", activity_id: "", required_by_date: "", remarks: "",
  // manpower
  designation_id: "", designation_name: "", count_required: 0, mandays: 0, daily_rate: 0,
  deploy_from: "", deploy_to: "", shift: "general", skill_level: "",
  // material
  item_id: "", item_code: "", item_name: "", category: "", uom: "", quantity: 0, unit_rate: 0, source: "stock",
  material_custom: false,
  // tools
  tool_name: "", tool_item_id: "", tool_category: "", specification: "", tool_owned_or_rented: "owned",
  rental_vendor_id: "", rental_vendor_name: "", mobilization_date: "", days: 0, tool_custom: false,
  // subcontract
  vendor_id: "", vendor_code: "", vendor_name: "", scope: "", basis: "lumpsum", value: 0,
  sub_qty: 0, sub_unit_rate: 0, work_start: "", work_end: "", contact_person: "", contact_phone: "",
  retention_pct: 0, payment_terms: "",
};

const SOURCES = ["stock", "purchase", "client_supply"];
const TOOL_OOR = ["owned", "rented"];
const SUB_BASIS = ["lumpsum", "unit_rate"];
const SHIFTS = ["general", "day", "night", "rotational"];
const SKILL_LEVELS = ["", "highly_skilled", "skilled", "semi_skilled", "unskilled"];

export default function ProjectResources() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [active, setActive]       = useState("manpower");
  const [exporting, setExporting] = useState("");

  const downloadReport = async (fmt) => {
    setExporting(fmt);
    try {
      const { data } = await api.get(`/proj-phase2/resources/${projectId}/export/${fmt}`, {
        responseType: "blob", params: { type: active },
      });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = `resource-plan-${active}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`${fmt === "xlsx" ? "Excel" : "PDF"} report downloaded`);
    } catch (e) { toast.error("Export failed"); }
    finally { setExporting(""); }
  };
  const [rows, setRows]           = useState([]);
  const [summary, setSummary]     = useState({});
  const [wbsNodes, setWbsNodes]   = useState([]);
  const [activities, setActivities] = useState([]);
  // pickers
  const [designations, setDesignations] = useState([]);
  const [items, setItems]               = useState([]);
  const [categories, setCategories]     = useState([]);
  const [vendors, setVendors]           = useState([]);
  // edit
  const [editing, setEditing] = useState(null);
  const [form, setForm]       = useState(EMPTY);
  const [selected, setSelected] = useState([]);
  const [convertOpen, setConvertOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
    // Designations via projects-scoped endpoint (active only) — /hr1/designations needs employees.read
    // which PM-adjacent roles (coordinator, site engineer, supervisor) don't have.
    api.get("/ops/resource-requests/meta/designations")
      .then((r) => setDesignations(r.data || []))
      .catch(() => {
        api.get("/hr1/designations")
          .then((r) => setDesignations((r.data || []).filter((d) => d.active !== false)))
          .catch(() => setDesignations([]));
      });
    api.get("/procurement/master/items").then((r) => setItems(r.data || [])).catch(() => setItems([]));
    api.get("/procurement/master/categories", { params: { active_only: true } }).then((r) => setCategories(r.data || [])).catch(() => setCategories([]));
    api.get("/vendors").then((r) => setVendors(r.data || [])).catch(() => setVendors([]));
  }, []);

  useEffect(() => {
    setSelected([]);
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

  const openNew = () => { setEditing({}); setForm({ ...EMPTY, resource_type: active, tool_category: active === "tools" ? "Tools and Tackles" : "" }); };
  const openEdit = (r) => {
    setEditing(r);
    setForm({
      ...EMPTY, ...r, wbs_id: r.wbs_id || "", activity_id: r.activity_id || "",
      material_custom: r.resource_type === "material" && !r.item_id && !!r.item_name,
      tool_custom: r.resource_type === "tools" && !r.tool_item_id && !!r.tool_name,
    });
  };

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
        tool_item_id: form.tool_item_id || null,
        vendor_id: form.vendor_id || null,
        rental_vendor_id: form.tool_owned_or_rented === "rented" ? (form.rental_vendor_id || null) : null,
        rental_vendor_name: form.tool_owned_or_rented === "rented" ? (form.rental_vendor_name || "") : "",
        count_required: Number(form.count_required) || 0,
        mandays: Number(form.mandays) || 0,
        daily_rate: Number(form.daily_rate) || 0,
        quantity: Number(form.quantity) || 0,
        unit_rate: Number(form.unit_rate) || 0,
        days: Number(form.days) || 0,
        sub_qty: Number(form.sub_qty) || 0,
        sub_unit_rate: Number(form.sub_unit_rate) || 0,
        retention_pct: Number(form.retention_pct) || 0,
        value: form.basis === "unit_rate"
          ? (Number(form.sub_qty) || 0) * (Number(form.sub_unit_rate) || 0)
          : Number(form.value) || 0,
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
  const convertible = active !== "subcontract" && canEdit;
  const toggleSelect = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  const selectedRows = rows.filter((r) => selected.includes(r.id));

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
          {projectId && (
            <div className="flex gap-2 mr-2">
              <Button size="sm" variant="outline" onClick={() => downloadReport("xlsx")} disabled={exporting === "xlsx"} data-testid="rp-export-xlsx" title="Excel report of this tab's resources">
                <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> {exporting === "xlsx" ? "Exporting…" : "Excel"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => downloadReport("pdf")} disabled={exporting === "pdf"} data-testid="rp-export-pdf" title="PDF report of this tab's resources">
                <FileText className="h-3.5 w-3.5 mr-1" /> {exporting === "pdf" ? "Exporting…" : "PDF"}
              </Button>
            </div>
          )}
          {canEdit && projectId && (
            <div className="flex gap-2">
              {convertible && selected.length > 0 && (
                <Button variant="outline" className="border-blue-300 text-blue-700 hover:bg-blue-50" onClick={() => setConvertOpen(true)} data-testid="rp-convert-btn">
                  <Send className="h-4 w-4 mr-1" /> Raise Request ({selected.length})
                </Button>
              )}
              <Button variant="outline" onClick={() => setQuickOpen(true)} data-testid="rp-quick-btn">Quick Qty Entry</Button>
              {active !== "subcontract" && (
                <Button variant="outline" onClick={() => setBulkOpen(true)} data-testid="rp-bulk-btn">Bulk Upload</Button>
              )}
              <Button onClick={openNew} data-testid="rp-new"><Plus className="h-4 w-4 mr-1" /> Add {labelOf(active)}</Button>
            </div>
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
                    selectable={convertible} selected={selected} onToggle={toggleSelect}
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
            designations={designations} items={items} categories={categories} vendors={vendors}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="rp-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {convertOpen && (
        <ConvertDialog
          projectId={projectId} rows={selectedRows} type={active}
          onClose={() => setConvertOpen(false)}
          onSaved={() => { setConvertOpen(false); setSelected([]); load(); }}
        />
      )}
      {bulkOpen && (
        <BulkUploadDialog
          projectId={projectId} type={active}
          onClose={() => setBulkOpen(false)}
          onSaved={() => { setBulkOpen(false); load(); }}
        />
      )}
      {quickOpen && (
        <QuickQtyDialog
          projectId={projectId} items={items} designations={designations}
          onClose={() => setQuickOpen(false)}
          onSaved={() => { setQuickOpen(false); load(); }}
        />
      )}
    </div>
  );
}

// ──────────────────────────────── Sub-components ────────────────────────────────
function ResourceTable({ type, rows, wbsMap, actMap, canEdit, selectable, selected, onToggle, onEdit, onRemove }) {
  return (
    <table className="w-full text-sm">
      <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
        {selectable && <th className="px-2 py-2 w-8"></th>}
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
            {selectable && (
              <td className="px-2 py-1">
                {r.converted_request_no ? (
                  <span className="inline-block px-1.5 py-0.5 text-[9px] font-bold rounded border bg-emerald-50 border-emerald-300 text-emerald-700 whitespace-nowrap" title={`Converted to ${r.converted_request_no}${r.converted_at ? ` on ${fmtD(r.converted_at)}` : ""}`} data-testid={`rp-converted-badge-${r.id}`}>
                    Converted → {r.converted_request_no}
                  </span>
                ) : r.rr_batch_id ? (
                  <span className="inline-block px-1.5 py-0.5 text-[9px] font-bold rounded border bg-green-50 border-green-300 text-green-700 whitespace-nowrap" title={`Requested as ${r.rr_no} (legacy)`} data-testid={`rp-rr-badge-${r.id}`}>Converted → {r.rr_no}</span>
                ) : (
                  <Checkbox checked={selected.includes(r.id)} onCheckedChange={() => onToggle(r.id)} data-testid={`rp-select-${r.id}`} />
                )}
              </td>
            )}
            {type === "manpower" && (
              <>
                <td className="px-2 py-1">
                  <div>{r.designation_name || "—"}</div>
                  <div className="text-[10px] text-slate-500">
                    {[r.skill_level?.replaceAll("_", " "), r.shift && r.shift !== "general" ? `${r.shift} shift` : null,
                      (r.deploy_from || r.deploy_to) ? `${r.deploy_from || "…"} → ${r.deploy_to || "…"}` : null]
                      .filter(Boolean).join(" · ")}
                  </div>
                </td>
                <td className="px-2 py-1 text-right font-mono">{r.count_required || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{r.mandays || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.daily_rate || 0).toLocaleString("en-IN")}</td>
              </>
            )}
            {type === "material" && (
              <>
                <td className="px-2 py-1">
                  <div><span className="font-mono text-xs text-primary mr-1">{r.item_code || ""}</span>{r.item_name || "—"}</div>
                  {r.category && <div className="text-[10px] text-blue-700">{r.category}</div>}
                </td>
                <td className="px-2 py-1 text-xs">{r.uom || "—"}</td>
                <td className="px-2 py-1 text-right font-mono">{r.quantity || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.unit_rate || 0).toLocaleString("en-IN")}</td>
                <td className="px-2 py-1 text-xs">{r.source || "stock"}</td>
              </>
            )}
            {type === "tools" && (
              <>
                <td className="px-2 py-1">
                  <div>{r.tool_name || "—"}</div>
                  <div className="text-[10px] text-slate-500">
                    {[r.tool_category, r.specification, r.mobilization_date ? `mob: ${r.mobilization_date}` : null].filter(Boolean).join(" · ")}
                  </div>
                </td>
                <td className="px-2 py-1 text-xs">
                  {r.tool_owned_or_rented || "—"}
                  {r.tool_owned_or_rented === "rented" && r.rental_vendor_name && <div className="text-[10px] text-slate-500">{r.rental_vendor_name}</div>}
                </td>
                <td className="px-2 py-1 text-right font-mono">{r.count_required || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{r.days || 0}</td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.daily_rate || 0).toLocaleString("en-IN")}</td>
              </>
            )}
            {type === "subcontract" && (
              <>
                <td className="px-2 py-1">
                  <div><span className="font-mono text-xs text-primary mr-1">{r.vendor_code || ""}</span>{r.vendor_name || "—"}</div>
                  <div className="text-[10px] text-slate-500">
                    {[(r.work_start || r.work_end) ? `${r.work_start || "…"} → ${r.work_end || "…"}` : null,
                      r.contact_person, r.retention_pct ? `retention ${r.retention_pct}%` : null].filter(Boolean).join(" · ")}
                  </div>
                </td>
                <td className="px-2 py-1">{r.scope || "—"}</td>
                <td className="px-2 py-1 text-xs">
                  {(r.basis || "—").replaceAll("_", " ")}
                  {r.basis === "unit_rate" && !!r.sub_qty && <div className="text-[10px] text-slate-500 font-mono">{r.sub_qty} × ₹{Number(r.sub_unit_rate || 0).toLocaleString("en-IN")}</div>}
                </td>
                <td className="px-2 py-1 text-right font-mono">{Number(r.total_cost || r.value || 0).toLocaleString("en-IN")}</td>
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

function ResourceForm({ type, form, setForm, wbsNodes, activities, designations, items, categories, vendors }) {
  const catItems = (cat) => items.filter((i) => (i.category_name || "") === cat);
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
              <option value="">{designations.length ? "— select —" : "No active designations — add via HR → Designations"}</option>
              {designations.map((d) => <option key={d.id} value={d.id}>{d.code ? `${d.code} · ` : ""}{d.name}</option>)}
            </select>
          </F>
          <F label="Skill Level">
            <select value={form.skill_level || ""} onChange={(e) => setForm({ ...form, skill_level: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-skill">
              {SKILL_LEVELS.map((s) => <option key={s} value={s}>{s ? s.replaceAll("_", " ") : "— not set —"}</option>)}
            </select>
          </F>
          <F label="Count Required"><Input type="number" value={form.count_required} onChange={(e) => setForm({ ...form, count_required: e.target.value })} /></F>
          <F label="Mandays"><Input type="number" value={form.mandays} onChange={(e) => setForm({ ...form, mandays: e.target.value })} /></F>
          <F label="Daily Rate (₹)"><Input type="number" value={form.daily_rate} onChange={(e) => setForm({ ...form, daily_rate: e.target.value })} data-testid="rp-form-daily-rate" /></F>
          <F label="Shift">
            <select value={form.shift || "general"} onChange={(e) => setForm({ ...form, shift: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-shift">
              {SHIFTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          <F label="Deploy From"><Input type="date" value={form.deploy_from || ""} onChange={(e) => setForm({ ...form, deploy_from: e.target.value })} data-testid="rp-form-deploy-from" /></F>
          <F label="Deploy To"><Input type="date" value={form.deploy_to || ""} onChange={(e) => setForm({ ...form, deploy_to: e.target.value })} data-testid="rp-form-deploy-to" /></F>
        </>
      )}
      {type === "material" && (
        <>
          <F label="Category *">
            <select value={form.category || ""} onChange={(e) => setForm({ ...form, category: e.target.value, item_id: "", item_code: "", item_name: "", material_custom: false })}
                     className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-category">
              <option value="">— select category —</option>
              {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </F>
          <F label="Item *">
            {form.material_custom ? (
              <div className="flex gap-1">
                <Input value={form.item_name} onChange={(e) => setForm({ ...form, item_name: e.target.value })} placeholder="Custom item name" data-testid="rp-form-custom-item" autoFocus />
                <Button size="sm" variant="ghost" className="h-9 px-2" title="Back to list" onClick={() => setForm({ ...form, material_custom: false, item_name: "", item_id: "" })}>✕</Button>
              </div>
            ) : (
              <select value={form.item_id || ""} onChange={(e) => {
                const id = e.target.value;
                if (id === "__custom__") { setForm({ ...form, item_id: "", item_code: "", item_name: "", material_custom: true }); return; }
                const it = items.find((x) => x.id === id);
                setForm({
                  ...form, item_id: id,
                  item_code: it?.code || "", item_name: it?.name || "",
                  uom: it?.unit || form.uom,
                  unit_rate: it?.last_rate || form.unit_rate,
                });
              }} disabled={!form.category} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50" data-testid="rp-form-item">
                <option value="">{form.category ? "— select item —" : "select category first"}</option>
                {catItems(form.category).map((i) => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}
                <option value="__custom__">✎ Other / custom item…</option>
              </select>
            )}
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
          <F label="Tool Category">
            <select value={form.tool_category || ""} onChange={(e) => setForm({ ...form, tool_category: e.target.value, tool_item_id: "", tool_name: form.tool_custom ? form.tool_name : "" })}
                     className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-tool-category">
              <option value="">— select category —</option>
              {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </F>
          <F label="Tool / Equipment *">
            {form.tool_custom ? (
              <div className="flex gap-1">
                <Input value={form.tool_name} onChange={(e) => setForm({ ...form, tool_name: e.target.value })} placeholder="Custom tool name" data-testid="rp-form-tool" autoFocus />
                <Button size="sm" variant="ghost" className="h-9 px-2" title="Back to list" onClick={() => setForm({ ...form, tool_custom: false, tool_name: "", tool_item_id: "" })}>✕</Button>
              </div>
            ) : (
              <select value={form.tool_item_id || ""} onChange={(e) => {
                const id = e.target.value;
                if (id === "__custom__") { setForm({ ...form, tool_item_id: "", tool_name: "", tool_custom: true }); return; }
                const it = items.find((x) => x.id === id);
                setForm({ ...form, tool_item_id: id, tool_name: it?.name || "" });
              }} disabled={!form.tool_category} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50" data-testid="rp-form-tool-item">
                <option value="">{form.tool_category ? "— select tool —" : "select category first"}</option>
                {catItems(form.tool_category).map((i) => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}
                <option value="__custom__">✎ Other / custom tool…</option>
              </select>
            )}
          </F>
          <F label="Specification" full><Input value={form.specification || ""} onChange={(e) => setForm({ ...form, specification: e.target.value })} placeholder="Capacity / size / model …" data-testid="rp-form-spec" /></F>
          <F label="Owned / Rented">
            <select value={form.tool_owned_or_rented} onChange={(e) => setForm({ ...form, tool_owned_or_rented: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-oor">
              {TOOL_OOR.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          {form.tool_owned_or_rented === "rented" && (
            <F label="Rental Vendor">
              <select value={form.rental_vendor_id || ""} onChange={(e) => {
                const id = e.target.value;
                const v = vendors.find((x) => x.id === id);
                setForm({ ...form, rental_vendor_id: id, rental_vendor_name: v?.name || "" });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-rental-vendor">
                <option value="">— select vendor —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.vendor_code} · {v.name}</option>)}
              </select>
            </F>
          )}
          <F label="Count"><Input type="number" value={form.count_required} onChange={(e) => setForm({ ...form, count_required: e.target.value })} /></F>
          <F label="Days"><Input type="number" value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} /></F>
          <F label="Daily Rate (₹)"><Input type="number" value={form.daily_rate} onChange={(e) => setForm({ ...form, daily_rate: e.target.value })} /></F>
          <F label="Mobilization Date"><Input type="date" value={form.mobilization_date || ""} onChange={(e) => setForm({ ...form, mobilization_date: e.target.value })} data-testid="rp-form-mob-date" /></F>
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
            <select value={form.basis} onChange={(e) => setForm({ ...form, basis: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-form-basis">
              {SUB_BASIS.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
            </select>
          </F>
          <F label="Scope of Work" full><Textarea rows={2} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} /></F>
          {form.basis === "unit_rate" ? (
            <>
              <F label="Quantity *"><Input type="number" value={form.sub_qty} onChange={(e) => setForm({ ...form, sub_qty: e.target.value })} data-testid="rp-form-sub-qty" /></F>
              <F label="Unit Rate (₹) *"><Input type="number" value={form.sub_unit_rate} onChange={(e) => setForm({ ...form, sub_unit_rate: e.target.value })} data-testid="rp-form-sub-rate" /></F>
              <F label="Value (auto)" full>
                <div className="h-9 flex items-center px-2 rounded-sm border bg-slate-50 text-sm font-mono font-semibold" data-testid="rp-form-value-auto">
                  ₹ {((Number(form.sub_qty) || 0) * (Number(form.sub_unit_rate) || 0)).toLocaleString("en-IN")}
                </div>
              </F>
            </>
          ) : (
            <F label="Value (₹)"><Input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} data-testid="rp-form-value" /></F>
          )}
          <F label="Work Start"><Input type="date" value={form.work_start || ""} onChange={(e) => setForm({ ...form, work_start: e.target.value })} data-testid="rp-form-work-start" /></F>
          <F label="Work End"><Input type="date" value={form.work_end || ""} onChange={(e) => setForm({ ...form, work_end: e.target.value })} data-testid="rp-form-work-end" /></F>
          <F label="Contact Person"><Input value={form.contact_person || ""} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} data-testid="rp-form-contact" /></F>
          <F label="Contact Phone"><Input value={form.contact_phone || ""} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></F>
          <F label="Retention %"><Input type="number" value={form.retention_pct} onChange={(e) => setForm({ ...form, retention_pct: e.target.value })} data-testid="rp-form-retention" /></F>
          <F label="Payment Terms"><Input value={form.payment_terms || ""} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} placeholder="e.g. 30 days from RA bill" /></F>
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

function ConvertDialog({ projectId, rows, type, onClose, onSaved }) {
  const [head, setHead] = useState({ required_date: "", site_location: "", priority: "medium", justification: "", submit: true });
  const [docs, setDocs] = useState(emptyApprovalDocs());
  const [saving, setSaving] = useState(false);
  const setH = (k, v) => setHead((h) => ({ ...h, [k]: v }));

  const lineLabel = (r) => {
    if (r.resource_type === "manpower") return `${r.designation_name || "Manpower"} × ${r.count_required || 1} Persons`;
    if (r.resource_type === "material") return `${r.item_name} × ${r.quantity || 1} ${r.uom || "Nos"}${r.category ? ` (${r.category})` : ""}`;
    return `${r.tool_name} × ${r.count_required || 1} Nos${r.tool_category ? ` (${r.tool_category})` : ""}`;
  };

  const go = async () => {
    if (head.submit) {
      const err = validateApprovalDocs(docs);
      if (err) { toast.error(err); return; }
    }
    setSaving(true);
    try {
      const r = await api.post("/project-requests/from-plan", {
        project_id: projectId,
        resource_ids: rows.map((x) => x.id),
        required_date: head.required_date || null,
        site_location: head.site_location || null,
        priority: head.priority === "normal" ? "medium" : head.priority,
        justification: head.justification || null,
        submit: head.submit,
        ...(head.submit ? docs : {}),
      });
      const d = r.data;
      toast.success(`Raised ${d.count} request${d.count > 1 ? "s" : ""} (${(d.request_nos || []).join(", ")}) · submitted for approval in the Request Center`);
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Conversion failed"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Raise Resource Request{rows.length > 1 ? "s" : ""} from Plan</DialogTitle></DialogHeader>
        <div className="border rounded-sm divide-y bg-slate-50/60 text-sm" data-testid="rp-convert-lines">
          {rows.map((r) => (
            <div key={r.id} className="px-3 py-1.5 flex items-center justify-between">
              <span>{lineLabel(r)}</span>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">{r.resource_type}</span>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <F label="Required Date"><Input type="date" value={head.required_date} onChange={(e) => setH("required_date", e.target.value)} data-testid="rp-convert-date" /></F>
          <F label="Priority">
            <select value={head.priority} onChange={(e) => setH("priority", e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="rp-convert-priority">
              {["low", "medium", "high", "critical"].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </F>
          <F label="Site Location"><SiteLocationSelect label="" value={head.site_location} onChange={(v) => setH("site_location", v)} testid="pr-site-location" /></F>
          <F label="Justification / Remarks"><Input value={head.justification} onChange={(e) => setH("justification", e.target.value)} placeholder="As per project resource plan" /></F>
        </div>
        {head.submit && (
          <ApprovalDocsGate parentType="resource_requests" value={docs} onChange={setDocs} testidPrefix="rp-convert-docs" />
        )}
        <DialogFooter className="flex items-center sm:justify-between gap-3">
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <Checkbox checked={head.submit} onCheckedChange={(v) => setH("submit", !!v)} data-testid="rp-convert-autosubmit" />
            Submit for approval immediately
          </label>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={go} disabled={saving} data-testid="rp-convert-save">
              <Send className="h-4 w-4 mr-1" />{saving ? "Raising…" : `Raise ${rows.length} Request${rows.length > 1 ? "s" : ""}`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
function validate(f) {
  if (f.resource_type === "manpower" && !f.designation_id) return "Pick a designation";
  if (f.resource_type === "material") {
    if (!f.category) return "Pick a material category";
    if (!f.item_id && !f.item_name?.trim()) return "Pick an item or enter a custom item name";
  }
  if (f.resource_type === "tools" && !f.tool_name?.trim()) return "Pick a tool or enter a tool name";
  if (f.resource_type === "subcontract") {
    if (!f.vendor_id) return "Pick a vendor";
    if (f.basis === "unit_rate" && !(Number(f.sub_qty) > 0 && Number(f.sub_unit_rate) > 0)) return "Enter quantity and unit rate for unit-rate basis";
  }
  return true;
}
