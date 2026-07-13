/**
 * Daily Progress Report (DPR) · P&O Phase 3 (Round 3A)
 *
 * Two views in one page:
 *   • List of DPRs for a project (filter by status / date range)
 *   • Drill-down editor with header + lines + attachments + status workflow
 *     (draft → submitted → approved | rejected | revised)
 *
 * Backend: /api/proj-phase3/dprs ...
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
import {
  ClipboardCheck, Plus, Pencil, Trash2, RefreshCcw, ArrowLeft,
  Send, CheckCircle2, XCircle, RotateCcw, Paperclip, Upload, Download,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const STATUSES = ["draft", "submitted", "approved", "rejected", "revised"];
const EMPTY_HEADER = {
  project_id: "", dpr_no: "", dpr_date: new Date().toISOString().slice(0, 10),
  site_id: "", site_location: "", service_type: "", site_incharge: "",
  project_manager: "", weather_condition: "", work_performed: "",
  manpower_deployed: 0, manpower_present: 0, overtime_hours: 0,
  material_used_summary: "", tools_used_summary: "", logistics_support_summary: "",
  safety_observations: "", work_permit_status: "", issues_faced: "",
  delay_reason: "", client_instruction: "", extra_work_identified: false,
  attachment_ids: [], remarks: "",
};
const EMPTY_LINE = {
  activity_id: "", boq_line_id: "", boq_id: "", description: "", uom: "",
  qty_completed_today: 0, extra_work: false, remarks: "",
};

export default function DailyProgressReports() {
  const [projects, setProjects]   = useState([]);
  const [rows, setRows]           = useState([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [statusFilter, setStatusFilter]   = useState("");
  const [fromDate, setFromDate]   = useState("");
  const [toDate, setToDate]       = useState("");
  const [selected, setSelected]   = useState(null);     // DPR id
  const [detail, setDetail]       = useState(null);     // header + lines + attachments
  const [editingHeader, setEditingHeader] = useState(false);
  const [hForm, setHForm]         = useState(EMPTY_HEADER);
  const [editingLine, setEditingLine]     = useState(null);
  const [lForm, setLForm]         = useState(EMPTY_LINE);
  const [boqLines, setBoqLines]   = useState([]);
  const [activities, setActivities] = useState([]);
  const fileInputRef = useRef(null);
  const { user } = useAuth() || {};
  const canApprove = ["super_admin", "director", "general_manager", "dept_head", "project_manager"].includes(user?.role);
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/proj-phase3/dprs", {
          params: { project_id: projectFilter || undefined, status: statusFilter || undefined,
                    from_date: fromDate || undefined, to_date: toDate || undefined },
        }),
        api.get("/projects"),
      ]);
      setRows(a.data || []);
      setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [projectFilter, statusFilter, fromDate, toDate]);

  const loadDetail = async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/proj-phase3/dprs/${id}`);
      setDetail(data);
      // load BOQ + activities of that project for pickers
      const [boqs, acts] = await Promise.all([
        api.get(`/proj-phase2/boqs`, { params: { project_id: data.project_id } }),
        api.get(`/proj-phase2/activities/${data.project_id}`),
      ]);
      // flatten BOQ lines across all BOQs of this project
      const linePromises = (boqs.data || []).map((b) => api.get(`/proj-phase2/boqs/${b.id}/lines`));
      const lineRows = (await Promise.all(linePromises)).flatMap((r, i) =>
        (r.data || []).map((ln) => ({ ...ln, boq_id: (boqs.data || [])[i].id, boq_no: (boqs.data || [])[i].boq_no }))
      );
      setBoqLines(lineRows);
      setActivities(acts.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load DPR"); }
  };
  useEffect(() => { loadDetail(selected); }, [selected]);

  const projectsById = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);

  const saveHeader = async () => {
    if (!hForm.project_id) { toast.error("Project is required"); return; }
    if (!hForm.dpr_date)   { toast.error("DPR date is required"); return; }
    try {
      const payload = {
        ...hForm,
        manpower_deployed: Number(hForm.manpower_deployed) || 0,
        manpower_present: Number(hForm.manpower_present) || 0,
        overtime_hours: Number(hForm.overtime_hours) || 0,
        lines: detail?.lines || [],
      };
      if (editingHeader && detail?.id) {
        await api.put(`/proj-phase3/dprs/${detail.id}`, payload);
        toast.success("DPR updated");
      } else {
        const { data } = await api.post(`/proj-phase3/dprs`, payload);
        toast.success(`DPR created · ${data.dpr_no}`);
        setSelected(data.id);
      }
      setEditingHeader(false); load();
      if (detail?.id) loadDetail(detail.id);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const removeDpr = async (r) => {
    if (!window.confirm(`Delete DPR ${r.dpr_no}?`)) return;
    try {
      await api.delete(`/proj-phase3/dprs/${r.id}`);
      toast.success("DPR deleted"); load();
      if (selected === r.id) setSelected(null);
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const doSubmit  = async () => { await transition("submit", "Submitted for approval"); };
  const doApprove = async () => { await transition("approve", "DPR approved"); };
  const doRevise  = async () => { await transition("revise", "DPR moved to revision"); };
  const doReject  = async () => {
    const reason = window.prompt("Rejection reason:");
    if (!reason) return;
    try {
      await api.post(`/proj-phase3/dprs/${detail.id}/reject?reason=${encodeURIComponent(reason)}`);
      toast.success("DPR rejected"); loadDetail(detail.id); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Reject failed"); }
  };
  const transition = async (kind, ok) => {
    try {
      await api.post(`/proj-phase3/dprs/${detail.id}/${kind}`);
      toast.success(ok); loadDetail(detail.id); load();
    } catch (e) { toast.error(e.response?.data?.detail || `${kind} failed`); }
  };

  // ── Line CRUD ──
  const saveLine = async () => {
    if (!lForm.description?.trim()) { toast.error("Description is required"); return; }
    try {
      const payload = {
        ...lForm,
        activity_id: lForm.activity_id || null,
        boq_line_id: lForm.boq_line_id || null,
        boq_id: lForm.boq_id || null,
        qty_completed_today: Number(lForm.qty_completed_today) || 0,
      };
      if (editingLine?.id) {
        await api.put(`/proj-phase3/dprs/${detail.id}/lines/${editingLine.id}`, payload);
        toast.success("Line updated");
      } else {
        await api.post(`/proj-phase3/dprs/${detail.id}/lines`, payload);
        toast.success("Line added");
      }
      setEditingLine(null); loadDetail(detail.id);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const removeLine = async (ln) => {
    if (!window.confirm("Delete this line?")) return;
    try {
      await api.delete(`/proj-phase3/dprs/${detail.id}/lines/${ln.id}`);
      toast.success("Deleted"); loadDetail(detail.id);
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  // ── Attachment upload via existing /api/uploads → updates dpr.attachment_ids ──
  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !detail) return;
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("folder", "projects");
      fd.append("parent_type", "dpr");
      fd.append("parent_id", detail.id);
      fd.append("title", f.name);
      const up = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const newIds = [...(detail.attachment_ids || []), up.data.id];
      // patch header to persist attachment ref
      await api.put(`/proj-phase3/dprs/${detail.id}`, {
        ...detail, project_id: detail.project_id, lines: detail.lines || [], attachment_ids: newIds,
      });
      toast.success(`Uploaded ${f.name}`); loadDetail(detail.id);
    } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
  };

  // ─────────── Detail view ───────────
  if (selected && detail) {
    const locked = !["draft", "rejected"].includes(detail.status);
    return (
      <div className="p-6 space-y-4" data-testid="page-dpr-detail">
        <div className="flex items-center justify-between">
          <div>
            <button onClick={() => setSelected(null)} className="text-sm text-primary inline-flex items-center mb-1" data-testid="dpr-back">
              <ArrowLeft className="h-3.5 w-3.5 mr-1" /> Back to DPR list
            </button>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <ClipboardCheck className="h-6 w-6 text-primary" /> {detail.dpr_no}
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(detail.status)}`}>{detail.status}</span>
            </h1>
            <p className="text-sm text-muted-foreground">
              {detail.project_code} · {detail.project_name} — {detail.dpr_date}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {!locked && canEdit && <Button size="sm" variant="outline" onClick={() => { setHForm({ ...EMPTY_HEADER, ...detail }); setEditingHeader(true); }} data-testid="dpr-edit-header"><Pencil className="h-3.5 w-3.5 mr-1" />Edit Header</Button>}
            {detail.status === "draft" && canEdit && <Button size="sm" variant="default" onClick={doSubmit} data-testid="dpr-submit"><Send className="h-3.5 w-3.5 mr-1" />Submit</Button>}
            {(detail.status === "submitted" || detail.status === "revised") && canApprove && (
              <>
                <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={doApprove} data-testid="dpr-approve"><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Approve</Button>
                <Button size="sm" variant="outline" className="text-rose-600" onClick={doReject} data-testid="dpr-reject"><XCircle className="h-3.5 w-3.5 mr-1" />Reject</Button>
              </>
            )}
            {detail.status === "approved" && canEdit && <Button size="sm" variant="outline" onClick={doRevise} data-testid="dpr-revise"><RotateCcw className="h-3.5 w-3.5 mr-1" />Revise</Button>}
          </div>
        </div>

        {/* Header summary */}
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Site Context</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <KV k="Client" v={detail.client_name} />
              <KV k="Site" v={detail.site_location} />
              <KV k="Service Type" v={detail.service_type} />
              <KV k="Weather" v={detail.weather_condition} />
              <KV k="Site In-charge" v={detail.site_incharge} />
              <KV k="Project Manager" v={detail.project_manager} />
              <KV k="Manpower Deployed / Present" v={`${detail.manpower_deployed || 0} / ${detail.manpower_present || 0}`} />
              <KV k="Overtime (hrs)" v={detail.overtime_hours || 0} />
            </div>
            {detail.work_performed && <div className="mt-3 text-sm"><span className="text-xs uppercase tracking-wider text-muted-foreground">Work Performed</span><div className="mt-1">{detail.work_performed}</div></div>}
          </CardContent>
        </Card>

        {/* Lines table */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-base">Work Logged <span className="text-xs text-slate-400">({(detail.lines || []).length})</span></CardTitle>
            {!locked && canEdit && (
              <Button size="sm" onClick={() => { setEditingLine({}); setLForm(EMPTY_LINE); }} data-testid="dpr-line-new"><Plus className="h-3.5 w-3.5 mr-1" />Add Line</Button>
            )}
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">Description</th>
                  <th className="px-2 py-2">BOQ / Activity</th>
                  <th className="px-2 py-2">UOM</th>
                  <th className="px-2 py-2 text-right">Today</th>
                  <th className="px-2 py-2 text-right">Cumulative</th>
                  <th className="px-2 py-2 text-right">Balance</th>
                  <th className="px-2 py-2 text-center">Extra?</th>
                  <th className="px-2 py-2 text-right w-20"></th>
                </tr></thead>
                <tbody>
                  {(detail.lines || []).length === 0 && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No lines yet</td></tr>}
                  {(detail.lines || []).map((ln) => {
                    const bq = boqLines.find((b) => b.id === ln.boq_line_id);
                    const ac = activities.find((a) => a.id === ln.activity_id);
                    return (
                      <tr key={ln.id} className="border-b" data-testid={`dpr-line-${ln.id}`}>
                        <td className="px-2 py-1">{ln.description}</td>
                        <td className="px-2 py-1 text-xs">
                          {bq ? <span className="font-mono text-primary">BOQ#{bq.sl_no}</span> : ""}
                          {ac ? <span className="ml-1 font-mono text-primary">{ac.code}</span> : ""}
                          {(!bq && !ac) && <span className="text-slate-400">free-form</span>}
                        </td>
                        <td className="px-2 py-1 text-xs">{ln.uom || "—"}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.qty_completed_today || 0).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.cumulative_qty_completed || 0).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.balance_qty || 0).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-center">{ln.extra_work ? <span className="text-amber-700">⚠ Extra</span> : ""}</td>
                        <td className="px-2 py-1 text-right">
                          {!locked && canEdit && (
                            <div className="flex justify-end gap-1">
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditingLine(ln); setLForm({ ...EMPTY_LINE, ...ln }); }} data-testid={`dpr-line-edit-${ln.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeLine(ln)} data-testid={`dpr-line-del-${ln.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
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

        {/* Operations / Safety / Issues */}
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Operations &amp; Issues</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <KV k="Material Used" v={detail.material_used_summary} multiline />
            <KV k="Tools / Equipment" v={detail.tools_used_summary} multiline />
            <KV k="Logistics Support" v={detail.logistics_support_summary} multiline />
            <KV k="Work Permit Status" v={detail.work_permit_status} multiline />
            <KV k="Safety Observations" v={detail.safety_observations} multiline />
            <KV k="Issues Faced" v={detail.issues_faced} multiline />
            <KV k="Delay Reason" v={detail.delay_reason} multiline />
            <KV k="Client Instruction" v={detail.client_instruction} multiline />
          </CardContent>
        </Card>

        {/* Attachments */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-base flex items-center gap-2"><Paperclip className="h-4 w-4" />Attachments <span className="text-xs text-slate-400">({(detail.attachments || []).length})</span></CardTitle>
            {!locked && canEdit && (
              <>
                <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()} data-testid="dpr-upload"><Upload className="h-3.5 w-3.5 mr-1" /> Upload</Button>
                <input ref={fileInputRef} type="file" hidden onChange={onUpload} />
              </>
            )}
          </CardHeader>
          <CardContent>
            {(detail.attachments || []).length === 0 ? (
              <div className="text-sm text-slate-400">No attachments yet</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {(detail.attachments || []).map((a) => (
                  <a key={a.id} href={`${API}/files/${a.id}/download`} target="_blank" rel="noreferrer"
                      className="border rounded-sm p-2 flex items-center gap-2 hover:bg-slate-50 text-sm" data-testid={`dpr-att-${a.id}`}>
                    <Download className="h-3.5 w-3.5 text-primary" />
                    <span className="truncate">{a.title || a.original_filename}</span>
                  </a>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Line dialog */}
        <Dialog open={editingLine !== null} onOpenChange={(o) => !o && setEditingLine(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>{editingLine?.id ? "Edit" : "Add"} Work Line</DialogTitle></DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <F label="BOQ Line">
                <select value={lForm.boq_line_id || ""}
                         onChange={(e) => {
                           const id = e.target.value;
                           const ln = boqLines.find((x) => x.id === id);
                           setLForm({ ...lForm, boq_line_id: id, boq_id: ln?.boq_id || "",
                                      description: ln?.description || lForm.description,
                                      uom: ln?.uom || lForm.uom });
                         }}
                         className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="dpr-line-boq">
                  <option value="">— none / free-form —</option>
                  {boqLines.map((b) => <option key={b.id} value={b.id}>{b.boq_no} · {b.sl_no}. {b.description?.slice(0, 60)}</option>)}
                </select>
              </F>
              <F label="Activity">
                <select value={lForm.activity_id || ""}
                         onChange={(e) => setLForm({ ...lForm, activity_id: e.target.value })}
                         className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                  <option value="">— none —</option>
                  {activities.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}
                </select>
              </F>
              <F label="Description *" full><Textarea rows={2} value={lForm.description} onChange={(e) => setLForm({ ...lForm, description: e.target.value })} data-testid="dpr-line-desc" /></F>
              <F label="UOM"><Input value={lForm.uom} onChange={(e) => setLForm({ ...lForm, uom: e.target.value })} /></F>
              <F label="Qty Completed Today *"><Input type="number" step="0.01" value={lForm.qty_completed_today} onChange={(e) => setLForm({ ...lForm, qty_completed_today: e.target.value })} data-testid="dpr-line-qty" /></F>
              <F label="Extra Work?" full>
                <label className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!lForm.extra_work} onChange={(e) => setLForm({ ...lForm, extra_work: e.target.checked })} data-testid="dpr-line-extra" />
                  <span>Mark this line as extra work (allows cumulative to exceed BOQ qty)</span>
                </label>
              </F>
              <F label="Remarks" full><Textarea rows={2} value={lForm.remarks} onChange={(e) => setLForm({ ...lForm, remarks: e.target.value })} /></F>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingLine(null)}>Cancel</Button>
              <Button onClick={saveLine} data-testid="dpr-line-save">Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Header dialog */}
        <Dialog open={editingHeader} onOpenChange={(o) => !o && setEditingHeader(false)}>
          <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Edit DPR Header</DialogTitle></DialogHeader>
            <HeaderForm form={hForm} setForm={setHForm} projects={projects} disableProject />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingHeader(false)}>Cancel</Button>
              <Button onClick={saveHeader} data-testid="dpr-header-save">Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ─────────── List view ───────────
  return (
    <div className="p-6 space-y-4" data-testid="page-dpr-list">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardCheck className="h-6 w-6 text-primary" /> Daily Progress Reports
          </h1>
          <p className="text-sm text-muted-foreground">Site execution log — work performed, manpower, material, safety, issues. Approved DPRs auto-update project Work Progress.</p>
        </div>
        {canEdit && (
          <Button onClick={() => { setHForm({ ...EMPTY_HEADER, project_id: projectFilter || "" }); setDetail({ id: null, lines: [] }); setEditingHeader(true); setSelected(null); }} data-testid="dpr-new">
            <Plus className="h-4 w-4 mr-1" /> New DPR
          </Button>
        )}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">All DPRs <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="dpr-filter-project">
              <option value="">All projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                     className="h-7 rounded-sm border border-input bg-background px-2" data-testid="dpr-filter-status">
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="h-7 w-32" />
            <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="h-7 w-32" />
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">DPR #</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Site</th>
                  <th className="px-3 py-2 text-right">Manpower</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2">Submitted</th>
                  <th className="px-3 py-2">Approved</th>
                  <th className="px-3 py-2 text-right w-24"></th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={9} className="text-center py-8 text-slate-400">No DPRs found</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-slate-50/50 cursor-pointer" onClick={() => setSelected(r.id)} data-testid={`dpr-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono font-bold text-primary">{r.dpr_no}</td>
                    <td className="px-3 py-2 text-xs">{r.dpr_date}</td>
                    <td className="px-3 py-2 text-xs">{projectsById[r.project_id]?.code || r.project_code}</td>
                    <td className="px-3 py-2 text-xs">{r.site_location || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{r.manpower_present || 0}/{r.manpower_deployed || 0}</td>
                    <td className="px-3 py-2 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(r.status)}`}>{r.status}</span></td>
                    <td className="px-3 py-2 text-xs">{r.submitted_by || "—"}</td>
                    <td className="px-3 py-2 text-xs">{r.approved_by || "—"}</td>
                    <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                      {canEdit && (
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeDpr(r)} data-testid={`dpr-del-${r.id}`}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* New DPR dialog */}
      <Dialog open={editingHeader && !selected} onOpenChange={(o) => !o && setEditingHeader(false)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Daily Progress Report</DialogTitle></DialogHeader>
          <HeaderForm form={hForm} setForm={setHForm} projects={projects} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingHeader(false)}>Cancel</Button>
            <Button onClick={saveHeader} data-testid="dpr-header-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function HeaderForm({ form, setForm, projects, disableProject }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <F label="Project *">
        <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                 disabled={disableProject}
                 className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="dpr-form-project">
          <option value="">— select —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
        </select>
      </F>
      <F label="DPR Date *"><Input type="date" value={form.dpr_date} onChange={(e) => setForm({ ...form, dpr_date: e.target.value })} data-testid="dpr-form-date" /></F>
      <F label="DPR #"><Input value={form.dpr_no} onChange={(e) => setForm({ ...form, dpr_no: e.target.value })} placeholder="auto" /></F>
      <F label="Site Location"><Input value={form.site_location} onChange={(e) => setForm({ ...form, site_location: e.target.value })} /></F>
      <F label="Service Type"><Input value={form.service_type} onChange={(e) => setForm({ ...form, service_type: e.target.value })} /></F>
      <F label="Weather Condition"><Input value={form.weather_condition} onChange={(e) => setForm({ ...form, weather_condition: e.target.value })} placeholder="Clear / Rain / Hot" /></F>
      <F label="Site In-charge"><Input value={form.site_incharge} onChange={(e) => setForm({ ...form, site_incharge: e.target.value })} /></F>
      <F label="Project Manager"><Input value={form.project_manager} onChange={(e) => setForm({ ...form, project_manager: e.target.value })} /></F>
      <div />
      <F label="Manpower Deployed"><Input type="number" value={form.manpower_deployed} onChange={(e) => setForm({ ...form, manpower_deployed: e.target.value })} /></F>
      <F label="Manpower Present"><Input type="number" value={form.manpower_present} onChange={(e) => setForm({ ...form, manpower_present: e.target.value })} /></F>
      <F label="Overtime (hrs)"><Input type="number" step="0.5" value={form.overtime_hours} onChange={(e) => setForm({ ...form, overtime_hours: e.target.value })} /></F>
      <F label="Work Performed" full><Textarea rows={2} value={form.work_performed} onChange={(e) => setForm({ ...form, work_performed: e.target.value })} /></F>
      <F label="Material Used"><Textarea rows={2} value={form.material_used_summary} onChange={(e) => setForm({ ...form, material_used_summary: e.target.value })} /></F>
      <F label="Tools / Equipment"><Textarea rows={2} value={form.tools_used_summary} onChange={(e) => setForm({ ...form, tools_used_summary: e.target.value })} /></F>
      <F label="Logistics"><Textarea rows={2} value={form.logistics_support_summary} onChange={(e) => setForm({ ...form, logistics_support_summary: e.target.value })} /></F>
      <F label="Safety Observations"><Textarea rows={2} value={form.safety_observations} onChange={(e) => setForm({ ...form, safety_observations: e.target.value })} /></F>
      <F label="Work Permit Status"><Textarea rows={2} value={form.work_permit_status} onChange={(e) => setForm({ ...form, work_permit_status: e.target.value })} /></F>
      <F label="Issues Faced"><Textarea rows={2} value={form.issues_faced} onChange={(e) => setForm({ ...form, issues_faced: e.target.value })} /></F>
      <F label="Delay Reason"><Textarea rows={2} value={form.delay_reason} onChange={(e) => setForm({ ...form, delay_reason: e.target.value })} /></F>
      <F label="Client Instruction"><Textarea rows={2} value={form.client_instruction} onChange={(e) => setForm({ ...form, client_instruction: e.target.value })} /></F>
      <F label="Remarks" full><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
      <F label="Extra Work Identified" full>
        <label className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.extra_work_identified} onChange={(e) => setForm({ ...form, extra_work_identified: e.target.checked })} />
          <span>Mark if extra work was discovered today</span>
        </label>
      </F>
    </div>
  );
}

const TONES = {
  draft:     "bg-slate-50 text-slate-600 border-slate-200",
  submitted: "bg-blue-50 text-blue-700 border-blue-200",
  approved:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected:  "bg-rose-50 text-rose-700 border-rose-200",
  revised:   "bg-amber-50 text-amber-700 border-amber-200",
};
function tone(s) { return TONES[s] || TONES.draft; }

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
function KV({ k, v, multiline }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className={multiline ? "text-sm whitespace-pre-wrap" : "text-sm font-medium"}>{v || "—"}</div>
    </div>
  );
}
