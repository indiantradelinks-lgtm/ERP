/**
 * Work Permit Register · P&O Phase 3 (Round 3C)
 * Backend: /api/proj-phase3/permits
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ShieldAlert, Plus, Pencil, Trash2, RefreshCcw, AlertTriangle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const TYPES = ["hot_work", "confined_space", "height", "electrical", "excavation", "lifting", "general"];
const CLEARANCE = ["pending", "cleared", "rejected"];
const STATUSES = ["active", "expired", "revoked", "pending_clearance"];
const EMPTY = { project_id: "", permit_no: "", permit_type: "general", permit_date: new Date().toISOString().slice(0, 10), valid_from: "", valid_to: "", issued_by: "", activity_covered: "", safety_clearance_status: "pending", attachment_ids: [], remarks: "" };

export default function WorkPermits() {
  const [projects, setProjects] = useState([]);
  const [rows, setRows] = useState([]);
  const [filt, setFilt] = useState({ project_id: "", status: "" });
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filt]);

  const load = async () => {
    try { const { data } = await api.get("/proj-phase3/permits", { params: { project_id: filt.project_id || undefined, status: filt.status || undefined } }); setRows(data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const save = async () => {
    if (!form.project_id) return toast.error("Project required");
    try {
      if (editing?.id) await api.put(`/proj-phase3/permits/${editing.id}`, form);
      else await api.post(`/proj-phase3/permits`, form);
      toast.success("Saved"); setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.permit_no}?`)) return;
    try { await api.delete(`/proj-phase3/permits/${r.id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const expiring = rows.filter((r) => r.status === "active" && r.valid_to && new Date(r.valid_to) <= new Date(Date.now() + 7 * 24 * 3600 * 1000));
  const expired = rows.filter((r) => r.status === "expired");

  return (
    <div className="p-6 space-y-4" data-testid="page-work-permits">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldAlert className="h-6 w-6 text-amber-600" /> Work Permits</h1>
          <p className="text-sm text-muted-foreground">Permits / site clearances. Expired and expiring-within-7-days permits are highlighted.</p>
        </div>
        {canEdit && <Button onClick={() => { setEditing({}); setForm({ ...EMPTY, project_id: filt.project_id || "" }); }} data-testid="wp-perm-new"><Plus className="h-4 w-4 mr-1" /> New Permit</Button>}
      </div>

      {(expiring.length > 0 || expired.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {expired.length > 0 && <Alert tone="bg-rose-50 border-rose-200 text-rose-700" icon><strong>{expired.length} permit(s) EXPIRED</strong> — operations on those activities must stop until renewed.</Alert>}
          {expiring.length > 0 && <Alert tone="bg-amber-50 border-amber-200 text-amber-700" icon><strong>{expiring.length} permit(s) expiring within 7 days</strong>.</Alert>}
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Permits <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <select value={filt.project_id} onChange={(e) => setFilt({ ...filt, project_id: e.target.value })} className="h-7 rounded-sm border px-2"><option value="">All projects</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}</select>
            <select value={filt.status} onChange={(e) => setFilt({ ...filt, status: e.target.value })} className="h-7 rounded-sm border px-2"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">Permit #</th><th className="px-2 py-2">Type</th><th className="px-2 py-2">Project</th>
                <th className="px-2 py-2">Activity</th><th className="px-2 py-2">Valid From</th><th className="px-2 py-2">Valid To</th>
                <th className="px-2 py-2">Issued By</th><th className="px-2 py-2 text-center">Clearance</th><th className="px-2 py-2 text-center">Status</th>
                <th className="px-2 py-2 text-right w-20"></th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-slate-400">No permits</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b" data-testid={`wp-perm-row-${r.id}`}>
                    <td className="px-2 py-1 font-mono font-bold text-primary">{r.permit_no}</td>
                    <td className="px-2 py-1 text-xs">{r.permit_type}</td>
                    <td className="px-2 py-1 text-xs">{r.project_code}</td>
                    <td className="px-2 py-1 truncate max-w-[200px]">{r.activity_covered || "—"}</td>
                    <td className="px-2 py-1 text-xs">{r.valid_from || "—"}</td>
                    <td className="px-2 py-1 text-xs">{r.valid_to || "—"}</td>
                    <td className="px-2 py-1 text-xs">{r.issued_by || "—"}</td>
                    <td className="px-2 py-1 text-center text-xs">{r.safety_clearance_status}</td>
                    <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${tone(r.status)}`}>{r.status}</span></td>
                    <td className="px-2 py-1 text-right">
                      {canEdit && <div className="flex justify-end gap-1">
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`wp-perm-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`wp-perm-del-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                      </div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Work Permit</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project *">
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} disabled={!!editing?.id} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="wp-perm-form-project"><option value="">— select —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select>
            </F>
            <F label="Permit #"><Input value={form.permit_no} onChange={(e) => setForm({ ...form, permit_no: e.target.value })} placeholder="auto" /></F>
            <F label="Type">
              <select value={form.permit_type} onChange={(e) => setForm({ ...form, permit_type: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="wp-perm-form-type">{TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select>
            </F>
            <F label="Permit Date"><Input type="date" value={form.permit_date} onChange={(e) => setForm({ ...form, permit_date: e.target.value })} /></F>
            <F label="Valid From"><Input type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} data-testid="wp-perm-form-from" /></F>
            <F label="Valid To"><Input type="date" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} data-testid="wp-perm-form-to" /></F>
            <F label="Issued By"><Input value={form.issued_by} onChange={(e) => setForm({ ...form, issued_by: e.target.value })} placeholder="Client / site rep" /></F>
            <F label="Safety Clearance">
              <select value={form.safety_clearance_status} onChange={(e) => setForm({ ...form, safety_clearance_status: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm">{CLEARANCE.map((c) => <option key={c} value={c}>{c}</option>)}</select>
            </F>
            <F label="Activity Covered" full><Textarea rows={2} value={form.activity_covered} onChange={(e) => setForm({ ...form, activity_covered: e.target.value })} /></F>
            <F label="Remarks" full><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="wp-perm-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const TONES = { active: "bg-emerald-50 text-emerald-700 border-emerald-200", expired: "bg-rose-50 text-rose-700 border-rose-200", revoked: "bg-slate-50 text-slate-600 border-slate-200", pending_clearance: "bg-amber-50 text-amber-700 border-amber-200" };
function tone(s) { return TONES[s] || TONES.active; }
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
function Alert({ tone, icon, children }) { return <div className={`border rounded-sm p-3 text-sm flex items-start gap-2 ${tone}`}>{icon && <AlertTriangle className="h-4 w-4 mt-0.5" />}{children}</div>; }
