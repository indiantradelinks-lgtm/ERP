/**
 * Client Instructions · P&O Phase 3 (Round 3B)
 * Backend: /api/proj-phase3/client-instructions
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
import { MessageSquare, Plus, Pencil, Trash2, RefreshCcw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const MODES = ["verbal", "written"];
const STATUSES = ["open", "in_progress", "actioned", "closed"];
const EMPTY = { project_id: "", instruction_date: new Date().toISOString().slice(0, 10), given_by: "", mode: "verbal", instruction_details: "", action_required: "", responsible_person: "", target_date: "", status: "open", attachment_ids: [] };

export default function ClientInstructions() {
  const [projects, setProjects] = useState([]);
  const [rows, setRows] = useState([]);
  const [filt, setFilt] = useState({ project_id: "", status: "" });
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filt]);
  const load = async () => {
    try { const { data } = await api.get("/proj-phase3/client-instructions", { params: { project_id: filt.project_id || undefined, status: filt.status || undefined } }); setRows(data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const save = async () => {
    if (!form.project_id) return toast.error("Project required");
    if (!form.instruction_details?.trim()) return toast.error("Instruction details required");
    try {
      if (editing?.id) await api.put(`/proj-phase3/client-instructions/${editing.id}`, form);
      else await api.post(`/proj-phase3/client-instructions`, form);
      toast.success("Saved"); setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.instruction_no}?`)) return;
    try { await api.delete(`/proj-phase3/client-instructions/${r.id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-client-instructions">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><MessageSquare className="h-6 w-6 text-primary" /> Client Instructions</h1>
          <p className="text-sm text-muted-foreground">Verbal &amp; written instructions from client with action / responsible / status.</p>
        </div>
        {canEdit && <Button onClick={() => { setEditing({}); setForm({ ...EMPTY, project_id: filt.project_id || "" }); }} data-testid="ci-new"><Plus className="h-4 w-4 mr-1" /> New Instruction</Button>}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Instructions <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
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
                <th className="px-2 py-2">CI #</th><th className="px-2 py-2">Date</th><th className="px-2 py-2">Project</th><th className="px-2 py-2">Mode</th>
                <th className="px-2 py-2">Given By</th><th className="px-2 py-2">Details</th><th className="px-2 py-2">Responsible</th>
                <th className="px-2 py-2">Target</th><th className="px-2 py-2 text-center">Status</th><th className="px-2 py-2 text-right w-20"></th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={10} className="text-center py-6 text-slate-400">No instructions</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b" data-testid={`ci-row-${r.id}`}>
                    <td className="px-2 py-1 font-mono font-bold text-primary">{r.instruction_no}</td>
                    <td className="px-2 py-1 text-xs">{r.instruction_date}</td>
                    <td className="px-2 py-1 text-xs">{r.project_code}</td>
                    <td className="px-2 py-1 text-xs">{r.mode}</td>
                    <td className="px-2 py-1 text-xs">{r.given_by || "—"}</td>
                    <td className="px-2 py-1 truncate max-w-[320px]">{r.instruction_details}</td>
                    <td className="px-2 py-1 text-xs">{r.responsible_person || "—"}</td>
                    <td className="px-2 py-1 text-xs">{r.target_date || "—"}</td>
                    <td className="px-2 py-1 text-center"><span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border bg-slate-50">{r.status}</span></td>
                    <td className="px-2 py-1 text-right">
                      {canEdit && <div className="flex justify-end gap-1">
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`ci-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`ci-del-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
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
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Client Instruction</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project *">
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} disabled={!!editing?.id} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="ci-form-project">
                <option value="">— select —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </select>
            </F>
            <F label="Date"><Input type="date" value={form.instruction_date} onChange={(e) => setForm({ ...form, instruction_date: e.target.value })} /></F>
            <F label="Given By"><Input value={form.given_by} onChange={(e) => setForm({ ...form, given_by: e.target.value })} placeholder="Client rep name" /></F>
            <F label="Mode">
              <select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm">{MODES.map((m) => <option key={m} value={m}>{m}</option>)}</select>
            </F>
            <F label="Instruction Details *" full><Textarea rows={3} value={form.instruction_details} onChange={(e) => setForm({ ...form, instruction_details: e.target.value })} data-testid="ci-form-details" /></F>
            <F label="Action Required" full><Textarea rows={2} value={form.action_required} onChange={(e) => setForm({ ...form, action_required: e.target.value })} /></F>
            <F label="Responsible"><Input value={form.responsible_person} onChange={(e) => setForm({ ...form, responsible_person: e.target.value })} /></F>
            <F label="Target Date"><Input type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></F>
            <F label="Status">
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm">{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
            </F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="ci-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
