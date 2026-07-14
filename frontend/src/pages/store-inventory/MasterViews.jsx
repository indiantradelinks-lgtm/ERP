/**
 * Store & Inventory · Phase 1 master views
 * =========================================
 * Six lightweight CRUD views + Opening Stock + Settings + Dashboard.
 * They are intentionally compact so they fit alongside the existing
 * Inventory.jsx / StoreTransactions.jsx / Grn.jsx pages without duplicating
 * any of their functionality.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, RefreshCcw, Boxes, Package, Warehouse, MapPin,
  Layers, Settings as SettingsIcon, AlertTriangle, IndianRupee, ShieldAlert,
  TrendingDown, Activity, CheckCircle2, Download, Upload, Loader2 } from "lucide-react";

const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/* ═══════════════════ Inventory Dashboard ═══════════════════ */
export function InventoryDashboardView() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/inv/dashboard");
      setD(r.data);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to load dashboard"));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading || !d) return <div className="p-4 text-sm text-slate-500">Loading dashboard…</div>;

  const tiles = [
    { label: "Total Stock Value", value: fmt(d.total_stock_value), icon: IndianRupee, accent: "emerald" },
    { label: "Total Items",       value: d.total_items, icon: Boxes },
    { label: "Low Stock",          value: d.low_stock_count, icon: AlertTriangle, accent: "amber" },
    { label: "Reorder Items",      value: d.reorder_count, icon: TrendingDown, accent: "orange" },
    { label: "Out of Stock",       value: d.out_of_stock_count, icon: ShieldAlert, accent: "rose" },
    { label: "Pending Approvals",  value: d.pending_approvals, icon: CheckCircle2, accent: "blue" },
    { label: "Stores",             value: d.stores_count, icon: Warehouse },
    { label: "Site Stores",        value: d.site_stores_count, icon: MapPin },
    { label: "Scaffolding Value",  value: fmt(d.scaffolding_value) },
    { label: "Painting Value",     value: fmt(d.painting_value) },
    { label: "Roof Sheeting Value",value: fmt(d.roof_sheeting_value) },
    { label: "Rope Access Value",  value: fmt(d.rope_access_value) },
    { label: "PPE Stock Value",    value: fmt(d.ppe_value) },
    { label: "Tools & Tackles",    value: fmt(d.tools_value) },
    { label: "Damaged Stock",      value: fmt(d.damaged_value), accent: "rose" },
    { label: "Scrap Stock",        value: fmt(d.scrap_value), accent: "slate" },
  ];

  return (
    <div className="space-y-4" data-testid="inv-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Inventory Dashboard</h2>
          <p className="text-xs text-slate-500">Real-time material control · {d.as_of?.slice(0, 16)}</p>
        </div>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {tiles.map((t, i) => {
          const Icon = t.icon || Package;
          const palette = {
            emerald: "bg-emerald-50 border-emerald-200 text-emerald-900",
            amber: "bg-amber-50 border-amber-200 text-amber-900",
            orange: "bg-orange-50 border-orange-200 text-orange-900",
            rose: "bg-rose-50 border-rose-200 text-rose-900",
            blue: "bg-blue-50 border-blue-200 text-blue-900",
            slate: "bg-slate-50 border-slate-200 text-slate-900",
          }[t.accent] || "bg-white border-slate-200";
          return (
            <div key={i} className={`p-3 rounded-md border ${palette}`} data-testid={`inv-tile-${i}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="text-[10px] uppercase tracking-wider">{t.label}</div>
                <Icon className="h-3.5 w-3.5 opacity-70" />
              </div>
              <div className="text-xl font-bold tabular-nums">{t.value}</div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Recent Transactions</CardTitle></CardHeader>
          <CardContent>
            <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto">
              {(d.recent_transactions || []).map(t => (
                <li key={t.id} className="flex justify-between border-b pb-1">
                  <span><span className="font-mono">{t.txn_no}</span> · <span className="capitalize">{t.txn_type}</span> · {t.item_name}</span>
                  <span className="text-slate-500">{t.quantity} · {(t.created_at || "").slice(5, 10)}</span>
                </li>
              ))}
              {!d.recent_transactions?.length && <li className="text-slate-400">No recent activity.</li>}
            </ul>
          </CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Top Consumed (90d)</CardTitle></CardHeader>
          <CardContent>
            <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto">
              {(d.top_consumed || []).map((t, i) => (
                <li key={i} className="flex justify-between border-b pb-1"><span>{t.name}</span><span className="font-semibold">{t.total_out}</span></li>
              ))}
              {!d.top_consumed?.length && <li className="text-slate-400">No outward activity in last 90d.</li>}
            </ul>
          </CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Slow Movers</CardTitle></CardHeader>
          <CardContent>
            <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto">
              {(d.slow_movers || []).map(m => (
                <li key={m.id} className="flex justify-between border-b pb-1"><span>{m.name}</span><span className="text-slate-500">{fmt(m.value)}</span></li>
              ))}
              {!d.slow_movers?.length && <li className="text-slate-400">No slow movers.</li>}
            </ul>
          </CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Need Inspection</CardTitle></CardHeader>
          <CardContent>
            <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto">
              {(d.items_needing_inspection || []).map(i => (
                <li key={i.id} className="border-b pb-1">{i.name}</li>
              ))}
              {!d.items_needing_inspection?.length && <li className="text-slate-400">All items inspected / no inspection-tracked items.</li>}
            </ul>
          </CardContent></Card>
      </div>
    </div>
  );
}

/* ═══════════════════ Generic small CRUD view ═══════════════════ */
function MasterCRUD({ title, endpoint, columns, formFields, testid, requiredFields = ["code", "name"], bulk = null }) {
  const [rows, setRows] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const fileRef = useRef(null);

  const load = async () => {
    try {
      const r = await api.get(endpoint);
      setRows(r.data);
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); }, [endpoint]);

  const startNew = () => {
    setEditing("new");
    const blank = formFields.reduce((acc, f) => ({ ...acc, [f.key]: f.default ?? "" }), {});
    setForm(blank);
  };
  const startEdit = (row) => {
    const f = { ...row };
    formFields.forEach((fd) => { if (fd.csv && Array.isArray(f[fd.key])) f[fd.key] = f[fd.key].join(", "); });
    setEditing(row.id); setForm(f);
  };

  const save = async () => {
    for (const k of requiredFields) {
      if (!form[k] || String(form[k]).trim() === "") {
        toast.error(`${k} is required`); return;
      }
    }
    const payload = { ...form };
    formFields.forEach((f) => {
      if (f.csv && typeof payload[f.key] === "string") {
        payload[f.key] = payload[f.key].split(",").map((s) => s.trim()).filter(Boolean);
      }
    });
    setBusy(true);
    try {
      if (editing === "new") {
        await api.post(endpoint, payload);
        toast.success("Created");
      } else {
        await api.put(`${endpoint}/${editing}`, payload);
        toast.success("Updated");
      }
      setEditing(null);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Save failed"));
    } finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this entry?")) return;
    try {
      await api.delete(`${endpoint}/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Delete failed"));
    }
  };

  const downloadBulkTemplate = async () => {
    if (!bulk?.templateUrl) return;
    try {
      const resp = await api.get(bulk.templateUrl, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${testid}-bulk-template-${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Template downloaded");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to download template"));
    }
  };
  const uploadBulkFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f || !bulk?.importUrl) return;
    setBulkBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const resp = await api.post(bulk.importUrl, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setBulkResult(resp.data);
      toast.success(`Bulk update done · ${resp.data.summary.updated} updated, ${resp.data.summary.created} created`);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Bulk import failed"));
    } finally {
      setBulkBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card data-testid={testid}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title} <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          {bulk && (
            <>
              <Button size="sm" variant="outline" onClick={downloadBulkTemplate} data-testid={`${testid}-bulk-download`}>
                <Download className="h-3.5 w-3.5 mr-1" />Bulk Template
              </Button>
              <input ref={fileRef} type="file" accept=".xlsx" className="hidden"
                     data-testid={`${testid}-bulk-file`} disabled={bulkBusy} onChange={uploadBulkFile} />
              <Button size="sm" variant="outline" disabled={bulkBusy}
                      data-testid={`${testid}-bulk-upload-btn`}
                      onClick={() => fileRef.current?.click()}
                      title="Upload edited xlsx to bulk-patch records">
                {bulkBusy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Upload className="h-3.5 w-3.5 mr-1" />}
                {bulkBusy ? "Uploading…" : "Bulk Update"}
              </Button>
            </>
          )}
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={startNew} data-testid={`${testid}-new`}><Plus className="h-3.5 w-3.5 mr-1" />New</Button>
        </div>
      </CardHeader>
      <CardContent>
        {editing && (
          <div className="border rounded-md p-3 mb-3 bg-slate-50 space-y-2" data-testid={`${testid}-form`}>
            <div className="grid grid-cols-3 gap-2">
              {formFields.map(f => (
                <div key={f.key} className={f.full ? "col-span-3" : ""}>
                  <Label className="text-xs">{f.label}{requiredFields.includes(f.key) && " *"}</Label>
                  {f.type === "textarea" ? (
                    <Textarea rows={2} value={form[f.key] || ""} onChange={e => setForm({ ...form, [f.key]: e.target.value })} />
                  ) : f.type === "select" ? (
                    <select className="w-full h-9 px-2 border rounded-md text-sm" value={form[f.key] || ""}
                            onChange={e => setForm({ ...form, [f.key]: e.target.value })}>
                      <option value="">—</option>
                      {f.options.map(o => <option key={o.value || o} value={o.value || o}>{o.label || o}</option>)}
                    </select>
                  ) : f.type === "checkbox" ? (
                    <label className="flex items-center gap-1 mt-1 text-xs">
                      <input type="checkbox" checked={!!form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.checked })} />
                      <span>{f.checkboxLabel || "Yes"}</span>
                    </label>
                  ) : (
                    <Input type={f.type || "text"} value={form[f.key] ?? ""}
                            onChange={e => setForm({ ...form, [f.key]: f.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value })}
                            data-testid={`${testid}-${f.key}`} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <Button size="sm" variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
              <Button size="sm" onClick={save} disabled={busy} data-testid={`${testid}-save`}>{editing === "new" ? "Create" : "Update"}</Button>
            </div>
          </div>
        )}

        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50"><tr>
              {columns.map(c => <th key={c.key} className="text-left px-2 py-1">{c.label}</th>)}
              <th className="text-right px-2 py-1">Actions</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`${testid}-row-${r.id}`}>
                  {columns.map(c => <td key={c.key} className="px-2 py-1">{c.render ? c.render(r) : (r[c.key] ?? "—")}</td>)}
                  <td className="px-2 py-1 text-right">
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => startEdit(r)} data-testid={`${testid}-edit-${r.id}`}><Pencil className="h-3 w-3" /></Button>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => remove(r.id)} data-testid={`${testid}-del-${r.id}`}><Trash2 className="h-3 w-3 text-rose-600" /></Button>
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={columns.length + 1} className="text-center py-6 text-slate-400">No records yet. Click &quot;New&quot; to add.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
      <Dialog open={!!bulkResult} onOpenChange={(o) => !o && setBulkResult(null)}>
        <DialogContent className="max-w-2xl" data-testid={`${testid}-bulk-result-dialog`}>
          <DialogHeader>
            <DialogTitle>Bulk Update Summary</DialogTitle>
            <DialogDescription>Snapshot saved — full backup retained for audit/rollback</DialogDescription>
          </DialogHeader>
          {bulkResult && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-5 gap-2 font-mono">
                {Object.entries(bulkResult.summary || {}).filter(([k]) => k !== "errors").map(([k, v]) => (
                  <div key={k} className="border rounded p-2 text-center">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">{k.replaceAll("_", " ")}</div>
                    <div className="text-lg font-bold">{v}</div>
                  </div>
                ))}
              </div>
              {(bulkResult.summary?.errors || []).length > 0 && (
                <div className="border rounded p-2 max-h-48 overflow-y-auto">
                  <div className="text-xs font-semibold mb-1">Errors ({bulkResult.summary.errors.length})</div>
                  <ul className="text-xs space-y-0.5">
                    {bulkResult.summary.errors.slice(0, 30).map((e, i) => (
                      <li key={i} className="text-rose-700">Row {e.row}: {e.error}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="text-[10px] text-slate-500">Snapshot ID: {bulkResult.snapshot_id}</div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setBulkResult(null)} data-testid={`${testid}-bulk-result-close`}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export const CategoryMasterView = () => (
  <MasterCRUD
    title="Item Category Master" endpoint="/inv/categories" testid="inv-categories"
    bulk={{ templateUrl: "/inv-bulk/categories/template", importUrl: "/inv-bulk/categories/import" }}
    columns={[
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "sub_categories", label: "Sub-categories", render: r => (r.sub_categories || []).slice(0, 4).join(", ") + (r.sub_categories?.length > 4 ? "…" : "") },
      { key: "active", label: "Active", render: r => r.active ? "✓" : "—" },
    ]}
    formFields={[
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "description", label: "Description", full: true, type: "textarea" },
      { key: "sub_categories", label: "Sub-categories (comma separated)", full: true,
        type: "text", csv: true },
      { key: "active", label: "Active", type: "checkbox", default: true },
    ]}
  />
);

export const UnitMasterView = () => (
  <MasterCRUD
    title="Unit / UOM Master" endpoint="/inv/units" testid="inv-units"
    columns={[
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "type", label: "Type" }, { key: "base_unit", label: "Base" },
      { key: "conversion_factor", label: "Factor" },
    ]}
    formFields={[
      { key: "code", label: "Code (e.g. KG, NOS)" }, { key: "name", label: "Name" },
      { key: "type", label: "Type", type: "select",
        options: ["count", "length", "weight", "volume", "area", "time"] },
      { key: "base_unit", label: "Base Unit (optional)" },
      { key: "conversion_factor", label: "Conversion Factor", type: "number" },
      { key: "active", label: "Active", type: "checkbox", default: true },
    ]}
  />
);

export const StoreMasterView = () => (
  <MasterCRUD
    title="Store / Warehouse Master" endpoint="/inv/stores" testid="inv-stores"
    columns={[
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "type", label: "Type", render: r => (r.type || "").replace(/_/g, " ") },
      { key: "incharge_name", label: "Incharge" },
      { key: "active", label: "Active", render: r => r.active ? "✓" : "—" },
    ]}
    formFields={[
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "type", label: "Type", type: "select",
        options: [
          { value: "main_store", label: "Main Store" },
          { value: "site_store", label: "Site Store" },
          { value: "project_store", label: "Project Store" },
          { value: "scrap_yard", label: "Scrap Yard" },
          { value: "damaged_stock", label: "Damaged Stock Area" },
        ] },
      { key: "address", label: "Address", full: true, type: "textarea" },
      { key: "incharge_name", label: "Incharge Name" },
      { key: "contact_phone", label: "Contact Phone" },
      { key: "remarks", label: "Remarks", full: true },
      { key: "active", label: "Active", type: "checkbox", default: true },
    ]}
  />
);

export const SiteStoreMasterView = () => (
  <MasterCRUD
    title="Site Store Master" endpoint="/inv/site-stores" testid="inv-site-stores"
    columns={[
      { key: "code", label: "Code" }, { key: "site_location", label: "Site Location" },
      { key: "project_code", label: "Project" }, { key: "client_name", label: "Client" },
      { key: "site_incharge_name", label: "Incharge" },
      { key: "active", label: "Active", render: r => r.active ? "✓" : "—" },
    ]}
    formFields={[
      { key: "code", label: "Code" },
      { key: "project_code", label: "Project Code" },
      { key: "client_name", label: "Client Name" },
      { key: "site_location", label: "Site Location" },
      { key: "site_incharge_name", label: "Site Incharge" },
      { key: "storekeeper_name", label: "Storekeeper" },
      { key: "start_date", label: "Start Date", type: "date" },
      { key: "closing_date", label: "Closing Date", type: "date" },
      { key: "remarks", label: "Remarks", full: true, type: "textarea" },
      { key: "active", label: "Active", type: "checkbox", default: true },
    ]}
    requiredFields={["code", "site_location"]}
  />
);

export function BinMasterView() {
  const [stores, setStores] = useState([]);
  const [storeId, setStoreId] = useState("");
  useEffect(() => { api.get("/inv/stores").then(r => { setStores(r.data); if (r.data.length) setStoreId(r.data[0].id); }); }, []);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Label className="text-xs">Store:</Label>
        <select className="h-8 px-2 border rounded-md text-sm" value={storeId}
                onChange={e => setStoreId(e.target.value)} data-testid="inv-bins-store-select">
          {stores.map(s => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
        </select>
      </div>
      {storeId && (
        <MasterCRUD
          key={storeId}
          title="Bin / Shelf Locations"
          endpoint={`/inv/bins?store_id=${storeId}`}
          testid="inv-bins"
          columns={[
            { key: "code", label: "Code" }, { key: "aisle", label: "Aisle" },
            { key: "rack", label: "Rack" }, { key: "shelf", label: "Shelf" },
            { key: "description", label: "Description" },
            { key: "active", label: "Active", render: r => r.active ? "✓" : "—" },
          ]}
          formFields={[
            { key: "code", label: "Bin Code (e.g. A-01-S3)" },
            { key: "aisle", label: "Aisle" },
            { key: "rack", label: "Rack" },
            { key: "shelf", label: "Shelf" },
            { key: "description", label: "Description", full: true },
            { key: "store_id", label: "Store", type: "hidden", default: storeId },
            { key: "active", label: "Active", type: "checkbox", default: true },
          ].filter(f => f.key !== "store_id")}
          requiredFields={["code"]}
        />
      )}
    </div>
  );
}

/* ═══════════════════ Opening Stock ═══════════════════ */
export function OpeningStockView() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [stores, setStores] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10), store_id: "", remarks: "",
    lines: [{ item_id: "", quantity: "", rate: "", condition: "new" }],
  });

  const load = async () => {
    try {
      const [r, i, s] = await Promise.all([
        api.get("/inv/opening-stock"),
        api.get("/inventory"),
        api.get("/inv/stores"),
      ]);
      setRows(r.data); setItems(i.data); setStores(s.data);
      if (s.data.length && !form.store_id) setForm(f => ({ ...f, store_id: s.data[0].id }));
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); }, []);

  const total = useMemo(() => form.lines.reduce((a, l) => a + (Number(l.quantity) || 0) * (Number(l.rate) || 0), 0), [form.lines]);

  const updateLine = (i, field, val) => setForm(f => ({ ...f, lines: f.lines.map((l, idx) => idx === i ? { ...l, [field]: val } : l) }));
  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, { item_id: "", quantity: "", rate: "", condition: "new" }] }));
  const removeLine = (i) => setForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));

  const submit = async () => {
    if (!form.store_id) { toast.error("Pick a store"); return; }
    if (!form.lines.length) { toast.error("Add at least one item line"); return; }
    for (const l of form.lines) {
      if (!l.item_id) { toast.error("Pick item on each line"); return; }
      if (!l.quantity || Number(l.quantity) <= 0) { toast.error("Quantity must be > 0"); return; }
      if (Number(l.rate) < 0) { toast.error("Rate cannot be negative"); return; }
    }
    setBusy(true);
    try {
      const payload = {
        ...form,
        lines: form.lines.map(l => ({
          item_id: l.item_id, quantity: Number(l.quantity), rate: Number(l.rate || 0),
          condition: l.condition, batch: l.batch || null, serial_no: l.serial_no || null,
          bin_id: l.bin_id || null,
        })),
      };
      const r = await api.post("/inv/opening-stock", payload);
      toast.success(`Opening stock ${r.data.os_number} ${r.data.status}`);
      setShowForm(false);
      setForm({ date: new Date().toISOString().slice(0, 10), store_id: stores[0]?.id || "", remarks: "",
                 lines: [{ item_id: "", quantity: "", rate: "", condition: "new" }] });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Create failed"));
    } finally { setBusy(false); }
  };

  const approve = async (id) => {
    try {
      await api.post(`/inv/opening-stock/${id}/approve`);
      toast.success("Approved & posted");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Approval failed"));
    }
  };

  return (
    <Card data-testid="inv-opening-stock">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Opening Stock</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="os-new"><Plus className="h-3.5 w-3.5 mr-1" />New Opening Stock</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="os-form">
            <div className="grid grid-cols-3 gap-2">
              <div><Label className="text-xs">Date *</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>
              <div className="col-span-2"><Label className="text-xs">Store *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.store_id}
                        onChange={e => setForm({ ...form, store_id: e.target.value })} data-testid="os-store">
                  <option value="">—</option>
                  {stores.map(s => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
                </select>
              </div>
            </div>
            <Label className="text-xs">Remarks</Label>
            <Textarea rows={2} value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} />
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label className="text-xs">Lines</Label>
                <Button size="sm" variant="outline" onClick={addLine}><Plus className="h-3 w-3 mr-1" />Add Line</Button>
              </div>
              <div className="border rounded-md overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-white"><tr>
                    <th className="text-left px-1 py-1">Item</th>
                    <th className="text-right px-1 py-1">Qty</th>
                    <th className="text-right px-1 py-1">Rate</th>
                    <th className="text-left px-1 py-1">Condition</th>
                    <th className="text-left px-1 py-1">Batch</th>
                    <th className="text-right px-1 py-1">Value</th>
                    <th></th>
                  </tr></thead>
                  <tbody>
                    {form.lines.map((l, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-1 py-1">
                          <select className="w-full h-7 px-1 border rounded text-xs" value={l.item_id}
                                  onChange={e => updateLine(i, "item_id", e.target.value)} data-testid={`os-line-${i}-item`}>
                            <option value="">—</option>
                            {items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name}</option>)}
                          </select>
                        </td>
                        <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.quantity} onChange={e => updateLine(i, "quantity", e.target.value)} data-testid={`os-line-${i}-qty`} /></td>
                        <td className="px-1 py-1 w-24"><Input className="h-7 text-right" type="number" value={l.rate} onChange={e => updateLine(i, "rate", e.target.value)} data-testid={`os-line-${i}-rate`} /></td>
                        <td className="px-1 py-1 w-28">
                          <select className="h-7 w-full px-1 border rounded text-xs" value={l.condition} onChange={e => updateLine(i, "condition", e.target.value)}>
                            <option value="new">New</option><option value="good">Good</option>
                            <option value="used">Used</option><option value="damaged">Damaged</option>
                            <option value="scrap">Scrap</option>
                          </select>
                        </td>
                        <td className="px-1 py-1 w-24"><Input className="h-7" value={l.batch || ""} onChange={e => updateLine(i, "batch", e.target.value)} /></td>
                        <td className="px-1 py-1 text-right tabular-nums">{fmt((Number(l.quantity) || 0) * (Number(l.rate) || 0))}</td>
                        <td className="px-1 py-1"><Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => removeLine(i)}><Trash2 className="h-3 w-3 text-rose-600" /></Button></td>
                      </tr>
                    ))}
                    <tr className="bg-slate-100 font-semibold">
                      <td colSpan={5} className="px-1 py-1 text-right">Total</td>
                      <td className="px-1 py-1 text-right tabular-nums">{fmt(total)}</td>
                      <td></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="os-save">Submit</Button>
            </div>
          </div>
        )}

        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50"><tr>
              <th className="text-left px-2 py-1">OS No</th>
              <th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">Store</th>
              <th className="text-right px-2 py-1">Lines</th>
              <th className="text-right px-2 py-1">Total Value</th>
              <th className="text-center px-2 py-1">Status</th>
              <th className="text-left px-2 py-1">Created By</th>
              <th></th>
            </tr></thead>
            <tbody>
              {rows.map(r => {
                const store = stores.find(s => s.id === r.store_id);
                return (
                  <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`os-row-${r.id}`}>
                    <td className="px-2 py-1 font-mono">{r.os_number}</td>
                    <td className="px-2 py-1 font-mono">{r.date}</td>
                    <td className="px-2 py-1">{store?.code || r.store_id}</td>
                    <td className="px-2 py-1 text-right">{r.line_count}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{fmt(r.total_value)}</td>
                    <td className="px-2 py-1 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        r.status === "approved" ? "bg-emerald-100 text-emerald-800" :
                        r.status === "pending_approval" ? "bg-amber-100 text-amber-800" :
                        r.status === "rejected" ? "bg-rose-100 text-rose-800" :
                        "bg-slate-100 text-slate-700"}`}>{r.status}</span>
                    </td>
                    <td className="px-2 py-1">{r.created_by_name}</td>
                    <td className="px-2 py-1 text-right">
                      {r.status === "pending_approval" && (
                        <Button size="sm" variant="outline" className="h-7" onClick={() => approve(r.id)} data-testid={`os-approve-${r.id}`}>Approve</Button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No opening stock declarations yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Stock Balance ═══════════════════ */
export function StockBalanceView() {
  const [rows, setRows] = useState([]);
  const [totals, setTotals] = useState({});
  const [onlyInStock, setOnlyInStock] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/inv/stock-balance?only_in_stock=${onlyInStock}`);
      setRows(r.data.rows); setTotals(r.data.totals);
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); }, [onlyInStock]);

  return (
    <Card data-testid="inv-stock-balance">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Stock Balance · <span className="text-xs text-slate-500">{rows.length} items · {fmt(totals.stock_value)}</span></CardTitle>
        <div className="flex gap-2">
          <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={onlyInStock} onChange={e => setOnlyInStock(e.target.checked)} /> In-stock only</label>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">Code</th>
              <th className="text-left px-2 py-1">Name</th>
              <th className="text-left px-2 py-1">Category</th>
              <th className="text-right px-2 py-1">Available</th>
              <th className="text-right px-2 py-1">In-Transit</th>
              <th className="text-right px-2 py-1">Damaged</th>
              <th className="text-right px-2 py-1">Scrap</th>
              <th className="text-right px-2 py-1">Avg Rate</th>
              <th className="text-right px-2 py-1">Value</th>
              <th className="text-left px-2 py-1">Last Txn</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.item_id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.item_code || "—"}</td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-[10px] text-slate-500">{r.category}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.available_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.in_transit_qty}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-rose-600">{r.damaged_qty || "—"}</td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-500">{r.scrap_qty || "—"}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.average_rate}</td>
                  <td className="px-2 py-1 text-right tabular-nums font-semibold">{fmt(r.stock_value)}</td>
                  <td className="px-2 py-1 text-[10px] text-slate-500">{(r.last_txn_date || "").slice(0, 10)} {r.last_txn_type}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={10} className="text-center py-6 text-slate-400">No stock records.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Settings ═══════════════════ */
export function InventorySettingsView() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get("/inv/settings");
      setS(r.data);
    } catch (e) { toast.error(apiErrorMessage(e, "Load failed")); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/inv/settings", s);
      toast.success("Settings saved");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Save failed"));
    } finally { setBusy(false); }
  };

  const seed = async () => {
    if (!window.confirm("Seed default ITL categories, units and Main Store? Safe to run multiple times.")) return;
    try {
      const r = await api.post("/inv/seed-defaults");
      toast.success(`Seeded · ${r.data.categories_added} categories, ${r.data.units_added} units`);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Seed failed"));
    }
  };

  if (!s) return <div className="p-4 text-sm text-slate-500">Loading settings…</div>;
  return (
    <Card data-testid="inv-settings">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Inventory Settings</CardTitle>
        <Button size="sm" variant="outline" onClick={seed} data-testid="inv-seed">Seed ITL Defaults</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Default Issue-Approval Threshold (qty)</Label>
            <Input type="number" value={s.issue_threshold_default || 0} onChange={e => setS({ ...s, issue_threshold_default: Number(e.target.value) })} />
            <p className="text-[10px] text-slate-500 mt-1">Outward issues above this qty auto-create an approval.</p>
          </div>
          <div>
            <Label className="text-xs">Opening Stock Approval Value (₹)</Label>
            <Input type="number" value={s.opening_stock_approval_value || 0} onChange={e => setS({ ...s, opening_stock_approval_value: Number(e.target.value) })} />
            <p className="text-[10px] text-slate-500 mt-1">Opening stock above this value goes to approval.</p>
          </div>
          <div>
            <Label className="text-xs">PPE Inspection Cycle (days)</Label>
            <Input type="number" value={s.ppe_inspection_days || 30} onChange={e => setS({ ...s, ppe_inspection_days: Number(e.target.value) })} />
          </div>
          <div>
            <Label className="text-xs">Tool Calibration Warning (days)</Label>
            <Input type="number" value={s.tool_calibration_warning_days || 30} onChange={e => setS({ ...s, tool_calibration_warning_days: Number(e.target.value) })} />
          </div>
          <div className="col-span-2">
            <Label className="text-xs">Low Stock Email Recipient</Label>
            <Input value={s.low_stock_email_to || ""} onChange={e => setS({ ...s, low_stock_email_to: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={!!s.block_negative_stock} onChange={e => setS({ ...s, block_negative_stock: e.target.checked })} /> Block negative stock</label>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={!!s.require_batch_on_receipt} onChange={e => setS({ ...s, require_batch_on_receipt: e.target.checked })} /> Require batch on inward receipts</label>
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={busy} data-testid="inv-settings-save">Save Settings</Button>
        </div>
      </CardContent>
    </Card>
  );
}
