import { useCallback, useEffect, useState } from "react";
import { Layers, RefreshCw, Warehouse, FileSpreadsheet, FileText, Plus, ArrowRightLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { TransfersTab, ChallansTab } from "./ScaffoldingMovements";

export const SCAF_APPROVE_ROLES = new Set(["super_admin", "store_manager", "inventory_manager", "dept_head", "general_manager", "director"]);

export default function Scaffolding() {
  const { user, can } = useAuth();
  const canWrite = can ? can("scaffolding", "write") : false;
  const canApprove = SCAF_APPROVE_ROLES.has(user?.role);
  const [summary, setSummary] = useState(null);
  const [locations, setLocations] = useState([]);
  const [items, setItems] = useState([]);
  const [bump, setBump] = useState(0);

  const reload = useCallback(() => {
    api.get("/scaffolding/summary").then((r) => setSummary(r.data)).catch(() => {});
    api.get("/scaffolding/locations").then((r) => setLocations(r.data || [])).catch(() => {});
    api.get("/scaffolding/items").then((r) => setItems(r.data || [])).catch(() => {});
    setBump((b) => b + 1);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const migrate = async () => {
    if (!window.confirm("Seed each catalog item's current global quantity into the Main Store? (one-time)")) return;
    try {
      const r = await api.post("/scaffolding/migrate-main-store");
      toast.success(`Migrated ${r.data.migrated} item(s) into ${r.data.store} (${r.data.skipped} skipped)`);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Migration failed"); }
  };

  const download = async (fmt, kind) => {
    try {
      const { data } = await api.get(`/scaffolding/export.${fmt}`, { responseType: "blob", params: { kind } });
      const url = URL.createObjectURL(data); const a = document.createElement("a");
      a.href = url; a.download = `scaffolding_${kind}.${fmt}`; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
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
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx", "stock")} data-testid="scaf-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Stock Excel</Button>
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

      <Tabs defaultValue="stock">
        <TabsList className="rounded-sm">
          <TabsTrigger value="stock" className="rounded-sm" data-testid="scaf-tab-stock">Stock Matrix</TabsTrigger>
          <TabsTrigger value="transfers" className="rounded-sm" data-testid="scaf-tab-transfers">Transfers</TabsTrigger>
          <TabsTrigger value="challans" className="rounded-sm" data-testid="scaf-tab-challans">Delivery Challans</TabsTrigger>
          <TabsTrigger value="items" className="rounded-sm" data-testid="scaf-tab-items">Item Catalog</TabsTrigger>
        </TabsList>
        <TabsContent value="stock" className="mt-4">
          <StockMatrixTab bump={bump} locations={locations} items={items} canWrite={canWrite} onChanged={reload} />
        </TabsContent>
        <TabsContent value="transfers" className="mt-4">
          <TransfersTab bump={bump} locations={locations} items={items} canWrite={canWrite} canApprove={canApprove} onChanged={reload} />
        </TabsContent>
        <TabsContent value="challans" className="mt-4">
          <ChallansTab bump={bump} canWrite={canWrite} onChanged={reload} />
        </TabsContent>
        <TabsContent value="items" className="mt-4">
          <ItemsTab items={items} canWrite={canWrite} onChanged={reload} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StockMatrixTab({ bump, locations, items, canWrite, onChanged }) {
  const [matrix, setMatrix] = useState(null);
  const [opening, setOpening] = useState(false);
  const [form, setForm] = useState({ item_id: "", location_id: "", quantity: "" });

  useEffect(() => { api.get("/scaffolding/stock-matrix").then((r) => setMatrix(r.data)).catch(() => {}); }, [bump]);

  const saveOpening = async () => {
    if (!form.item_id || !form.location_id) { toast.error("Pick item and location"); return; }
    try {
      const r = await api.post("/scaffolding/opening-stock", { ...form, quantity: Number(form.quantity) || 0 });
      toast.success(`${r.data.item} @ ${r.data.location} set to ${r.data.quantity}`);
      setOpening(false); setForm({ item_id: "", location_id: "", quantity: "" }); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const cols = matrix?.locations || [];
  const rows = matrix?.items || [];
  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-2">
          <ArrowRightLeft className="h-3 w-3" /> Item × Location Stock Matrix
        </div>
        {canWrite && (
          <Button size="sm" variant="outline" className="h-8 rounded-sm" onClick={() => setOpening(true)} data-testid="scaf-opening-btn">
            <Plus className="h-3.5 w-3.5 mr-1" /> Opening / Adjust Stock
          </Button>
        )}
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
            {cols.map((c) => <TableHead key={c.id} className="text-[10px] uppercase tracking-wider text-right whitespace-nowrap">{c.name}</TableHead>)}
            <TableHead className="text-[10px] uppercase tracking-wider text-right">In Transit</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Total</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={cols.length + 3} className="text-center py-10 text-muted-foreground">
                No location stock yet. Use "Migrate to Main Store" or add Opening Stock to begin.
              </TableCell></TableRow>
            )}
            {rows.map((it) => (
              <TableRow key={it.item_id} data-testid={`scaf-stock-row-${it.item_id}`}>
                <TableCell>
                  <div className="font-semibold text-sm">{it.item_name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono-data">{it.item_code}{it.size ? ` · ${it.size}` : ""} · {it.unit}</div>
                </TableCell>
                {cols.map((c) => (
                  <TableCell key={c.id} className="text-right font-mono-data tabular text-sm">{it.by_location[c.id] ?? "—"}</TableCell>
                ))}
                <TableCell className="text-right font-mono-data tabular text-sm text-amber-700">{it.in_transit || "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-sm font-bold">{it.total}</TableCell>
              </TableRow>
            ))}
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

function ItemsTab({ items, canWrite, onChanged }) {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", size: "", spec: "", unit: "Nos", rate: "", min_stock: "" });

  const create = async () => {
    if (!form.name.trim()) { toast.error("Item name required"); return; }
    try {
      const r = await api.post("/scaffolding/items", { ...form, rate: Number(form.rate) || 0, min_stock: Number(form.min_stock) || 0 });
      toast.success(`Item ${r.data.code} created`);
      setCreating(false); setForm({ name: "", code: "", size: "", spec: "", unit: "Nos", rate: "", min_stock: "" }); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const ql = q.trim().toLowerCase();
  const filtered = ql ? items.filter((i) => (i.name || "").toLowerCase().includes(ql) || (i.code || "").toLowerCase().includes(ql)) : items;

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center justify-between p-3 border-b border-border gap-2 flex-wrap">
        <Input placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 rounded-sm w-64 text-xs" data-testid="scaf-item-search" />
        {canWrite && (
          <Button size="sm" className="h-8 rounded-sm" onClick={() => setCreating(true)} data-testid="scaf-new-item">
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
          <TableHead className="text-[10px] uppercase tracking-wider text-right">Rate</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider text-right">Global Qty</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {filtered.slice(0, 300).map((i) => (
            <TableRow key={i.id} data-testid={`scaf-item-row-${i.id}`}>
              <TableCell className="font-mono-data text-xs font-bold">{i.code || i.sku || "—"}</TableCell>
              <TableCell className="text-sm font-semibold">{i.name}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{[i.size, i.spec].filter(Boolean).join(" · ") || "—"}</TableCell>
              <TableCell className="text-xs">{i.unit || i.uom || "Nos"}</TableCell>
              <TableCell className="text-right font-mono-data tabular text-xs">{i.rate ? `₹ ${Number(i.rate).toLocaleString("en-IN")}` : "—"}</TableCell>
              <TableCell className="text-right font-mono-data tabular text-xs font-bold">{i.quantity ?? 0}</TableCell>
            </TableRow>
          ))}
          {filtered.length === 0 && (
            <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No items found.</TableCell></TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">New Scaffolding Item</DialogTitle>
            <DialogDescription>Added to the item catalog with category "scaffolding".</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Vertical Standard 3m" className="h-9 rounded-sm mt-1" data-testid="scaf-item-name" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Code (auto if blank)</Label>
              <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="SCF-0001" className="h-9 rounded-sm mt-1" data-testid="scaf-item-code" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Size</Label>
              <Input value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} placeholder="3.0 m" className="h-9 rounded-sm mt-1" data-testid="scaf-item-size" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Spec</Label>
              <Input value={form.spec} onChange={(e) => setForm({ ...form, spec: e.target.value })} placeholder="48.3mm OD, 3.2mm" className="h-9 rounded-sm mt-1" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Unit</Label>
              <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Rate (₹)</Label>
              <Input type="number" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} className="h-9 rounded-sm mt-1 tabular" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Min Stock</Label>
              <Input type="number" value={form.min_stock} onChange={(e) => setForm({ ...form, min_stock: e.target.value })} className="h-9 rounded-sm mt-1 tabular" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="scaf-item-submit">Create Item</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
