import { useEffect, useMemo, useState } from "react";
import { Wallet, Plus, Edit2, Trash2, Wand2, Search, IndianRupee } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function CostCenters() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ project_id: "", category_id: "", code: "", name: "", budget: 0, active: true });

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || []))
       .catch((e) => toast.error(e.response?.data?.detail || "Load projects failed"));
    api.get("/procurement/master/categories?active_only=true").then((r) => setCategories(r.data || []))
       .catch(() => { });
  }, []);

  const load = async () => {
    if (!projectId) { setRows([]); return; }
    try {
      const r = await api.get(`/procurement/master/cost-centers?project_id=${projectId}`);
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [projectId]);

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) => [r.code, r.name, r.category_name].some((v) => (v || "").toLowerCase().includes(s)));
  }, [rows, q]);

  const totals = useMemo(() => ({
    budget: filtered.reduce((s, r) => s + Number(r.budget || 0), 0),
    committed: filtered.reduce((s, r) => s + Number(r.committed || 0), 0),
    actual: filtered.reduce((s, r) => s + Number(r.actual || 0), 0),
  }), [filtered]);

  const autoProvision = async () => {
    if (!projectId) { toast.error("Select a project first"); return; }
    try {
      const r = await api.post(`/procurement/master/cost-centers/auto-provision/${projectId}`);
      toast.success(r.data.created ? `Created ${r.data.created} cost center(s)` : "All categories already have cost centers");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Auto-provision failed"); }
  };
  const save = async () => {
    try {
      if (editing) {
        await api.put(`/procurement/master/cost-centers/${editing.id}`, { name: form.name, budget: Number(form.budget) || 0, active: form.active });
        toast.success("Updated");
      } else {
        if (!form.project_id || !form.category_id) { toast.error("Project & category required"); return; }
        await api.post("/procurement/master/cost-centers", { ...form, budget: Number(form.budget) || 0 });
        toast.success("Created");
      }
      setOpen(false); setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete cost center ${r.code}?`)) return;
    try { await api.delete(`/procurement/master/cost-centers/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="space-y-6" data-testid="cost-centers-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Wallet className="h-3 w-3" /> Admin · Cost Centers
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project Cost Centers</h1>
        <p className="text-sm text-muted-foreground mt-1">Track budget vs committed (PO) vs actual (GRN) per (project × category). PRs auto-stamp the matching cost center on every line item.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Project</Label>
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                    className="h-9 mt-1 rounded-sm border border-input bg-background px-2 text-sm min-w-[280px]" data-testid="cc-project-select">
              <option value="">— select a project —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
          </div>
          <div className="flex-1 max-w-md">
            <Label className="text-[10px] uppercase tracking-wider">Search</Label>
            <div className="relative mt-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9 h-9 rounded-sm" placeholder="Search code / category…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="cc-search" />
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="rounded-sm h-9" onClick={autoProvision} disabled={!projectId} data-testid="cc-auto-provision">
              <Wand2 className="h-3.5 w-3.5 mr-1.5" /> Auto-Provision Missing
            </Button>
            <Button className="rounded-sm h-9" onClick={() => { setEditing(null); setForm({ project_id: projectId, category_id: "", code: "", name: "", budget: 0, active: true }); setOpen(true); }} disabled={!projectId} data-testid="cc-add">
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Cost Center
            </Button>
          </div>
        </div>
        {projectId && (
          <div className="px-4 py-2 bg-muted/30 flex flex-wrap gap-4 text-[12px] border-b border-border">
            <span>Total Budget: <b className="tabular">{inr(totals.budget)}</b></span>
            <span>Committed (PO): <b className="tabular text-amber-700">{inr(totals.committed)}</b></span>
            <span>Actual (GRN): <b className="tabular text-emerald-700">{inr(totals.actual)}</b></span>
            <span>Remaining: <b className="tabular text-primary">{inr(totals.budget - totals.committed)}</b></span>
          </div>
        )}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Budget</TableHead>
                <TableHead className="text-right">Committed (PO)</TableHead>
                <TableHead className="text-right">Actual (GRN)</TableHead>
                <TableHead className="text-right">Remaining</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => {
                const remaining = Number(r.budget || 0) - Number(r.committed || 0);
                return (
                  <TableRow key={r.id} className={r.active === false ? "opacity-60" : ""} data-testid={`cc-row-${r.id}`}>
                    <TableCell className="font-mono text-[11px]">{r.code}</TableCell>
                    <TableCell className="font-semibold text-sm">{r.category_name}</TableCell>
                    <TableCell className="text-right tabular">{inr(r.budget)}</TableCell>
                    <TableCell className="text-right tabular text-amber-700">{inr(r.committed)}</TableCell>
                    <TableCell className="text-right tabular text-emerald-700">{inr(r.actual)}</TableCell>
                    <TableCell className={`text-right tabular ${remaining < 0 ? "text-red-700 font-bold" : ""}`}>{inr(remaining)}</TableCell>
                    <TableCell>
                      {r.active === false
                        ? <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm bg-red-100 text-red-900 border border-red-300">inactive</span>
                        : <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm bg-emerald-100 text-emerald-900 border border-emerald-300">active</span>}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => { setEditing(r); setForm({ ...r, project_id: r.project_id, category_id: r.category_id }); setOpen(true); }} data-testid={`cc-edit-${r.id}`}>
                          <Edit2 className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r)} data-testid={`cc-delete-${r.id}`}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {!projectId && (
                <TableRow><TableCell colSpan={8} className="text-center py-6 text-muted-foreground">Pick a project to see / manage its cost centers.</TableCell></TableRow>
              )}
              {projectId && filtered.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center py-6 text-muted-foreground">No cost centers yet — click "Auto-Provision Missing" to create one per active category.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><IndianRupee className="h-4 w-4 text-primary" /> {editing ? "Edit" : "New"} Cost Center</DialogTitle>
            <DialogDescription>One cost center per (project, category). PRs and POs auto-tag the line items with this CC code.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {!editing && (
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Category *</Label>
                <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                        className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="cc-form-category">
                  <option value="">— select —</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
                </select>
              </div>
            )}
            {editing && <Field label="Code" value={form.code} onChange={() => { }} testid="cc-form-code" /> /* read-only */}
            <Field label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="cc-form-name" />
            <Field label="Budget (₹)" type="number" value={form.budget} onChange={(v) => setForm({ ...form, budget: v })} testid="cc-form-budget" />
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} data-testid="cc-form-active" /> Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="cc-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
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
