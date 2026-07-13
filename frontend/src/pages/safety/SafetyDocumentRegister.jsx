/**
 * Safety Document Register — safety licenses, certificates, statutory
 * approvals with expiry tracking. Every doc gets a computed expiry_status
 * badge (valid / expiring_soon / expired) client-side from the value the
 * backend already returns.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { FileText, Plus, Pencil, RefreshCcw, Trash2, Filter } from "lucide-react";

const DOC_TYPES = ["license", "certificate", "insurance", "statutory", "policy", "plan", "other"];
const EXPIRY_STATUSES = ["", "valid", "expiring_soon", "expired", "no_expiry"];
const EXPIRY_TONE = {
  valid: "bg-emerald-50 text-emerald-700 border-emerald-300",
  expiring_soon: "bg-amber-50 text-amber-800 border-amber-300",
  expired: "bg-red-50 text-red-700 border-red-300",
  no_expiry: "bg-slate-50 text-slate-500 border-slate-200",
};
const EMPTY = {
  title: "", doc_type: "license", reference_no: "", issued_by: "", issued_on: "",
  expires_on: "", project_id: "", project_code: "", remarks: "", file_ids: [],
};

export default function SafetyDocumentRegister() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get(`/safety/documents${statusFilter ? `?status=${statusFilter}` : ""}${typeFilter ? `${statusFilter ? "&" : "?"}doc_type=${typeFilter}` : ""}`),
        api.get("/projects"),
      ]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [statusFilter, typeFilter]);

  const summary = useMemo(() => {
    const s = { total: rows.length, valid: 0, expiring_soon: 0, expired: 0, no_expiry: 0 };
    rows.forEach((r) => { s[r.expiry_status] = (s[r.expiry_status] || 0) + 1; });
    return s;
  }, [rows]);

  const save = async () => {
    if (!form.title?.trim()) { toast.error("Title required"); return; }
    if (!form.doc_type) { toast.error("Doc type required"); return; }
    try {
      if (editing?.id) { await api.put(`/safety/documents/${editing.id}`, form); toast.success("Updated"); }
      else { await api.post(`/safety/documents`, form); toast.success("Created"); }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try { await api.delete(`/safety/documents/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="safety-docs-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <FileText className="h-6 w-6 text-blue-600" /> Safety Document Register
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">Licenses · Certificates · Insurance · Statutory approvals — with expiry alerts.</p>
        </div>
        <div className="flex gap-2 items-center">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="h-8 rounded-sm border border-input bg-background text-xs px-2">
            <option value="">All types</option>{DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-8 rounded-sm border border-input bg-background text-xs px-2">
            {EXPIRY_STATUSES.map((s) => <option key={s} value={s}>{s || "all statuses"}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="doc-new">
            <Plus className="h-4 w-4 mr-1" /> New Document
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Total" value={summary.total} />
        <Stat label="Valid" value={summary.valid} tone="emerald" />
        <Stat label="Expiring ≤ 30d" value={summary.expiring_soon} tone="amber" />
        <Stat label="Expired" value={summary.expired} tone="red" />
        <Stat label="No expiry" value={summary.no_expiry} tone="slate" />
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Title</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Ref #</th>
              <th className="text-left px-3 py-2">Issued</th>
              <th className="text-left px-3 py-2">Expires</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No documents.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`doc-row-${r.id}`}>
                <td className="px-3 py-2 font-medium">{r.title}</td>
                <td className="px-3 py-2 text-xs uppercase tracking-wider">{r.doc_type}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.reference_no || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.issued_on || "—"}</td>
                <td className="px-3 py-2 text-xs">{r.expires_on || "—"}</td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border ${EXPIRY_TONE[r.expiry_status] || "bg-slate-50"}`}>
                    {(r.expiry_status || "").replaceAll("_", " ")}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit Document" : "New Document"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Title *</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="doc-form-title" /></div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Type *</Label>
              <select value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Reference #</Label><Input value={form.reference_no || ""} onChange={(e) => setForm({ ...form, reference_no: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Issued By</Label><Input value={form.issued_by || ""} onChange={(e) => setForm({ ...form, issued_by: e.target.value })} /></div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Project</Label>
              <select value={form.project_id || ""} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                <option value="">— none —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Issued On</Label><Input type="date" value={form.issued_on || ""} onChange={(e) => setForm({ ...form, issued_on: e.target.value })} /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Expires On</Label><Input type="date" value={form.expires_on || ""} onChange={(e) => setForm({ ...form, expires_on: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="doc-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const tint = tone === "red" ? "text-red-700" : tone === "amber" ? "text-amber-700" : tone === "emerald" ? "text-emerald-700" : "text-foreground";
  return (
    <div className="border rounded-sm p-3 bg-card">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-display font-black text-2xl tabular mt-0.5 ${tint}`}>{value}</div>
    </div>
  );
}
