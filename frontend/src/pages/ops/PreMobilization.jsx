import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, ListChecks, Pencil, Trash2, AlertTriangle, CheckCircle2, Boxes, Users, CircleDot } from "lucide-react";
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
import { ProjectSelect } from "@/components/MasterSelect";
import { lookupGet } from "@/lib/lookups";

const TYPES = [
  { value: "material", label: "Material", Icon: Boxes },
  { value: "manpower", label: "Manpower", Icon: Users },
  { value: "other", label: "Other", Icon: CircleDot },
];
const TYPE_TONE = { material: "bg-sky-50 text-sky-800 border-sky-200", manpower: "bg-violet-50 text-violet-800 border-violet-200", other: "bg-slate-100 text-slate-700 border-slate-300" };
const STATUS_TONE = { pending: "bg-amber-50 text-amber-800 border-amber-200", in_progress: "bg-blue-50 text-blue-800 border-blue-200", completed: "bg-emerald-50 text-emerald-800 border-emerald-200" };
const CONCERNS = [
  { value: "needs_extension", label: "Needs Date Extension" },
  { value: "on_hold", label: "On Hold" },
  { value: "other", label: "Other Problem" },
];

const blank = () => ({ project_id: "", project_code: "", item_type: "material", name: "", qty: "", unit: "", target_date: "", status: "pending", remarks: "" });

const Sel = ({ label, value, onChange, children, testid }) => (
  <div>
    <Label className="text-xs">{label}</Label>
    <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}
      className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1">{children}</select>
  </div>
);

const Chip = ({ label, value, tone, testid }) => (
  <div className={`border rounded-sm px-3 py-2 ${tone || ""}`} data-testid={testid}>
    <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
    <div className="text-xl font-bold">{value}</div>
  </div>
);

export default function PreMobilization() {
  const { can } = useAuth();
  const canWrite = can ? can("projects", "write") : true;
  const [rows, setRows] = useState([]);
  const [sum, setSum] = useState({});
  const [projects, setProjects] = useState([]);
  const [filters, setFilters] = useState({ project_id: "", item_type: "", status: "", flagged: false });
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(blank());
  const [concernFor, setConcernFor] = useState(null);
  const [concern, setConcern] = useState({ type: "needs_extension", note: "", proposed_date: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    api.get("/ops/premob-items", { params }).then((r) => setRows(r.data || [])).catch(() => {});
    api.get("/ops/premob-items/summary", { params: filters.project_id ? { project_id: filters.project_id } : {} })
      .then((r) => setSum(r.data || {})).catch(() => {});
  }, [filters]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  const openNew = () => { setEditId(null); setForm({ ...blank(), project_id: filters.project_id }); setOpen(true); };
  const openEdit = (r) => {
    setEditId(r.id);
    setForm({ project_id: r.project_id, project_code: r.project_code || "", item_type: r.item_type, name: r.name,
      qty: r.qty ?? "", unit: r.unit || "", target_date: r.target_date || "", status: r.status, remarks: r.remarks || "" });
    setOpen(true);
  };

  const save = async () => {
    if (!form.project_id) return toast.error("Select a project");
    if (!form.name.trim()) return toast.error("Enter item name");
    if (!form.target_date) return toast.error("Set a target date");
    setSaving(true);
    try {
      const payload = { ...form, qty: form.qty === "" ? null : Number(form.qty) };
      if (editId) await api.put(`/ops/premob-items/${editId}`, payload);
      else await api.post("/ops/premob-items", payload);
      toast.success(editId ? "Item updated" : "Item added");
      setOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const setStatus = async (r, status) => {
    try {
      await api.put(`/ops/premob-items/${r.id}`, { project_id: r.project_id, item_type: r.item_type, name: r.name,
        qty: r.qty, unit: r.unit, target_date: r.target_date, status, remarks: r.remarks });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Update failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.name}"?`)) return;
    try { await api.delete(`/ops/premob-items/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  const raiseConcern = async () => {
    if (!concern.note.trim() && concern.type === "other") return toast.error("Describe the problem");
    if (concern.type === "needs_extension" && !concern.proposed_date) return toast.error("Propose a new date");
    try {
      await api.post(`/ops/premob-items/${concernFor.id}/concern`, concern);
      toast.success("Concern raised");
      setConcernFor(null); setConcern({ type: "needs_extension", note: "", proposed_date: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const resolveConcern = async (r) => {
    const isExt = r.concern?.type === "needs_extension";
    if (!window.confirm(isExt ? `Resolve & extend target date to ${r.concern.proposed_date}?` : "Mark this concern as resolved?")) return;
    try { await api.post(`/ops/premob-items/${r.id}/concern/resolve`); toast.success("Concern resolved"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const flaggedRows = rows.filter((r) => r.is_delayed || r.concern);

  return (
    <div className="space-y-4" data-testid="premob-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display font-bold text-xl flex items-center gap-2"><ListChecks className="h-5 w-5 text-primary" /> Pre-Mobilization Plan</h2>
          <p className="text-xs text-muted-foreground">Item-wise material & manpower plan · target dates · delays flagged automatically.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="premob-refresh"><RefreshCw className="h-4 w-4" /></Button>
          {canWrite && <Button size="sm" onClick={openNew} data-testid="premob-new-btn"><Plus className="h-4 w-4 mr-1" /> Add Item</Button>}
        </div>
      </div>

      {/* Delay / concern alert banner */}
      {flaggedRows.length > 0 && (
        <div className="border border-red-200 bg-red-50 rounded-sm p-3 text-sm text-red-900 flex items-start gap-2" data-testid="premob-alert-banner">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <b>{flaggedRows.length} item(s) need attention:</b>{" "}
            {flaggedRows.slice(0, 5).map((r) => `${r.name}${r.is_delayed ? " (delayed)" : ""}${r.concern ? ` — ${r.concern.type_label}` : ""}`).join(" · ")}
            {flaggedRows.length > 5 ? ` · +${flaggedRows.length - 5} more` : ""}
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <Chip label="Total" value={sum.total ?? 0} testid="premob-sum-total" />
        <Chip label="Pending" value={sum.pending ?? 0} tone="bg-amber-50 border-amber-200" testid="premob-sum-pending" />
        <Chip label="In Progress" value={sum.in_progress ?? 0} tone="bg-blue-50 border-blue-200" testid="premob-sum-progress" />
        <Chip label="Completed" value={sum.completed ?? 0} tone="bg-emerald-50 border-emerald-200" testid="premob-sum-completed" />
        <Chip label="Delayed" value={sum.delayed ?? 0} tone="bg-red-50 border-red-200 text-red-900" testid="premob-sum-delayed" />
        <Chip label="Concerns" value={sum.concerns ?? 0} tone="bg-orange-50 border-orange-200 text-orange-900" testid="premob-sum-concerns" />
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 border rounded-sm p-3 bg-slate-50/60">
        <Sel label="Project" value={filters.project_id} onChange={(v) => setFilters((f) => ({ ...f, project_id: v }))} testid="premob-filter-project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
        </Sel>
        <Sel label="Type" value={filters.item_type} onChange={(v) => setFilters((f) => ({ ...f, item_type: v }))} testid="premob-filter-type">
          <option value="">All types</option>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Sel>
        <Sel label="Status" value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} testid="premob-filter-status">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
        </Sel>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={filters.flagged} onChange={(e) => setFilters((f) => ({ ...f, flagged: e.target.checked }))} data-testid="premob-filter-flagged" />
            Delayed / concerns only
          </label>
        </div>
      </div>

      {/* Items table */}
      <div className="border rounded-sm overflow-auto">
        <Table data-testid="premob-table">
          <TableHeader>
            <TableRow>
              <TableHead>Project</TableHead><TableHead>Type</TableHead><TableHead>Item</TableHead>
              <TableHead className="text-right">Qty</TableHead><TableHead>Target Date</TableHead>
              <TableHead>Status</TableHead><TableHead>Flags</TableHead>
              {canWrite && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} className={r.is_delayed ? "bg-red-50/50" : ""} data-testid={`premob-row-${r.id}`}>
                <TableCell className="text-xs whitespace-nowrap">{r.project_code}</TableCell>
                <TableCell><Badge variant="outline" className={`text-[10px] ${TYPE_TONE[r.item_type]}`}>{r.item_type}</Badge></TableCell>
                <TableCell className="text-sm font-medium">{r.name}{r.remarks && <div className="text-[11px] text-muted-foreground font-normal max-w-[220px] truncate">{r.remarks}</div>}</TableCell>
                <TableCell className="text-right text-xs">{r.qty ?? "—"} {r.unit || ""}</TableCell>
                <TableCell className={`text-xs whitespace-nowrap ${r.is_delayed ? "text-red-700 font-semibold" : ""}`}>{r.target_date || "—"}{r.completed_on && <div className="text-emerald-700">✓ {r.completed_on}</div>}</TableCell>
                <TableCell>
                  {canWrite ? (
                    <select value={r.status} onChange={(e) => setStatus(r, e.target.value)} data-testid={`premob-status-${r.id}`}
                      className={`h-8 rounded-sm border px-1.5 text-xs ${STATUS_TONE[r.status]}`}>
                      <option value="pending">Pending</option>
                      <option value="in_progress">In Progress</option>
                      <option value="completed">Completed</option>
                    </select>
                  ) : <Badge variant="outline" className={`text-[10px] ${STATUS_TONE[r.status]}`}>{r.status}</Badge>}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {r.is_delayed && <Badge className="bg-red-600 text-white text-[10px] mr-1" data-testid={`premob-delayed-${r.id}`}>DELAYED</Badge>}
                  {r.concern && (
                    <Badge variant="outline" className="bg-orange-50 text-orange-900 border-orange-300 text-[10px]" title={r.concern.note} data-testid={`premob-concern-${r.id}`}>
                      {r.concern.type_label}{r.concern.proposed_date ? ` → ${r.concern.proposed_date}` : ""}
                    </Badge>
                  )}
                  {!r.is_delayed && !r.concern && r.status === "completed" && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                </TableCell>
                {canWrite && (
                  <TableCell className="text-right whitespace-nowrap">
                    {r.concern
                      ? <Button variant="outline" size="sm" className="h-7 text-xs mr-1" onClick={() => resolveConcern(r)} data-testid={`premob-resolve-${r.id}`}>Resolve</Button>
                      : <Button variant="outline" size="sm" className="h-7 text-xs mr-1 text-orange-700 border-orange-300" onClick={() => { setConcernFor(r); setConcern({ type: "needs_extension", note: "", proposed_date: "" }); }} data-testid={`premob-raise-${r.id}`}>
                          <AlertTriangle className="h-3 w-3 mr-1" /> Concern
                        </Button>}
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(r)} data-testid={`premob-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-red-600" onClick={() => remove(r)} data-testid={`premob-delete-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">No items planned yet. Click "Add Item" to start.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* Add / Edit dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editId ? "Edit Item" : "Add Pre-Mobilization Item"}</DialogTitle>
            <DialogDescription>Material or manpower to arrange before mobilization, with a target date.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <ProjectSelect label="Project *" value={form.project_code || projects.find((p) => p.id === form.project_id)?.code || ""}
                onChange={(code, row) => setForm((f) => ({ ...f, project_code: code, project_id: row?.id || "" }))} testid="premob-form-project" />
            </div>
            <Sel label="Type *" value={form.item_type} onChange={(v) => setForm((f) => ({ ...f, item_type: v }))} testid="premob-form-type">
              {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Sel>
            <div>
              <Label className="text-xs">Target Date *</Label>
              <Input type="date" className="h-9 mt-1" value={form.target_date} onChange={(e) => setForm((f) => ({ ...f, target_date: e.target.value }))} data-testid="premob-form-target" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs">Item / Resource Name *</Label>
              <Input className="h-9 mt-1" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder={form.item_type === "manpower" ? "e.g., Scaffolders — Level 2" : "e.g., MS Scaffolding Pipes 6m"} data-testid="premob-form-name" />
            </div>
            <div>
              <Label className="text-xs">Qty</Label>
              <Input type="number" min="0" className="h-9 mt-1" value={form.qty} onChange={(e) => setForm((f) => ({ ...f, qty: e.target.value }))} data-testid="premob-form-qty" />
            </div>
            <div>
              <Label className="text-xs">Unit</Label>
              <Input className="h-9 mt-1" value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))} placeholder={form.item_type === "manpower" ? "persons" : "Nos"} data-testid="premob-form-unit" />
            </div>
            <div className="col-span-2">
              <Label className="text-xs">Remarks</Label>
              <Textarea rows={2} value={form.remarks} onChange={(e) => setForm((f) => ({ ...f, remarks: e.target.value }))} data-testid="premob-form-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} disabled={saving} data-testid="premob-form-save">{saving ? "Saving…" : editId ? "Update" : "Add Item"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Concern dialog */}
      <Dialog open={!!concernFor} onOpenChange={(v) => !v && setConcernFor(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-orange-600" /> Raise Concern</DialogTitle>
            <DialogDescription>{concernFor?.name} · target {concernFor?.target_date}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              {CONCERNS.map((c) => (
                <label key={c.value} className={`flex items-center gap-2 border rounded-sm px-3 py-2 text-sm cursor-pointer ${concern.type === c.value ? "border-orange-400 bg-orange-50" : ""}`}>
                  <input type="radio" name="concern-type" checked={concern.type === c.value} onChange={() => setConcern((x) => ({ ...x, type: c.value }))} data-testid={`concern-type-${c.value}`} />
                  {c.label}
                </label>
              ))}
            </div>
            {concern.type === "needs_extension" && (
              <div>
                <Label className="text-xs">Proposed New Target Date *</Label>
                <Input type="date" className="h-9 mt-1" value={concern.proposed_date} onChange={(e) => setConcern((x) => ({ ...x, proposed_date: e.target.value }))} data-testid="concern-proposed-date" />
              </div>
            )}
            <div>
              <Label className="text-xs">Note {concern.type === "other" ? "*" : "(optional)"}</Label>
              <Textarea rows={2} value={concern.note} onChange={(e) => setConcern((x) => ({ ...x, note: e.target.value }))} placeholder="What is the problem?" data-testid="concern-note" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConcernFor(null)}>Cancel</Button>
            <Button className="bg-orange-600 hover:bg-orange-700" onClick={raiseConcern} data-testid="concern-submit">Raise Concern</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
