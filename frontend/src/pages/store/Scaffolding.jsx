import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Layers, RefreshCw, Warehouse, FileSpreadsheet, FileText, Plus, ArrowRightLeft, Pencil, Trash2, Upload, Download, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { TransfersTab, ChallansTab } from "./ScaffoldingMovements";

export const SCAF_APPROVE_ROLES = new Set(["super_admin", "store_manager", "inventory_manager", "dept_head", "general_manager", "director"]);
const fmtW = (kg) => Number(kg || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 });

export default function Scaffolding() {
  const { user, can } = useAuth();
  const canWrite = can ? can("scaffolding", "write") : false;
  const canApprove = SCAF_APPROVE_ROLES.has(user?.role);
  const [summary, setSummary] = useState(null);
  const [locations, setLocations] = useState([]);
  const [items, setItems] = useState([]);
  const [matrix, setMatrix] = useState(null);
  const [bump, setBump] = useState(0);
  const [tab, setTab] = useState("stock");
  const [transferPrefill, setTransferPrefill] = useState(null);
  const [importOpen, setImportOpen] = useState(false);

  const reload = useCallback(() => {
    api.get("/scaffolding/summary").then((r) => setSummary(r.data)).catch(() => {});
    api.get("/scaffolding/locations").then((r) => setLocations(r.data || [])).catch(() => {});
    api.get("/scaffolding/items").then((r) => setItems(r.data || [])).catch(() => {});
    api.get("/scaffolding/stock-matrix").then((r) => setMatrix(r.data)).catch(() => {});
    setBump((b) => b + 1);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const stockMap = useMemo(() => {
    const m = {};
    (matrix?.items || []).forEach((it) => { m[it.item_id] = it.by_location || {}; });
    return m;
  }, [matrix]);

  const migrate = async () => {
    if (!window.confirm("Seed each catalog item's current global quantity into the Main Store? (one-time)")) return;
    try {
      const r = await api.post("/scaffolding/migrate-main-store");
      toast.success(`Migrated ${r.data.migrated} item(s) into ${r.data.store} (${r.data.skipped} skipped)`);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Migration failed"); }
  };

  const download = async (fmt, kind, params = {}) => {
    try {
      const { data } = await api.get(`/scaffolding/export.${fmt}`, { responseType: "blob", params: { kind, ...params } });
      const url = URL.createObjectURL(data); const a = document.createElement("a");
      a.href = url; a.download = `scaffolding_${kind}.${fmt}`; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const onTransferSelected = (selected) => {
    setTransferPrefill({ lines: selected.map((it) => ({ item_id: it.item_id, quantity: "" })) });
    setTab("transfers");
  };

  const kpis = summary ? [["Items Tracked", summary.items_tracked], ["Locations", summary.locations],
    ["Total Qty", summary.total_qty], ["Pending Approvals", summary.pending_approvals],
    ["In-Transit Challans", summary.in_transit_challans], ["Open Transfers", summary.open_transfers]] : [];

  return (
    <div className="space-y-5" data-testid="scaffolding-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Layers className="h-3 w-3" /> Scaffolding Stock &amp; Challan Center
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Scaffolding Inventory</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Location-wise scaffolding stock across Main Store &amp; running project sites. Raise transfer requests,
            get Store Manager approval, dispatch with one or many Delivery Challans and receive at destination.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" className="h-9 rounded-sm" onClick={reload} data-testid="scaf-reload"><RefreshCw className="h-4 w-4" /></Button>
          {canWrite && (
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => setImportOpen(true)} data-testid="scaf-bulk-import-btn">
              <Upload className="h-4 w-4 mr-1.5" /> Bulk Import
            </Button>
          )}
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf", "challans")} data-testid="scaf-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> Challan Register</Button>
          {canApprove && (
            <Button variant="outline" className="h-9 rounded-sm" onClick={migrate} data-testid="scaf-migrate-btn">
              <Warehouse className="h-4 w-4 mr-1.5" /> Migrate to Main Store
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {kpis.map(([label, v]) => (
          <div key={label} className="bg-card border border-border rounded-sm p-3" data-testid={`scaf-kpi-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <div className="text-xl font-black tabular">{v}</div>
          </div>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="stock" className="rounded-sm" data-testid="scaf-tab-stock">Stock Matrix</TabsTrigger>
          <TabsTrigger value="transfers" className="rounded-sm" data-testid="scaf-tab-transfers">Transfers</TabsTrigger>
          <TabsTrigger value="challans" className="rounded-sm" data-testid="scaf-tab-challans">Delivery Challans</TabsTrigger>
          <TabsTrigger value="items" className="rounded-sm" data-testid="scaf-tab-items">Item Catalog</TabsTrigger>
        </TabsList>
        <TabsContent value="stock" className="mt-4">
          <StockMatrixTab matrix={matrix} locations={locations} items={items} canWrite={canWrite}
            onChanged={reload} onExport={download} onTransferSelected={onTransferSelected} />
        </TabsContent>
        <TabsContent value="transfers" className="mt-4">
          <TransfersTab bump={bump} locations={locations} items={items} canWrite={canWrite} canApprove={canApprove}
            onChanged={reload} stockMap={stockMap} prefill={transferPrefill} onPrefillConsumed={() => setTransferPrefill(null)} />
        </TabsContent>
        <TabsContent value="challans" className="mt-4">
          <ChallansTab bump={bump} canWrite={canWrite} onChanged={reload} />
        </TabsContent>
        <TabsContent value="items" className="mt-4">
          <ItemsTab items={items} canWrite={canWrite} isSuperAdmin={user?.role === "super_admin"} onChanged={reload} />
        </TabsContent>
      </Tabs>

      <BulkImportDialog open={importOpen} onClose={() => setImportOpen(false)} onChanged={reload} />
    </div>
  );
}

/* ─── Stock Matrix ──────────────────────────────────────────────────── */
function StockMatrixTab({ matrix, locations, items, canWrite, onChanged, onExport, onTransferSelected }) {
  const [opening, setOpening] = useState(false);
  const [form, setForm] = useState({ item_id: "", location_id: "", quantity: "" });
  const [locFilter, setLocFilter] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState({});

  const cols = useMemo(() => {
    const all = matrix?.locations || [];
    return locFilter ? all.filter((c) => c.id === locFilter) : all;
  }, [matrix, locFilter]);

  const rows = useMemo(() => {
    let out = matrix?.items || [];
    const ql = q.trim().toLowerCase();
    if (ql) out = out.filter((it) => (it.item_name || "").toLowerCase().includes(ql) || (it.item_code || "").toLowerCase().includes(ql));
    if (locFilter) out = out.filter((it) => Number(it.by_location?.[locFilter] || 0) > 0);
    return out.map((it) => {
      const qty = locFilter ? Number(it.by_location?.[locFilter] || 0) : it.total;
      const wkg = Math.round(qty * (it.unit_weight_kg || 0) * 100) / 100;
      return { ...it, disp_qty: qty, disp_weight: wkg };
    });
  }, [matrix, q, locFilter]);

  const totals = useMemo(() => {
    const qty = rows.reduce((a, r) => a + r.disp_qty, 0);
    const wkg = rows.reduce((a, r) => a + r.disp_weight, 0);
    return { qty: Math.round(qty * 100) / 100, wkg: Math.round(wkg * 100) / 100, mt: Math.round(wkg / 10) / 100 };
  }, [rows]);

  const selRows = rows.filter((r) => selected[r.item_id]);
  const allChecked = rows.length > 0 && selRows.length === rows.length;
  const toggleAll = () => {
    if (allChecked) { setSelected({}); return; }
    const next = {}; rows.forEach((r) => { next[r.item_id] = true; }); setSelected(next);
  };

  const saveOpening = async () => {
    if (!form.item_id || !form.location_id) { toast.error("Pick item and location"); return; }
    try {
      const r = await api.post("/scaffolding/opening-stock", { ...form, quantity: Number(form.quantity) || 0 });
      toast.success(`${r.data.item} @ ${r.data.location} set to ${r.data.quantity}`);
      setOpening(false); setForm({ item_id: "", location_id: "", quantity: "" }); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const exportParams = () => {
    const p = {};
    if (locFilter) p.location_id = locFilter;
    if (q.trim()) p.q = q.trim();
    if (selRows.length) p.item_ids = selRows.map((r) => r.item_id).join(",");
    return p;
  };

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center justify-between p-3 border-b border-border gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <select value={locFilter} onChange={(e) => { setLocFilter(e.target.value); setSelected({}); }}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="scaf-matrix-loc-filter">
            <option value="">All locations</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.type === "store" ? "🏬" : "🏗"} {l.name}</option>)}
          </select>
          <Input placeholder="Search item / code…" value={q} onChange={(e) => setQ(e.target.value)}
            className="h-8 rounded-sm w-52 text-xs" data-testid="scaf-matrix-search" />
        </div>
        <div className="flex gap-2 flex-wrap">
          {selRows.length > 0 && canWrite && (
            <Button size="sm" className="h-8 rounded-sm" onClick={() => { onTransferSelected(selRows); setSelected({}); }} data-testid="scaf-transfer-selected">
              <Truck className="h-3.5 w-3.5 mr-1" /> Transfer Selected ({selRows.length})
            </Button>
          )}
          <Button size="sm" variant="outline" className="h-8 rounded-sm" onClick={() => onExport("xlsx", "stock", exportParams())} data-testid="scaf-matrix-export-xlsx">
            <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Excel{selRows.length ? ` (${selRows.length})` : ""}
          </Button>
          <Button size="sm" variant="outline" className="h-8 rounded-sm" onClick={() => onExport("pdf", "stock", exportParams())} data-testid="scaf-matrix-export-pdf">
            <FileText className="h-3.5 w-3.5 mr-1" /> PDF
          </Button>
          {canWrite && (
            <Button size="sm" variant="outline" className="h-8 rounded-sm" onClick={() => setOpening(true)} data-testid="scaf-opening-btn">
              <Plus className="h-3.5 w-3.5 mr-1" /> Opening / Adjust
            </Button>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-8"><Checkbox checked={allChecked} onCheckedChange={toggleAll} data-testid="scaf-matrix-select-all" /></TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
            {!locFilter && cols.map((c) => <TableHead key={c.id} className="text-[10px] uppercase tracking-wider text-right whitespace-nowrap">{c.name}</TableHead>)}
            {locFilter && <TableHead className="text-[10px] uppercase tracking-wider text-right">Qty @ Location</TableHead>}
            {!locFilter && <TableHead className="text-[10px] uppercase tracking-wider text-right">In Transit</TableHead>}
            {!locFilter && <TableHead className="text-[10px] uppercase tracking-wider text-right">Total</TableHead>}
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Weight (kg)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Tonnage (MT)</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={cols.length + 6} className="text-center py-10 text-muted-foreground">
                No location stock found. Use "Migrate to Main Store", Bulk Import or Opening Stock to begin.
              </TableCell></TableRow>
            )}
            {rows.map((it) => (
              <TableRow key={it.item_id} data-testid={`scaf-stock-row-${it.item_id}`} className={selected[it.item_id] ? "bg-primary/5" : ""}>
                <TableCell><Checkbox checked={!!selected[it.item_id]}
                  onCheckedChange={(v) => setSelected((s) => ({ ...s, [it.item_id]: !!v }))}
                  data-testid={`scaf-select-${it.item_id}`} /></TableCell>
                <TableCell>
                  <div className="font-semibold text-sm">{it.item_name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono-data">
                    {it.item_code}{it.size ? ` · ${it.size}` : ""} · {it.unit}{it.unit_weight_kg ? ` · ${it.unit_weight_kg} kg/u` : ""}
                  </div>
                </TableCell>
                {!locFilter && cols.map((c) => (
                  <TableCell key={c.id} className="text-right font-mono-data tabular text-sm">{it.by_location[c.id] ?? "—"}</TableCell>
                ))}
                {locFilter && <TableCell className="text-right font-mono-data tabular text-sm font-bold">{it.disp_qty}</TableCell>}
                {!locFilter && <TableCell className="text-right font-mono-data tabular text-sm text-amber-700">{it.in_transit || "—"}</TableCell>}
                {!locFilter && <TableCell className="text-right font-mono-data tabular text-sm font-bold">{it.total}</TableCell>}
                <TableCell className="text-right font-mono-data tabular text-sm">{it.disp_weight ? fmtW(it.disp_weight) : "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-sm">{it.disp_weight ? (it.disp_weight / 1000).toFixed(3) : "—"}</TableCell>
              </TableRow>
            ))}
            {rows.length > 0 && (
              <TableRow className="bg-muted/40 hover:bg-muted/40 font-bold" data-testid="scaf-matrix-totals">
                <TableCell></TableCell>
                <TableCell className="text-[10px] uppercase tracking-wider">Totals ({rows.length} items)</TableCell>
                {!locFilter && cols.map((c) => <TableCell key={c.id}></TableCell>)}
                {!locFilter && <TableCell></TableCell>}
                <TableCell className="text-right font-mono-data tabular">{totals.qty}</TableCell>
                <TableCell className="text-right font-mono-data tabular">{fmtW(totals.wkg)}</TableCell>
                <TableCell className="text-right font-mono-data tabular">{totals.mt.toFixed(2)}</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={opening} onOpenChange={setOpening}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Opening / Adjust Stock</DialogTitle>
            <DialogDescription>Sets the absolute quantity of an item at a location.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Item *</Label>
              <select value={form.item_id} onChange={(e) => setForm({ ...form, item_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="scaf-opening-item">
                <option value="">— select item —</option>
                {items.map((i) => <option key={i.id} value={i.id}>{i.name}{i.size ? ` (${i.size})` : ""} · {i.code}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Location *</Label>
              <select value={form.location_id} onChange={(e) => setForm({ ...form, location_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="scaf-opening-location">
                <option value="">— select location —</option>
                {locations.map((l) => <option key={l.id} value={l.id}>{l.type === "store" ? "🏬" : "🏗"} {l.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Quantity *</Label>
              <Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })}
                className="h-9 rounded-sm mt-1 tabular" data-testid="scaf-opening-qty" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpening(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={saveOpening} data-testid="scaf-opening-submit">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ─── Item Catalog ──────────────────────────────────────────────────── */
const blankItemForm = () => ({ name: "", code: "", size: "", spec: "", unit: "Nos", rate: "", min_stock: "", unit_weight_kg: "" });

function ItemsTab({ items, canWrite, isSuperAdmin, onChanged }) {
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null); // null | "new" | item object

  const remove = async (i) => {
    if (!window.confirm(`Delete ${i.name}? Only possible when it has no stock and no open transfers.`)) return;
    try { await api.delete(`/scaffolding/items/${i.id}`); toast.success("Item deleted"); onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  const ql = q.trim().toLowerCase();
  const filtered = ql ? items.filter((i) => (i.name || "").toLowerCase().includes(ql) || (i.code || "").toLowerCase().includes(ql)) : items;

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center justify-between p-3 border-b border-border gap-2 flex-wrap">
        <Input placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 rounded-sm w-64 text-xs" data-testid="scaf-item-search" />
        {canWrite && (
          <Button size="sm" className="h-8 rounded-sm" onClick={() => setEditing("new")} data-testid="scaf-new-item">
            <Plus className="h-3.5 w-3.5 mr-1" /> New Item
          </Button>
        )}
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="text-[10px] uppercase tracking-wider">Code</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Size / Spec</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-right">Unit Wt (kg)</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-right">Rate</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-right">Global Qty</TableHead>
          <TableHead className="text-right"></TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {filtered.slice(0, 300).map((i) => (
            <TableRow key={i.id} data-testid={`scaf-item-row-${i.id}`}>
              <TableCell className="font-mono-data text-xs font-bold">{i.code || i.sku || "—"}</TableCell>
              <TableCell className="text-sm font-semibold">{i.name}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{[i.size, i.spec].filter(Boolean).join(" · ") || "—"}</TableCell>
              <TableCell className="text-xs">{i.unit || i.uom || "Nos"}</TableCell>
              <TableCell className="text-right font-mono-data tabular text-xs">{i.unit_weight_kg || "—"}</TableCell>
              <TableCell className="text-right font-mono-data tabular text-xs">{i.rate ? `₹ ${Number(i.rate).toLocaleString("en-IN")}` : "—"}</TableCell>
              <TableCell className="text-right font-mono-data tabular text-xs font-bold">{i.quantity ?? 0}</TableCell>
              <TableCell className="text-right space-x-1 whitespace-nowrap">
                {canWrite && (
                  <Button size="sm" variant="ghost" className="h-7 rounded-sm" onClick={() => setEditing(i)} data-testid={`scaf-item-edit-${i.id}`}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                )}
                {canWrite && (
                  <Button size="sm" variant="ghost" className="h-7 rounded-sm text-destructive" onClick={() => remove(i)} data-testid={`scaf-item-delete-${i.id}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {filtered.length === 0 && (
            <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">No items found.</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
      <ItemFormDialog editing={editing} onClose={() => setEditing(null)} onChanged={onChanged} />
    </div>
  );
}

function ItemFormDialog({ editing, onClose, onChanged }) {
  const isNew = editing === "new";
  const [form, setForm] = useState(blankItemForm());
  useEffect(() => {
    if (!editing) return;
    setForm(isNew ? blankItemForm() : {
      name: editing.name || "", code: editing.code || "", size: editing.size || "", spec: editing.spec || "",
      unit: editing.unit || editing.uom || "Nos", rate: editing.rate ?? "", min_stock: editing.min_stock ?? "",
      unit_weight_kg: editing.unit_weight_kg ?? "",
    });
  }, [editing]); // eslint-disable-line

  const save = async () => {
    if (!form.name.trim()) { toast.error("Item name required"); return; }
    const payload = { ...form, rate: Number(form.rate) || 0, min_stock: Number(form.min_stock) || 0, unit_weight_kg: Number(form.unit_weight_kg) || 0 };
    try {
      if (isNew) {
        const r = await api.post("/scaffolding/items", payload);
        toast.success(`Item ${r.data.code} created`);
      } else {
        await api.put(`/scaffolding/items/${editing.id}`, payload);
        toast.success("Item updated");
      }
      onClose(); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <Dialog open={!!editing} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">{isNew ? "New Scaffolding Item" : `Edit — ${editing?.name || ""}`}</DialogTitle>
          <DialogDescription>{isNew ? 'Added to the item catalog with category "scaffolding".' : "Changes sync to all location stock rows."}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Name *</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Vertical Standard 3m" className="h-9 rounded-sm mt-1" data-testid="scaf-item-name" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Code {isNew ? "(auto if blank)" : ""}</Label>
            <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="SCF-0001" className="h-9 rounded-sm mt-1" data-testid="scaf-item-code" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Size</Label>
            <Input value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} placeholder="3.0 m" className="h-9 rounded-sm mt-1" data-testid="scaf-item-size" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Spec</Label>
            <Input value={form.spec} onChange={(e) => setForm({ ...form, spec: e.target.value })} placeholder="48.3mm OD, 3.2mm" className="h-9 rounded-sm mt-1" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Unit</Label>
            <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Unit Weight (kg)</Label>
            <Input type="number" value={form.unit_weight_kg} onChange={(e) => setForm({ ...form, unit_weight_kg: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="scaf-item-weight" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Rate (₹)</Label>
            <Input type="number" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} className="h-9 rounded-sm mt-1 tabular" /></div>
          <div><Label className="text-[10px] uppercase tracking-wider">Min Stock</Label>
            <Input type="number" value={form.min_stock} onChange={(e) => setForm({ ...form, min_stock: e.target.value })} className="h-9 rounded-sm mt-1 tabular" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={save} data-testid="scaf-item-submit">{isNew ? "Create Item" : "Save Changes"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Bulk Import ───────────────────────────────────────────────────── */
function BulkImportDialog({ open, onClose, onChanged }) {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const { data } = await api.get("/scaffolding/import-template", { responseType: "blob" });
      const url = URL.createObjectURL(data); const a = document.createElement("a");
      a.href = url; a.download = "scaffolding_import_template.csv"; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Template download failed"); }
  };

  const upload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { toast.error("Choose a CSV file"); return; }
    const fd = new FormData(); fd.append("file", f);
    setBusy(true); setResult(null);
    try {
      const { data } = await api.post("/scaffolding/import.csv", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`Imported: ${data.created} created · ${data.updated} updated · ${data.opening_stock_set} stock rows`);
      onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setResult(null); onClose(); } }}>
      <DialogContent className="max-w-lg rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">Bulk Import Material List</DialogTitle>
          <DialogDescription>
            CSV columns: code, name, size, spec, unit, rate, min_stock, unit_weight_kg, location, opening_quantity.
            Existing items (matched by code or name) are updated — ideal for filling unit weights. New items are created.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Button variant="outline" className="rounded-sm w-full" onClick={downloadTemplate} data-testid="scaf-template-btn">
            <Download className="h-4 w-4 mr-1.5" /> Download CSV Template
          </Button>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">CSV File</Label>
            <Input ref={fileRef} type="file" accept=".csv" className="h-9 rounded-sm mt-1" data-testid="scaf-import-file" />
          </div>
          {result && (
            <div className="border border-border rounded-sm p-2.5 text-xs space-y-1" data-testid="scaf-import-result">
              <div className="font-bold">Result: {result.created} created · {result.updated} updated · {result.opening_stock_set} opening-stock rows set</div>
              {(result.errors || []).length > 0 && (
                <div className="max-h-28 overflow-y-auto space-y-0.5">
                  {result.errors.map((e, i) => <div key={`${e.row}-${i}`} className="text-rose-700">Row {e.row}: {e.error}</div>)}
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
          <Button className="rounded-sm" onClick={upload} disabled={busy} data-testid="scaf-import-submit">
            <Upload className="h-4 w-4 mr-1.5" /> {busy ? "Importing…" : "Import CSV"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
