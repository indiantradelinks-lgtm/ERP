/**
 * Project BOQ · P&O Phase 2 (Round 1)
 *
 * Bill of Quantities (BOQ) / Scope Breakdown — per project.
 * Two screens in one page:
 *   • List of BOQs (header) for filterable project
 *   • Drill-down editor with inline lines, Excel import/export.
 *
 * Backend: /api/proj-phase2/boqs ...
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { FileSpreadsheet, Plus, Pencil, Trash2, RefreshCcw, Upload, Download, CheckCircle2, ArrowLeft, FileDown } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const STATUSES = ["draft", "in_review", "approved", "revised", "cancelled"];
const UOMS = ["nos", "sqm", "cum", "lm", "MT", "kg", "manday", "LS"];
const SCOPE_TYPES = ["service", "supply", "material", "labour"];

const EMPTY_HEADER = {
  project_id: "", boq_no: "", boq_date: new Date().toISOString().slice(0, 10),
  title: "", description: "", currency: "INR", version: "1.0",
  tax_rate: 18, status: "draft", remarks: "",
};
const EMPTY_LINE = {
  sl_no: "", item_code: "", description: "", category: "",
  scope_type: "service", uom: "nos", quantity: 0, unit_rate: 0,
  wbs_code: "", remarks: "",
};

export default function ProjectBOQ() {
  const [projects, setProjects]   = useState([]);
  const [rows, setRows]           = useState([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [statusFilter, setStatusFilter]   = useState("");
  const [headerEditing, setHeaderEditing] = useState(null);     // {} for new, row for edit
  const [hForm, setHForm]                 = useState(EMPTY_HEADER);
  const [selected, setSelected]           = useState(null);     // BOQ id of detail view
  const [detail, setDetail]               = useState(null);     // {boq, lines}
  const [lineEditing, setLineEditing]     = useState(null);
  const [lForm, setLForm]                 = useState(EMPTY_LINE);
  const fileInputRef = useRef(null);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/proj-phase2/boqs", { params: { project_id: projectFilter || undefined, status: statusFilter || undefined } }),
        api.get("/projects"),
      ]);
      setRows(a.data || []);
      setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [projectFilter, statusFilter]);

  const loadDetail = async (id) => {
    try {
      const { data } = await api.get(`/proj-phase2/boqs/${id}`);
      setDetail(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load BOQ detail"); }
  };
  useEffect(() => { if (selected) loadDetail(selected); else setDetail(null); }, [selected]);

  const projectsById = useMemo(() => Object.fromEntries(projects.map(p => [p.id, p])), [projects]);

  const saveHeader = async () => {
    if (!hForm.project_id) { toast.error("Project is required"); return; }
    if (!hForm.title?.trim()) { toast.error("Title is required"); return; }
    try {
      const payload = { ...hForm, tax_rate: Number(hForm.tax_rate) || 0 };
      if (headerEditing?.id) {
        await api.put(`/proj-phase2/boqs/${headerEditing.id}`, payload);
        toast.success("BOQ updated");
      } else {
        const { data } = await api.post(`/proj-phase2/boqs`, payload);
        toast.success(`BOQ created · ${data.boq_no}`);
      }
      setHeaderEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const removeHeader = async (r) => {
    if (!window.confirm(`Delete BOQ ${r.boq_no}? All lines will be removed.`)) return;
    try {
      await api.delete(`/proj-phase2/boqs/${r.id}`);
      toast.success("BOQ deleted"); load();
      if (selected === r.id) setSelected(null);
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const approveHeader = async (r) => {
    if (!window.confirm(`Approve BOQ ${r.boq_no}? It will be locked.`)) return;
    try {
      await api.post(`/proj-phase2/boqs/${r.id}/approve`);
      toast.success("BOQ approved"); load();
      if (selected === r.id) loadDetail(r.id);
    } catch (e) { toast.error(e.response?.data?.detail || "Approval failed"); }
  };

  const saveLine = async () => {
    if (!lForm.description?.trim()) { toast.error("Description is required"); return; }
    try {
      const payload = {
        ...lForm,
        sl_no: lForm.sl_no === "" ? null : Number(lForm.sl_no),
        quantity: Number(lForm.quantity) || 0,
        unit_rate: Number(lForm.unit_rate) || 0,
      };
      if (lineEditing?.id) {
        await api.put(`/proj-phase2/boqs/${selected}/lines/${lineEditing.id}`, payload);
        toast.success("Line updated");
      } else {
        await api.post(`/proj-phase2/boqs/${selected}/lines`, payload);
        toast.success("Line added");
      }
      setLineEditing(null); loadDetail(selected); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const removeLine = async (l) => {
    if (!window.confirm("Delete this line?")) return;
    try {
      await api.delete(`/proj-phase2/boqs/${selected}/lines/${l.id}`);
      toast.success("Line deleted"); loadDetail(selected); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  // ── Excel handlers ──
  const downloadTemplate = () => {
    const url = `${API}/proj-phase2/boqs/template`;
    window.open(url, "_blank");
  };
  const downloadExport = () => {
    if (!selected) return;
    const url = `${API}/proj-phase2/boqs/${selected}/export`;
    window.open(url, "_blank");
  };
  const onImportFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !selected) return;
    const replace = window.confirm("Replace ALL existing lines with the imported file?\nClick 'Cancel' to APPEND instead.");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post(
        `/proj-phase2/boqs/${selected}/import?replace=${replace ? "true" : "false"}`,
        fd, { headers: { "Content-Type": "multipart/form-data" } }
      );
      toast.success(`Imported ${data.inserted} lines${data.errors?.length ? ` (${data.errors.length} skipped)` : ""}`);
      if (data.errors?.length) console.warn("BOQ import errors:", data.errors);
      loadDetail(selected); load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    }
  };

  // ── views ──
  if (selected && detail) return (
    <BoqDetailView
      boq={detail}
      lines={detail.lines || []}
      onBack={() => setSelected(null)}
      canEdit={canEdit}
      onNewLine={() => { setLineEditing({}); setLForm(EMPTY_LINE); }}
      onEditLine={(l) => { setLineEditing(l); setLForm({ ...EMPTY_LINE, ...l }); }}
      onDeleteLine={removeLine}
      onApprove={() => approveHeader(detail)}
      onDownloadTemplate={downloadTemplate}
      onDownloadExport={downloadExport}
      onImportClick={() => fileInputRef.current?.click()}
      fileInputRef={fileInputRef}
      onImportFile={onImportFile}
      lineEditing={lineEditing}
      lForm={lForm}
      setLForm={setLForm}
      saveLine={saveLine}
      onCloseLineDialog={() => setLineEditing(null)}
    />
  );

  return (
    <div className="p-6 space-y-4" data-testid="page-project-boq">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileSpreadsheet className="h-6 w-6 text-primary" /> BOQ / Scope Breakdown
          </h1>
          <p className="text-sm text-muted-foreground">Bill of Quantities for projects. Header + line items with UOM, qty, rate, amount. Excel I/O.</p>
        </div>
        {canEdit && (
          <Button onClick={() => { setHeaderEditing({}); setHForm({ ...EMPTY_HEADER, project_id: projectFilter || "" }); }} data-testid="boq-new">
            <Plus className="h-4 w-4 mr-1" /> New BOQ
          </Button>
        )}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">All BOQs <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="boq-filter-project">
              <option value="">All projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="boq-filter-status">
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">BOQ #</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Title</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2 text-right">Lines</th>
                  <th className="px-3 py-2 text-right">Subtotal</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-8 text-slate-400">No BOQs created yet</td></tr>
                )}
                {rows.map((r) => {
                  const p = projectsById[r.project_id];
                  return (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50 cursor-pointer" onClick={() => setSelected(r.id)} data-testid={`boq-row-${r.id}`}>
                      <td className="px-3 py-2 font-mono font-bold text-primary">{r.boq_no}</td>
                      <td className="px-3 py-2">{p ? <span><span className="font-mono text-xs">{p.code}</span> · {p.name}</span> : r.project_code || "—"}</td>
                      <td className="px-3 py-2">{r.title}</td>
                      <td className="px-3 py-2 text-xs">{r.boq_date || "—"}</td>
                      <td className="px-3 py-2 text-right">{r.line_count || 0}</td>
                      <td className="px-3 py-2 text-right font-mono">{Number(r.subtotal || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-right font-mono font-semibold">{Number(r.total || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(r.status)}`}>{r.status}</span>
                      </td>
                      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        {canEdit && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setHeaderEditing(r); setHForm({ ...EMPTY_HEADER, ...r }); }} data-testid={`boq-edit-${r.id}`}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeHeader(r)} data-testid={`boq-del-${r.id}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Header Dialog */}
      <Dialog open={headerEditing !== null} onOpenChange={(o) => !o && setHeaderEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{headerEditing?.id ? "Edit" : "New"} BOQ</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project *">
              <select value={hForm.project_id} onChange={(e) => setHForm({ ...hForm, project_id: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" disabled={!!headerEditing?.id} data-testid="boq-form-project">
                <option value="">— select —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </F>
            <F label="BOQ #"><Input value={hForm.boq_no} onChange={(e) => setHForm({ ...hForm, boq_no: e.target.value })} placeholder="auto" /></F>
            <F label="Title *" full><Input value={hForm.title} onChange={(e) => setHForm({ ...hForm, title: e.target.value })} data-testid="boq-form-title" /></F>
            <F label="BOQ Date"><Input type="date" value={hForm.boq_date || ""} onChange={(e) => setHForm({ ...hForm, boq_date: e.target.value })} /></F>
            <F label="Version"><Input value={hForm.version} onChange={(e) => setHForm({ ...hForm, version: e.target.value })} placeholder="1.0" /></F>
            <F label="Currency"><Input value={hForm.currency} onChange={(e) => setHForm({ ...hForm, currency: e.target.value })} /></F>
            <F label="Tax Rate (%)"><Input type="number" value={hForm.tax_rate} onChange={(e) => setHForm({ ...hForm, tax_rate: e.target.value })} /></F>
            <F label="Status">
              <select value={hForm.status} onChange={(e) => setHForm({ ...hForm, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="Description" full><Textarea rows={2} value={hForm.description || ""} onChange={(e) => setHForm({ ...hForm, description: e.target.value })} /></F>
            <F label="Remarks" full><Textarea rows={2} value={hForm.remarks || ""} onChange={(e) => setHForm({ ...hForm, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHeaderEditing(null)}>Cancel</Button>
            <Button onClick={saveHeader} data-testid="boq-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─────────────────────── BOQ Detail View (lines + Excel) ───────────────────────
function BoqDetailView({
  boq, lines, onBack, canEdit, onNewLine, onEditLine, onDeleteLine,
  onApprove, onDownloadTemplate, onDownloadExport, onImportClick,
  fileInputRef, onImportFile,
  lineEditing, lForm, setLForm, saveLine, onCloseLineDialog,
}) {
  const isApproved = boq.status === "approved";
  return (
    <div className="p-6 space-y-4" data-testid="page-boq-detail">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={onBack} className="text-sm text-primary inline-flex items-center mb-1" data-testid="boq-back">
            <ArrowLeft className="h-3.5 w-3.5 mr-1" /> Back to BOQ List
          </button>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileSpreadsheet className="h-6 w-6 text-primary" /> {boq.boq_no}
            <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusTone(boq.status)}`}>{boq.status}</span>
          </h1>
          <p className="text-sm text-muted-foreground">
            {boq.project_code} · {boq.project_name} — {boq.title} (v{boq.version})
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <Button size="sm" variant="outline" onClick={onDownloadTemplate} data-testid="boq-template-dl">
            <FileDown className="h-3.5 w-3.5 mr-1" /> Template
          </Button>
          <Button size="sm" variant="outline" onClick={onDownloadExport} data-testid="boq-export">
            <Download className="h-3.5 w-3.5 mr-1" /> Export
          </Button>
          {canEdit && !isApproved && (
            <>
              <Button size="sm" variant="outline" onClick={onImportClick} data-testid="boq-import">
                <Upload className="h-3.5 w-3.5 mr-1" /> Import
              </Button>
              <input ref={fileInputRef} type="file" accept=".xlsx,.xls" hidden onChange={onImportFile} />
              <Button size="sm" onClick={onNewLine} data-testid="boq-line-new">
                <Plus className="h-3.5 w-3.5 mr-1" /> Add Line
              </Button>
            </>
          )}
          {canEdit && !isApproved && (
            <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={onApprove} data-testid="boq-approve">
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve BOQ
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Lines" value={boq.line_count || lines.length} />
        <Stat label="Subtotal" value={`${boq.currency} ${Number(boq.subtotal || 0).toLocaleString("en-IN")}`} />
        <Stat label={`Tax @ ${boq.tax_rate}%`} value={`${boq.currency} ${Number(boq.tax_amount || 0).toLocaleString("en-IN")}`} />
        <Stat label="Total" value={`${boq.currency} ${Number(boq.total || 0).toLocaleString("en-IN")}`} highlight />
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Line Items</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2 w-12 text-right">Sl</th>
                  <th className="px-2 py-2">Item Code</th>
                  <th className="px-2 py-2">Description</th>
                  <th className="px-2 py-2">Category</th>
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">UOM</th>
                  <th className="px-2 py-2 text-right">Qty</th>
                  <th className="px-2 py-2 text-right">Rate</th>
                  <th className="px-2 py-2 text-right">Amount</th>
                  <th className="px-2 py-2">WBS</th>
                  <th className="px-2 py-2 text-right w-20"></th>
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 && <tr><td colSpan={11} className="text-center py-6 text-slate-400">No lines yet — add the first line or import from Excel.</td></tr>}
                {lines.map((l) => (
                  <tr key={l.id} className="border-b hover:bg-slate-50/50" data-testid={`boq-line-${l.id}`}>
                    <td className="px-2 py-1 text-right font-mono">{l.sl_no}</td>
                    <td className="px-2 py-1 text-xs font-mono">{l.item_code || "—"}</td>
                    <td className="px-2 py-1">{l.description}</td>
                    <td className="px-2 py-1 text-xs">{l.category || "—"}</td>
                    <td className="px-2 py-1 text-xs">{l.scope_type || "—"}</td>
                    <td className="px-2 py-1 text-xs">{l.uom}</td>
                    <td className="px-2 py-1 text-right font-mono">{Number(l.quantity || 0).toLocaleString("en-IN")}</td>
                    <td className="px-2 py-1 text-right font-mono">{Number(l.unit_rate || 0).toLocaleString("en-IN")}</td>
                    <td className="px-2 py-1 text-right font-mono font-semibold">{Number(l.amount || 0).toLocaleString("en-IN")}</td>
                    <td className="px-2 py-1 text-xs">{l.wbs_code || "—"}</td>
                    <td className="px-2 py-1 text-right">
                      {canEdit && !isApproved && (
                        <div className="flex justify-end gap-1">
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onEditLine(l)} data-testid={`boq-line-edit-${l.id}`}><Pencil className="h-3.5 w-3.5"/></Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => onDeleteLine(l)} data-testid={`boq-line-del-${l.id}`}><Trash2 className="h-3.5 w-3.5"/></Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={lineEditing !== null} onOpenChange={(o) => !o && onCloseLineDialog()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{lineEditing?.id ? "Edit" : "Add"} BOQ Line</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Sl No"><Input type="number" value={lForm.sl_no} onChange={(e) => setLForm({ ...lForm, sl_no: e.target.value })} placeholder="auto" /></F>
            <F label="Item Code"><Input value={lForm.item_code} onChange={(e) => setLForm({ ...lForm, item_code: e.target.value })} /></F>
            <F label="Description *" full><Textarea rows={2} value={lForm.description} onChange={(e) => setLForm({ ...lForm, description: e.target.value })} data-testid="boq-line-desc" /></F>
            <F label="Category"><Input value={lForm.category} onChange={(e) => setLForm({ ...lForm, category: e.target.value })} placeholder="Civil / MEP / Painting / Scaffolding" /></F>
            <F label="Scope Type">
              <select value={lForm.scope_type} onChange={(e) => setLForm({ ...lForm, scope_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {SCOPE_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="UOM">
              <select value={lForm.uom} onChange={(e) => setLForm({ ...lForm, uom: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </F>
            <F label="Quantity"><Input type="number" step="0.01" value={lForm.quantity} onChange={(e) => setLForm({ ...lForm, quantity: e.target.value })} data-testid="boq-line-qty" /></F>
            <F label="Unit Rate"><Input type="number" step="0.01" value={lForm.unit_rate} onChange={(e) => setLForm({ ...lForm, unit_rate: e.target.value })} data-testid="boq-line-rate" /></F>
            <F label="WBS Code"><Input value={lForm.wbs_code} onChange={(e) => setLForm({ ...lForm, wbs_code: e.target.value })} placeholder="WBS-1.1 (optional, set in Round 2)" /></F>
            <F label="Amount (auto)" >
              <div className="h-9 px-3 flex items-center text-sm font-mono font-bold text-primary border rounded-sm bg-slate-50">
                ₹ {(Number(lForm.quantity || 0) * Number(lForm.unit_rate || 0)).toFixed(2)}
              </div>
            </F>
            <F label="Remarks" full><Textarea rows={2} value={lForm.remarks} onChange={(e) => setLForm({ ...lForm, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onCloseLineDialog}>Cancel</Button>
            <Button onClick={saveLine} data-testid="boq-line-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const TONES = {
  draft: "bg-slate-50 text-slate-600 border-slate-200",
  in_review: "bg-blue-50 text-blue-700 border-blue-200",
  approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  revised: "bg-amber-50 text-amber-700 border-amber-200",
  cancelled: "bg-rose-50 text-rose-700 border-rose-200",
};
function statusTone(s) { return TONES[s] || "bg-slate-50 text-slate-600 border-slate-200"; }

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
function Stat({ label, value, highlight }) {
  return (
    <div className={`border rounded-sm p-3 ${highlight ? "bg-primary/5 border-primary/30" : "bg-card"}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`text-xl font-bold truncate ${highlight ? "text-primary" : ""}`}>{value}</div>
    </div>
  );
}
