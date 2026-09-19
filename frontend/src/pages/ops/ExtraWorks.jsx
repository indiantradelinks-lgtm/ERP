/**
 * Extra Work Register · P&O Phase 3 (Round 3B)
 * Backend: /api/proj-phase3/extra-works
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
import { PlusSquare, Plus, Pencil, Trash2, RefreshCcw, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const APPROVAL = ["pending", "approved", "rejected"];
const CLIENT_APPROVAL = ["pending", "written", "verbal", "rejected"];
const EMPTY = { project_id: "", client_instruction_id: "", work_description: "", quantity: 0, uom: "", rate: 0, estimated_value: null, client_approval_status: "pending", attachment_ids: [], remarks: "" };

export default function ExtraWorks() {
  const [projects, setProjects] = useState([]);
  const [instructions, setInstructions] = useState([]);
  const [rows, setRows] = useState([]);
  const [filt, setFilt] = useState({ project_id: "", approval_status: "" });
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const { user } = useAuth() || {};
  const canApprove = ["super_admin", "director", "general_manager", "dept_head", "project_manager"].includes(user?.role);
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filt]);
  useEffect(() => {
    if (filt.project_id) api.get("/proj-phase3/client-instructions", { params: { project_id: filt.project_id } }).then((r) => setInstructions(r.data || [])).catch(() => {});
    else setInstructions([]);
  }, [filt.project_id]);

  const load = async () => {
    try { const { data } = await api.get("/proj-phase3/extra-works", { params: { project_id: filt.project_id || undefined, approval_status: filt.approval_status || undefined } }); setRows(data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const save = async () => {
    if (!form.project_id) return toast.error("Project required");
    if (!form.work_description?.trim()) return toast.error("Description required");
    try {
      const payload = { ...form, quantity: Number(form.quantity) || 0, rate: Number(form.rate) || 0,
        estimated_value: form.estimated_value === "" || form.estimated_value === null ? null : Number(form.estimated_value),
        client_instruction_id: form.client_instruction_id || null };
      if (editing?.id) await api.put(`/proj-phase3/extra-works/${editing.id}`, payload);
      else await api.post(`/proj-phase3/extra-works`, payload);
      toast.success("Saved"); setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.extra_work_no}?`)) return;
    try { await api.delete(`/proj-phase3/extra-works/${r.id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const approve = async (r) => {
    if (!window.confirm(`Approve ${r.extra_work_no}?`)) return;
    try { await api.post(`/proj-phase3/extra-works/${r.id}/approve`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
  };
  const reject = async (r) => {
    const reason = window.prompt("Rejection reason:");
    if (!reason) return;
    try { await api.post(`/proj-phase3/extra-works/${r.id}/reject?reason=${encodeURIComponent(reason)}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Reject failed"); }
  };

  const totalBillable = rows.filter((r) => r.approval_status === "approved" && r.billing_status === "pending")
    .reduce((s, r) => s + Number(r.estimated_value || 0), 0);

  return (
    <div className="p-6 space-y-4" data-testid="page-extra-works">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><PlusSquare className="h-6 w-6 text-primary" /> Extra Work Register</h1>
          <p className="text-sm text-muted-foreground">Variation / extra work records. PM approval required before billing. Items without written client approval flagged as risk.</p>
        </div>
        {canEdit && <Button onClick={() => { setEditing({}); setForm({ ...EMPTY, project_id: filt.project_id || "" }); }} data-testid="ew-new"><Plus className="h-4 w-4 mr-1" /> New Extra Work</Button>}
      </div>

      {filt.project_id && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Total" value={rows.length} />
          <Tile label="Approved" value={rows.filter((r) => r.approval_status === "approved").length} />
          <Tile label="Pending Approval" value={rows.filter((r) => r.approval_status === "pending").length} />
          <Tile label="Billable Value" value={`₹ ${totalBillable.toLocaleString("en-IN")}`} highlight />
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Extra Works <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <select value={filt.project_id} onChange={(e) => setFilt({ ...filt, project_id: e.target.value })} className="h-7 rounded-sm border px-2" data-testid="ew-filter-project"><option value="">All projects</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}</select>
            <select value={filt.approval_status} onChange={(e) => setFilt({ ...filt, approval_status: e.target.value })} className="h-7 rounded-sm border px-2"><option value="">All approval</option>{APPROVAL.map((s) => <option key={s} value={s}>{s}</option>)}</select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">EXW #</th><th className="px-2 py-2">Project</th><th className="px-2 py-2">Description</th>
                <th className="px-2 py-2 text-right">Qty</th><th className="px-2 py-2">UOM</th>
                <th className="px-2 py-2 text-right">Rate</th><th className="px-2 py-2 text-right">Value</th>
                <th className="px-2 py-2 text-center">Approval</th><th className="px-2 py-2 text-center">Client Apv</th>
                <th className="px-2 py-2 text-center">Risk</th><th className="px-2 py-2 text-right w-32"></th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={11} className="text-center py-6 text-slate-400">No extra works</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b" data-testid={`ew-row-${r.id}`}>
                    <td className="px-2 py-1 font-mono font-bold text-primary">{r.extra_work_no}</td>
                    <td className="px-2 py-1 text-xs">{r.project_code}</td>
                    <td className="px-2 py-1 truncate max-w-[260px]">{r.work_description}</td>
                    <td className="px-2 py-1 text-right font-mono">{Number(r.quantity || 0)}</td>
                    <td className="px-2 py-1 text-xs">{r.uom || "—"}</td>
                    <td className="px-2 py-1 text-right font-mono">{Number(r.rate || 0)}</td>
                    <td className="px-2 py-1 text-right font-mono">{Number(r.estimated_value || 0).toLocaleString("en-IN")}</td>
                    <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${aTone(r.approval_status)}`}>{r.approval_status}</span></td>
                    <td className="px-2 py-1 text-center text-xs">{r.client_approval_status}</td>
                    <td className="px-2 py-1 text-center">{r.is_risk ? <AlertTriangle className="h-4 w-4 text-rose-600 inline" /> : ""}</td>
                    <td className="px-2 py-1 text-right">
                      <div className="flex justify-end gap-1">
                        {canEdit && r.approval_status === "pending" && <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`ew-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>}
                        {canApprove && r.approval_status === "pending" && <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-600" onClick={() => approve(r)} data-testid={`ew-approve-${r.id}`}><CheckCircle2 className="h-3.5 w-3.5" /></Button>}
                        {canApprove && r.approval_status === "pending" && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => reject(r)} data-testid={`ew-reject-${r.id}`}><XCircle className="h-3.5 w-3.5" /></Button>}
                        {canEdit && r.approval_status !== "approved" && <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`ew-del-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
                      </div>
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
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} Extra Work</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project *">
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} disabled={!!editing?.id} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="ew-form-project"><option value="">— select —</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select>
            </F>
            <F label="Client Instruction Ref">
              <select value={form.client_instruction_id || ""} onChange={(e) => setForm({ ...form, client_instruction_id: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm"><option value="">— none —</option>{instructions.map((i) => <option key={i.id} value={i.id}>{i.instruction_no}</option>)}</select>
            </F>
            <F label="Description *" full><Textarea rows={3} value={form.work_description} onChange={(e) => setForm({ ...form, work_description: e.target.value })} data-testid="ew-form-desc" /></F>
            <F label="Quantity"><Input type="number" step="0.01" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></F>
            <F label="UOM"><Input value={form.uom} onChange={(e) => setForm({ ...form, uom: e.target.value })} /></F>
            <F label="Rate"><Input type="number" step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} /></F>
            <F label="Estimated Value (auto from qty×rate)"><Input type="number" step="0.01" value={form.estimated_value ?? ""} onChange={(e) => setForm({ ...form, estimated_value: e.target.value })} placeholder={`${Number(form.quantity || 0) * Number(form.rate || 0)}`} /></F>
            <F label="Client Approval Status">
              <select value={form.client_approval_status} onChange={(e) => setForm({ ...form, client_approval_status: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="ew-form-client-approval">{CLIENT_APPROVAL.map((c) => <option key={c} value={c}>{c}</option>)}</select>
            </F>
            <F label="Remarks" full><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="ew-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
const ATONES = { pending: "bg-slate-50 text-slate-600 border-slate-200", approved: "bg-emerald-50 text-emerald-700 border-emerald-200", rejected: "bg-rose-50 text-rose-700 border-rose-200" };
function aTone(s) { return ATONES[s] || ATONES.pending; }
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
function Tile({ label, value, highlight }) { return <div className={`border rounded-sm p-3 ${highlight ? "bg-primary/5 border-primary/30" : ""}`}><div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div><div className={`text-xl font-bold ${highlight ? "text-primary" : ""}`}>{value}</div></div>; }
