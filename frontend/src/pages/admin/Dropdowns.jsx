import { useEffect, useState } from "react";
import { Plus, Trash2, Pencil, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function Dropdowns() {
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ category: "", label: "", value: "", order: 0, active: true });

  const load = async () => {
    try {
      const { data } = await api.get("/admin/dropdowns");
      setRows(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load dropdowns");
    }
  };
  useEffect(() => { load(); }, []);

  const filtered = rows.filter((r) =>
    !query || [r.category, r.label, r.value].some((v) => String(v ?? "").toLowerCase().includes(query.toLowerCase()))
  );

  const startCreate = () => {
    setEditing(null);
    setForm({ category: "", label: "", value: "", order: 0, active: true });
    setOpen(true);
  };
  const startEdit = (row) => {
    setEditing(row);
    setForm({ category: row.category, label: row.label, value: row.value, order: row.order ?? 0, active: row.active !== false });
    setOpen(true);
  };

  const save = async () => {
    try {
      const payload = { ...form, order: Number(form.order) || 0 };
      if (editing) await api.put(`/admin/dropdowns/${editing.id}`, payload);
      else await api.post("/admin/dropdowns", payload);
      toast.success(editing ? "Updated" : "Created");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this option?")) return;
    try {
      await api.delete(`/admin/dropdowns/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-dropdowns">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Super Admin · Dropdown Master</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Dropdown Options</h1>
        <p className="text-sm text-muted-foreground mt-1">Categorised select-list values. Forms across modules read from <code className="font-mono-data text-xs bg-muted px-1 py-0.5 rounded">/api/admin/dropdowns/by-category/&lt;category&gt;</code>.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border gap-3">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="dropdowns-search" />
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="h-9 rounded-sm" onClick={startCreate} data-testid="dropdowns-add"><Plus className="h-4 w-4 mr-1" /> New Option</Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg rounded-sm">
              <DialogHeader>
                <DialogTitle className="font-display">{editing ? "Edit Option" : "New Option"}</DialogTitle>
                <DialogDescription className="sr-only">Manage a single dropdown option.</DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Category</Label>
                  <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="h-9 rounded-sm mt-1.5" placeholder="e.g. project_status" data-testid="dropdowns-field-category" />
                </div>
                <div><Label className="text-xs uppercase tracking-wider">Label</Label>
                  <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="dropdowns-field-label" />
                </div>
                <div><Label className="text-xs uppercase tracking-wider">Value</Label>
                  <Input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="dropdowns-field-value" />
                </div>
                <div><Label className="text-xs uppercase tracking-wider">Order</Label>
                  <Input type="number" value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="dropdowns-field-order" />
                </div>
                <div className="flex items-end gap-2">
                  <input id="active" type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} className="h-4 w-4" data-testid="dropdowns-field-active" />
                  <Label htmlFor="active" className="text-xs uppercase tracking-wider">Active</Label>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
                <Button className="rounded-sm" onClick={save} data-testid="dropdowns-save">Save</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Category</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Label</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Order</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
              <TableHead className="text-right w-24">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-10">No options yet.</TableCell></TableRow>
            )}
            {filtered.map((r) => (
              <TableRow key={r.id} className="hover:bg-muted/30">
                <TableCell className="text-sm font-mono-data">{r.category}</TableCell>
                <TableCell className="text-sm font-semibold">{r.label}</TableCell>
                <TableCell className="text-sm text-muted-foreground font-mono-data">{r.value}</TableCell>
                <TableCell className="text-sm tabular">{r.order ?? 0}</TableCell>
                <TableCell><StatusBadge text={r.active === false ? "inactive" : "active"} tone={r.active === false ? "neutral" : "success"} /></TableCell>
                <TableCell className="text-right">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => startEdit(r)} data-testid={`dropdowns-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => remove(r.id)} data-testid={`dropdowns-delete-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="px-4 py-2 border-t border-border text-xs text-muted-foreground">
          Showing <span className="text-foreground font-semibold">{filtered.length}</span> of {rows.length}
        </div>
      </div>
    </div>
  );
}
