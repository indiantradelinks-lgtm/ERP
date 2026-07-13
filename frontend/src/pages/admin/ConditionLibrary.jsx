import { useEffect, useMemo, useState } from "react";
import { ListPlus, Plus, Edit2, Trash2, Search, Library } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CATEGORIES = ["technical", "commercial", "inclusion", "exclusion"];
const SERVICES = ["common", "scaffolding", "painting", "rope_access", "insulation", "roof_sheeting"];
const blank = () => ({ category: "technical", service: "common", text: "", order: 99, active: true });

export default function ConditionLibrary() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blank());
  const [q, setQ] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [filterSvc, setFilterSvc] = useState("");

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filterCat) params.set("category", filterCat);
      // svc filter: server side returns service + common when filtered, but we want to also
      // see only-common rows. So we filter client-side instead.
      const r = await api.get("/quotation-builder/conditions" + (params.toString() ? `?${params}` : ""));
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filterCat]);

  const filtered = useMemo(() => {
    let arr = rows;
    if (filterSvc) arr = arr.filter((r) => r.service === filterSvc);
    if (q.trim()) {
      const s = q.toLowerCase();
      arr = arr.filter((r) => (r.text || "").toLowerCase().includes(s) || (r.service || "").toLowerCase().includes(s));
    }
    return arr;
  }, [rows, q, filterSvc]);

  const grouped = useMemo(() => {
    const out = {};
    filtered.forEach((r) => {
      const k = r.category;
      (out[k] = out[k] || []).push(r);
    });
    return out;
  }, [filtered]);

  const save = async () => {
    if (!form.text.trim()) { toast.error("Text is required"); return; }
    try {
      if (editing) {
        await api.put(`/quotation-builder/conditions/${editing.id}`, form);
        toast.success("Updated");
      } else {
        await api.post("/quotation-builder/conditions", form);
        toast.success("Created");
      }
      setOpen(false); setEditing(null); setForm(blank()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm("Delete this clause?")) return;
    try { await api.delete(`/quotation-builder/conditions/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const edit = (r) => { setEditing(r); setForm({ ...blank(), ...r }); setOpen(true); };

  return (
    <div className="space-y-6" data-testid="condition-library-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Library className="h-3 w-3" /> Quotation · Clause Library
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Conditions Library</h1>
        <p className="text-sm text-muted-foreground mt-1">Technical / commercial conditions, inclusions and exclusions consumed by the AI Quotation Builder. Service = "common" applies to every quotation.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search clauses…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="cl-search" />
          </div>
          <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="cl-filter-cat">
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterSvc} onChange={(e) => setFilterSvc(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="cl-filter-svc">
            <option value="">All services</option>
            {SERVICES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </select>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => { setEditing(null); setForm(blank()); setOpen(true); }} data-testid="cl-add">
              <Plus className="h-4 w-4 mr-1" /> New Clause
            </Button>
          </div>
        </div>

        <div className="p-3 space-y-4">
          {Object.keys(grouped).length === 0 && <div className="text-center text-sm text-muted-foreground py-10">No clauses match the filter.</div>}
          {CATEGORIES.filter((c) => grouped[c]?.length).map((cat) => (
            <div key={cat} className="border border-border rounded-sm" data-testid={`cl-group-${cat}`}>
              <div className="p-2.5 border-b border-border bg-muted/30 flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{cat} · {grouped[cat].length}</span>
              </div>
              <ul className="divide-y divide-border">
                {grouped[cat].map((r) => (
                  <li key={r.id} className="p-3 flex gap-3 items-start" data-testid={`cl-row-${r.id}`}>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-2 py-0.5 rounded-sm border border-border bg-background mt-0.5">{r.service?.replaceAll("_", " ")}</span>
                    <div className="flex-1 text-sm">{r.text}</div>
                    <div className="inline-flex gap-1 shrink-0">
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => edit(r)} data-testid={`cl-edit-${r.id}`}><Edit2 className="h-3 w-3" /></Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r)} data-testid={`cl-del-${r.id}`}><Trash2 className="h-3 w-3" /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><ListPlus className="h-4 w-4 text-primary" /> {editing ? "Edit" : "New"} Clause</DialogTitle>
            <DialogDescription className="sr-only">Add or edit a quotation clause.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <Sel label="Category" value={form.category} options={CATEGORIES} onChange={(v) => setForm({ ...form, category: v })} testid="cl-form-category" />
              <Sel label="Service" value={form.service} options={SERVICES} onChange={(v) => setForm({ ...form, service: v })} testid="cl-form-service" />
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Order</Label>
                <Input type="number" value={form.order} onChange={(e) => setForm({ ...form, order: Number(e.target.value) })} className="h-9 rounded-sm mt-1 tabular" data-testid="cl-form-order" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} data-testid="cl-form-active" /> Active
                </label>
              </div>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Clause text *</Label>
              <Textarea value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} className="rounded-sm mt-1 min-h-[100px]" data-testid="cl-form-text" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="cl-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Sel({ label, value, options, onChange, testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={testid}>
        {options.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
      </select>
    </div>
  );
}
