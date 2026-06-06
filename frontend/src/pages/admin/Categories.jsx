import { useEffect, useMemo, useState } from "react";
import { Tag, Plus, Edit2, Trash2, Search, Power, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";

const blank = () => ({ code: "", name: "", description: "", gst_pct: 18, default_hsn: "", active: true });

export default function Categories() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank());
  const [itemDialog, setItemDialog] = useState(null); // current category to view items for

  const load = async () => {
    try {
      const r = await api.get("/procurement/master/categories");
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) =>
      [r.code, r.name, r.description, r.default_hsn].some((v) => (v || "").toLowerCase().includes(s)));
  }, [rows, q]);

  const save = async () => {
    if (!form.code.trim() || !form.name.trim()) { toast.error("Code & name required"); return; }
    try {
      if (editing) {
        await api.put(`/procurement/master/categories/${editing.id}`, form);
        toast.success("Updated");
      } else {
        await api.post("/procurement/master/categories", form);
        toast.success("Created");
      }
      setOpen(false); setEditing(null); setForm(blank()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete category '${r.name}'?`)) return;
    try { await api.delete(`/procurement/master/categories/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const toggle = async (r) => {
    try { await api.put(`/procurement/master/categories/${r.id}`, { active: !r.active }); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Toggle failed"); }
  };
  const viewItems = async (cat) => {
    try {
      const r = await api.get(`/procurement/master/items?category_id=${cat.id}`);
      setItems(r.data || []); setItemDialog(cat);
    } catch (e) { toast.error(e.response?.data?.detail || "Load items failed"); }
  };

  return (
    <div className="space-y-6" data-testid="categories-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Tag className="h-3 w-3" /> Admin · Procurement Master
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Categories</h1>
        <p className="text-sm text-muted-foreground mt-1">Master list of material / service categories. Used by PR dropdowns, item master, and cost center auto-provisioning.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="cat-search" />
          </div>
          <span className="text-[11px] text-muted-foreground">{filtered.length} of {rows.length}</span>
          <Button className="ml-auto h-9 rounded-sm" onClick={() => { setEditing(null); setForm(blank()); setOpen(true); }} data-testid="cat-add">
            <Plus className="h-4 w-4 mr-1.5" /> New Category
          </Button>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">GST %</TableHead>
                <TableHead>Default HSN</TableHead>
                <TableHead className="text-right">Items</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => (
                <TableRow key={r.id} className={r.active === false ? "opacity-60" : ""} data-testid={`cat-row-${r.id}`}>
                  <TableCell className="font-bold text-[10px] uppercase tracking-wider">{r.code}</TableCell>
                  <TableCell className="font-semibold text-sm">{r.name}</TableCell>
                  <TableCell className="text-[12px] text-muted-foreground max-w-md truncate">{r.description}</TableCell>
                  <TableCell className="text-right tabular">{r.gst_pct ?? "—"}</TableCell>
                  <TableCell className="font-mono text-[12px]">{r.default_hsn || "—"}</TableCell>
                  <TableCell className="text-right">
                    <button className="text-primary hover:underline text-[12px]" onClick={() => viewItems(r)} data-testid={`cat-items-${r.id}`}>
                      <Layers className="h-3 w-3 inline mr-1" />{r.item_count || 0}
                    </button>
                  </TableCell>
                  <TableCell>
                    {r.active === false
                      ? <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm bg-red-100 text-red-900 border border-red-300">inactive</span>
                      : <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm bg-emerald-100 text-emerald-900 border border-emerald-300">active</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => { setEditing(r); setForm({ ...blank(), ...r }); setOpen(true); }} data-testid={`cat-edit-${r.id}`}>
                        <Edit2 className="h-3 w-3" />
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => toggle(r)} data-testid={`cat-toggle-${r.id}`}>
                        <Power className="h-3 w-3" />
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r)} data-testid={`cat-delete-${r.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Tag className="h-4 w-4 text-primary" /> {editing ? "Edit" : "New"} Category</DialogTitle>
            <DialogDescription>Categories drive PR dropdowns, item master, and cost-center provisioning per project.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Code *" value={form.code} onChange={(v) => setForm({ ...form, code: v.toUpperCase() })} testid="cat-form-code" />
              <Field label="Default HSN" value={form.default_hsn} onChange={(v) => setForm({ ...form, default_hsn: v })} testid="cat-form-hsn" />
              <Field label="GST %" type="number" value={form.gst_pct} onChange={(v) => setForm({ ...form, gst_pct: Number(v) })} testid="cat-form-gst" />
              <label className="flex items-end gap-2 text-sm cursor-pointer pb-1">
                <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} data-testid="cat-form-active" /> Active
              </label>
            </div>
            <Field label="Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="cat-form-name" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Description</Label>
              <Textarea value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-sm mt-1 min-h-[80px]" data-testid="cat-form-desc" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="cat-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ItemsDialog open={!!itemDialog} onClose={() => setItemDialog(null)} category={itemDialog} items={items}
                   reload={() => itemDialog && viewItems(itemDialog)} />
    </div>
  );
}

function ItemsDialog({ open, onClose, category, items, reload }) {
  const [open2, setOpen2] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", unit: "Nos", hsn_sac: "", last_rate: 0, active: true });
  const save = async () => {
    if (!form.code || !form.name) { toast.error("Code & name required"); return; }
    try {
      await api.post("/procurement/master/items", { ...form, category_id: category.id });
      toast.success("Item added"); setOpen2(false);
      setForm({ code: "", name: "", unit: "Nos", hsn_sac: "", last_rate: 0, active: true });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (it) => {
    if (!window.confirm(`Delete '${it.name}'?`)) return;
    try { await api.delete(`/procurement/master/items/${it.id}`); reload(); toast.success("Deleted"); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Layers className="h-4 w-4 text-primary" /> Items in {category?.name}</DialogTitle>
          <DialogDescription>{items?.length || 0} item(s) under this category.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[400px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead className="text-right">Last Rate</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((it) => (
                <TableRow key={it.id} data-testid={`item-row-${it.id}`}>
                  <TableCell className="font-mono text-[11px]">{it.code}</TableCell>
                  <TableCell className="text-sm">{it.name}</TableCell>
                  <TableCell className="text-[12px]">{it.unit}</TableCell>
                  <TableCell className="text-right tabular">{Number(it.last_rate || 0).toLocaleString("en-IN")}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(it)} data-testid={`item-delete-${it.id}`}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {open2 ? (
          <div className="border-t border-border pt-3 grid grid-cols-2 gap-2">
            <Field label="Code *" value={form.code} onChange={(v) => setForm({ ...form, code: v.toUpperCase() })} testid="item-form-code" />
            <Field label="Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="item-form-name" />
            <Field label="Unit" value={form.unit} onChange={(v) => setForm({ ...form, unit: v })} testid="item-form-unit" />
            <Field label="HSN/SAC" value={form.hsn_sac} onChange={(v) => setForm({ ...form, hsn_sac: v })} testid="item-form-hsn" />
            <Field label="Last Rate" type="number" value={form.last_rate} onChange={(v) => setForm({ ...form, last_rate: Number(v) })} testid="item-form-rate" />
            <div className="flex items-end gap-2">
              <Button className="h-9 rounded-sm" onClick={save} data-testid="item-form-save">Save Item</Button>
              <Button variant="outline" className="h-9 rounded-sm" onClick={() => setOpen2(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
            <Button className="rounded-sm" onClick={() => setOpen2(true)} data-testid="item-add"><Plus className="h-4 w-4 mr-1" /> Add Item</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
