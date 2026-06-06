import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Building2, Plus, Trash2, X as XIcon, Network } from "lucide-react";
import { toast } from "sonner";

export default function DepartmentMaster() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get("/admin/department-master"); setRows(data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const addItem = async (deptId, kind, value) => {
    if (!value) return;
    try { await api.post(`/admin/department-master/${deptId}/items`, { kind, value }); await load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const removeItem = async (deptId, kind, value) => {
    try { await api.delete(`/admin/department-master/${deptId}/items?kind=${kind}&value=${encodeURIComponent(value)}`); await load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const remove = async (id) => {
    if (!confirm("Delete this department?")) return;
    try { await api.delete(`/admin/department-master/${id}`); toast.success("Deleted"); await load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" data-testid="dept-master-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6 text-blue-600" /> Department Master
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            The 9 primary departments + sub-departments, branches and business units.
          </p>
        </div>
        <Button onClick={() => { setEditing(null); setShowAdd(true); }} data-testid="dept-add-btn">
          <Plus className="h-4 w-4 mr-1" /> Add Department
        </Button>
      </div>

      {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {rows.map((d) => (
            <Card key={d.id} data-testid={`dept-card-${d.slug}`}>
              <CardHeader className="flex flex-row items-center justify-between pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Badge variant="outline" className="font-mono">{d.code}</Badge>
                  {d.name}
                  {!d.active && <Badge className="bg-rose-100 text-rose-700">inactive</Badge>}
                </CardTitle>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(d); setShowAdd(true); }}>Edit</Button>
                  <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => remove(d.id)}><Trash2 className="h-3 w-3" /></Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ItemList title="Sub-departments" items={d.sub_departments || []} onAdd={(v) => addItem(d.id, "sub_departments", v)} onRemove={(v) => removeItem(d.id, "sub_departments", v)} testid={`subs-${d.slug}`} />
                <ItemList title="Branches" items={d.branches || []} onAdd={(v) => addItem(d.id, "branches", v)} onRemove={(v) => removeItem(d.id, "branches", v)} testid={`branches-${d.slug}`} />
                <ItemList title="Business Units" items={d.business_units || []} onAdd={(v) => addItem(d.id, "business_units", v)} onRemove={(v) => removeItem(d.id, "business_units", v)} testid={`bus-${d.slug}`} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showAdd && <EditDialog open={showAdd} dept={editing} onClose={() => { setShowAdd(false); setEditing(null); }} onSaved={load} />}
    </div>
  );
}

function ItemList({ title, items, onAdd, onRemove, testid }) {
  const [v, setV] = useState("");
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <Label className="text-xs font-semibold uppercase">{title}</Label>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      <div className="flex flex-wrap gap-1 mb-2">
        {items.length === 0 && <div className="text-xs text-muted-foreground">—</div>}
        {items.map((it) => (
          <Badge key={it} variant="secondary" className="flex items-center gap-1" data-testid={`${testid}-item-${it}`}>
            {it}
            <button onClick={() => onRemove(it)} className="hover:text-rose-600 ml-1" aria-label="remove"><XIcon className="h-3 w-3" /></button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-1">
        <Input value={v} onChange={(e) => setV(e.target.value)} placeholder={`Add ${title.toLowerCase()}…`} className="h-8 text-xs" onKeyDown={(e) => { if (e.key === "Enter") { onAdd(v); setV(""); } }} data-testid={`${testid}-input`} />
        <Button size="sm" variant="outline" onClick={() => { onAdd(v); setV(""); }} data-testid={`${testid}-add`}><Plus className="h-3 w-3" /></Button>
      </div>
    </div>
  );
}

function EditDialog({ open, dept, onClose, onSaved }) {
  const [form, setForm] = useState(() => dept || { slug: "", code: "", name: "", color: "neutral", active: true });
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!form.slug || !form.code || !form.name) { toast.error("Slug, code and name required"); return; }
    setSaving(true);
    try {
      if (dept) await api.put(`/admin/department-master/${dept.id}`, form);
      else await api.post("/admin/department-master", form);
      toast.success("Saved"); onSaved(); onClose();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{dept ? "Edit" : "Add"} Department</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Slug *</Label><Input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="qa-control" data-testid="dept-slug" /></div>
          <div><Label>Code *</Label><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="QA" maxLength={5} data-testid="dept-code" /></div>
          <div><Label>Name *</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Quality Assurance" data-testid="dept-name" /></div>
          <div className="flex items-center gap-2"><input type="checkbox" id="active" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /><Label htmlFor="active">Active</Label></div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={saving} data-testid="dept-save">{saving ? "…" : "Save"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
