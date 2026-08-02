import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Wallet, Pencil, Trash2, FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect, useCategories } from "@/components/MasterSelect";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const FREQS = [
  { value: "daily", label: "Daily Budget" },
  { value: "weekly", label: "Weekly Budget" },
  { value: "monthly", label: "Monthly Budget" },
  { value: "yearly", label: "Year Budget" },
  { value: "one_time", label: "One Time Budget" },
];
const FREQ_TONE = { daily: "bg-sky-50 text-sky-800 border-sky-200", weekly: "bg-violet-50 text-violet-800 border-violet-200",
  monthly: "bg-emerald-50 text-emerald-800 border-emerald-200", yearly: "bg-amber-50 text-amber-800 border-amber-200",
  one_time: "bg-slate-100 text-slate-700 border-slate-300" };

const blank = () => ({ project_id: "", project_code: "", category_id: "", cost_center_id: "",
  description: "", frequency: "monthly", amount: "", start_date: "", end_date: "", total_override: "", remarks: "" });

function previewTotal(f) {
  const amt = Number(f.amount || 0);
  if (f.total_override) return Number(f.total_override);
  if (f.frequency === "one_time" || !f.start_date || !f.end_date) return amt;
  const days = Math.floor((new Date(f.end_date) - new Date(f.start_date)) / 86400000) + 1;
  if (days <= 0) return amt;
  const units = { daily: days, weekly: Math.ceil(days / 7), monthly: Math.max(1, Math.round(days / 30.44)), yearly: Math.max(1, Math.ceil(days / 365.25)) }[f.frequency] || 1;
  return amt * units;
}

const Sel = ({ label, value, onChange, children, testid }) => (
  <div>
    <Label className="text-xs">{label}</Label>
    <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}
      className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1">
      {children}
    </select>
  </div>
);

export default function ProjectBudgetPlanner() {
  const { can } = useAuth();
  const canWrite = can ? can("projects", "write") : true;
  const categories = useCategories();
  const [rows, setRows] = useState([]);
  const [report, setReport] = useState({ groups: [], grand_total: 0, count: 0 });
  const [groupBy, setGroupBy] = useState("category");
  const [filters, setFilters] = useState({ project_id: "", category_id: "", frequency: "", from_date: "", to_date: "" });
  const [projects, setProjects] = useState([]);
  const [ccList, setCcList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(blank());
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    api.get("/ops/project-budgets", { params }).then((r) => setRows(r.data || [])).catch(() => {});
    api.get("/ops/project-budgets/report", { params: { ...params, group_by: groupBy } })
      .then((r) => setReport(r.data || { groups: [], grand_total: 0, count: 0 })).catch(() => {});
  }, [filters, groupBy]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  const loadCC = (projectId) => {
    if (!projectId) return setCcList([]);
    api.get("/procurement/master/cost-centers", { params: { project_id: projectId } }).then((r) => setCcList(r.data || [])).catch(() => setCcList([]));
  };

  const openNew = () => { setEditId(null); setForm(blank()); setCcList([]); setOpen(true); };
  const openEdit = (r) => {
    setEditId(r.id);
    setForm({ project_id: r.project_id, project_code: r.project_code || "", category_id: r.category_id || "",
      cost_center_id: r.cost_center_id || "", description: r.description || "", frequency: r.frequency,
      amount: r.amount, start_date: r.start_date || "", end_date: r.end_date || "",
      total_override: r.total_override || "", remarks: r.remarks || "" });
    loadCC(r.project_id);
    setOpen(true);
  };

  const onProject = (code, row) => {
    const p = row || projects.find((x) => x.code === code);
    setForm((f) => ({ ...f, project_code: code, project_id: p?.id || "", cost_center_id: "",
      start_date: f.start_date || (p?.start_date || "").slice(0, 10), end_date: f.end_date || (p?.end_date || "").slice(0, 10) }));
    loadCC(p?.id);
  };

  const onCategory = (catId) => {
    const cat = categories.find((c) => c.id === catId);
    const cc = catId ? ccList.find((c) => c.category_id === catId || (cat && c.category_code === cat.code)) : null;
    setForm((f) => ({ ...f, category_id: catId, cost_center_id: cc ? cc.id : f.cost_center_id }));
  };

  const save = async () => {
    if (!form.project_id) return toast.error("Select a project");
    if (!form.category_id) return toast.error("Select a category");
    if (!Number(form.amount)) return toast.error("Enter a budget amount");
    setSaving(true);
    try {
      const payload = { ...form, amount: Number(form.amount), total_override: form.total_override ? Number(form.total_override) : null };
      if (editId) await api.put(`/ops/project-budgets/${editId}`, payload);
      else await api.post("/ops/project-budgets", payload);
      toast.success(editId ? "Budget line updated" : "Budget line added");
      setOpen(false); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete budget line for ${r.category_name || "this category"}?`)) return;
    try { await api.delete(`/ops/project-budgets/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  const download = async (fmt) => {
    const params = new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([, v]) => v)));
    try {
      const r = await api.get(`/ops/project-budgets/export.${fmt}?${params}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a"); a.href = url; a.download = `project_budget.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const preview = useMemo(() => previewTotal(form), [form]);

  return (
    <div className="space-y-4" data-testid="project-budget-planner">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display font-bold text-xl flex items-center gap-2"><Wallet className="h-5 w-5 text-primary" /> Project Budget</h2>
          <p className="text-xs text-muted-foreground">Category-wise budget lines per project · daily / weekly / monthly / yearly / one-time.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => download("xlsx")} data-testid="budget-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" size="sm" onClick={() => download("pdf")} data-testid="budget-export-pdf"><FileText className="h-4 w-4 mr-1" /> PDF</Button>
          <Button variant="outline" size="sm" onClick={load} data-testid="budget-refresh"><RefreshCw className="h-4 w-4" /></Button>
          {canWrite && <Button size="sm" onClick={openNew} data-testid="budget-new-btn"><Plus className="h-4 w-4 mr-1" /> New Budget Line</Button>}
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 border rounded-sm p-3 bg-slate-50/60" data-testid="budget-filters">
        <Sel label="Project" value={filters.project_id} onChange={(v) => setFilters((f) => ({ ...f, project_id: v }))} testid="budget-filter-project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
        </Sel>
        <Sel label="Category" value={filters.category_id} onChange={(v) => setFilters((f) => ({ ...f, category_id: v }))} testid="budget-filter-category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
        </Sel>
        <Sel label="Frequency" value={filters.frequency} onChange={(v) => setFilters((f) => ({ ...f, frequency: v }))} testid="budget-filter-frequency">
          <option value="">All frequencies</option>
          {FREQS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </Sel>
        <div><Label className="text-xs">From</Label><Input type="date" className="h-9 mt-1" value={filters.from_date} onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} data-testid="budget-filter-from" /></div>
        <div><Label className="text-xs">To</Label><Input type="date" className="h-9 mt-1" value={filters.to_date} onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} data-testid="budget-filter-to" /></div>
        <Sel label="Report group by" value={groupBy} onChange={setGroupBy} testid="budget-groupby">
          <option value="category">Category</option>
          <option value="project">Project</option>
          <option value="frequency">Frequency</option>
        </Sel>
      </div>

      {/* Summary report */}
      <div className="grid md:grid-cols-3 gap-3">
        <div className="border rounded-sm p-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Budget (filtered)</div>
          <div className="text-2xl font-bold" data-testid="budget-grand-total">{inr(report.grand_total)}</div>
          <div className="text-xs text-muted-foreground">{report.count} line(s)</div>
        </div>
        <div className="md:col-span-2 border rounded-sm overflow-auto max-h-44" data-testid="budget-report-groups">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-3 py-1.5 text-xs uppercase text-muted-foreground">By {groupBy}</th>
              <th className="text-right px-3 py-1.5 text-xs uppercase text-muted-foreground">Lines</th>
              <th className="text-right px-3 py-1.5 text-xs uppercase text-muted-foreground">Budget</th>
              <th className="text-right px-3 py-1.5 text-xs uppercase text-muted-foreground">%</th>
            </tr></thead>
            <tbody>
              {report.groups.map((g) => (
                <tr key={g.group} className="border-t">
                  <td className="px-3 py-1.5">{g.group}</td>
                  <td className="px-3 py-1.5 text-right">{g.lines}</td>
                  <td className="px-3 py-1.5 text-right font-semibold">{inr(g.total)}</td>
                  <td className="px-3 py-1.5 text-right text-muted-foreground">{report.grand_total ? ((g.total / report.grand_total) * 100).toFixed(1) : 0}%</td>
                </tr>
              ))}
              {!report.groups.length && <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">No budget lines yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Lines table */}
      <div className="border rounded-sm overflow-auto">
        <Table data-testid="budget-lines-table">
          <TableHeader>
            <TableRow>
              <TableHead>Project</TableHead><TableHead>Category</TableHead><TableHead>Cost Center</TableHead>
              <TableHead>Description</TableHead><TableHead>Frequency</TableHead>
              <TableHead className="text-right">Amount</TableHead><TableHead>Period</TableHead>
              <TableHead className="text-right">Units</TableHead><TableHead className="text-right">Total Budget</TableHead>
              {canWrite && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`budget-row-${r.id}`}>
                <TableCell className="whitespace-nowrap text-xs">{r.project_code}<div className="text-muted-foreground">{r.project_name}</div></TableCell>
                <TableCell className="text-xs">{r.category_name || "—"}</TableCell>
                <TableCell className="text-xs">{r.cost_center_label || "—"}</TableCell>
                <TableCell className="text-xs max-w-[220px] truncate">{r.description || "—"}</TableCell>
                <TableCell><Badge variant="outline" className={`text-[10px] ${FREQ_TONE[r.frequency] || ""}`}>{r.frequency_label}</Badge></TableCell>
                <TableCell className="text-right text-xs">{inr(r.amount)}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{r.start_date || "—"} → {r.end_date || "—"}</TableCell>
                <TableCell className="text-right text-xs">{r.units}</TableCell>
                <TableCell className="text-right font-semibold">{inr(r.total)}</TableCell>
                {canWrite && (
                  <TableCell className="text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(r)} data-testid={`budget-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-red-600" onClick={() => remove(r)} data-testid={`budget-delete-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">No budget lines. Click "New Budget Line" to start.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* Form dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editId ? "Edit Budget Line" : "New Budget Line"}</DialogTitle>
            <DialogDescription>Category-wise budget for a project. Total auto-computed from the period; override if needed.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <ProjectSelect label="Project *" value={form.project_code} onChange={onProject} testid="budget-form-project" />
            </div>
            <Sel label="Category *" value={form.category_id} onChange={onCategory} testid="budget-form-category">
              <option value="">— select category —</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
            </Sel>
            <Sel label="Cost Center" value={form.cost_center_id} onChange={(v) => setForm((f) => ({ ...f, cost_center_id: v }))} testid="budget-form-costcenter">
              <option value="">— select cost center —</option>
              {ccList.map((c) => <option key={c.id} value={c.id}>{c.category_code} · {c.category_name}</option>)}
            </Sel>
            <Sel label="Budget Frequency *" value={form.frequency} onChange={(v) => setForm((f) => ({ ...f, frequency: v }))} testid="budget-form-frequency">
              {FREQS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </Sel>
            <div>
              <Label className="text-xs">Amount (per {form.frequency === "one_time" ? "line" : form.frequency.replace("_", " ")}) *</Label>
              <Input type="number" min="0" className="h-9 mt-1" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} data-testid="budget-form-amount" />
            </div>
            <div><Label className="text-xs">Period From</Label><Input type="date" className="h-9 mt-1" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} data-testid="budget-form-start" /></div>
            <div><Label className="text-xs">Period To</Label><Input type="date" className="h-9 mt-1" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} data-testid="budget-form-end" /></div>
            <div className="col-span-2">
              <Label className="text-xs">Description</Label>
              <Input className="h-9 mt-1" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="e.g., Site labour daily wages" data-testid="budget-form-desc" />
            </div>
            <div>
              <Label className="text-xs">Total Override (optional)</Label>
              <Input type="number" min="0" className="h-9 mt-1" value={form.total_override} onChange={(e) => setForm((f) => ({ ...f, total_override: e.target.value }))} placeholder="Leave blank to auto-calc" data-testid="budget-form-override" />
            </div>
            <div className="flex items-end">
              <div className="border rounded-sm px-3 py-1.5 bg-emerald-50 text-emerald-900 text-sm w-full" data-testid="budget-form-preview">
                Computed total: <b>{inr(preview)}</b>
              </div>
            </div>
            <div className="col-span-2">
              <Label className="text-xs">Remarks</Label>
              <Textarea rows={2} value={form.remarks} onChange={(e) => setForm((f) => ({ ...f, remarks: e.target.value }))} data-testid="budget-form-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} disabled={saving} data-testid="budget-form-save">{saving ? "Saving…" : editId ? "Update" : "Save Budget Line"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
