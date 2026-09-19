/**
 * Measurement Sheet · P&O Phase 3 (Round 3B)
 * Backend: /api/proj-phase3/measurements
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Ruler, Plus, Pencil, Trash2, RefreshCcw, ArrowLeft, Send, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const MS_STATUS = ["draft", "submitted", "checked", "approved", "rejected"];
const CERT = ["pending", "certified", "partial", "rejected", "held"];
const EMPTY_H = {
  project_id: "", measurement_no: "", measurement_date: new Date().toISOString().slice(0, 10),
  period_from: "", period_to: "", title: "", description: "",
  prepared_by: "", checked_by: "", approved_by: "", attachment_ids: [], remarks: "",
};
const EMPTY_L = {
  sl_no: "", boq_line_id: "", activity_id: "", dpr_id: "",
  description: "", location: "", length: 0, width: 0, height: 0, quantity: 0,
  uom: "", rate: 0, client_certification_status: "pending", certified_quantity: 0,
  rejected_held_quantity: 0, remarks: "",
};

export default function MeasurementSheets() {
  const [projects, setProjects] = useState([]);
  const [rows, setRows] = useState([]);
  const [filt, setFilt] = useState({ project_id: "", status: "" });
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [boqLines, setBoqLines] = useState([]);
  const [editHeader, setEditHeader] = useState(null);
  const [hForm, setHForm] = useState(EMPTY_H);
  const [editLine, setEditLine] = useState(null);
  const [lForm, setLForm] = useState(EMPTY_L);
  const [certLine, setCertLine] = useState(null);
  const [cForm, setCForm] = useState({ certified_quantity: 0, client_certification_status: "certified", rejected_held_quantity: 0, remarks: "" });
  const { user } = useAuth() || {};
  const canApprove = ["super_admin", "director", "general_manager", "dept_head", "project_manager"].includes(user?.role);
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filt]);

  const load = async () => {
    try {
      const { data } = await api.get("/proj-phase3/measurements", { params: { project_id: filt.project_id || undefined, status: filt.status || undefined } });
      setRows(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const loadDetail = async (id) => {
    if (!id) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/proj-phase3/measurements/${id}`);
      setDetail(data);
      const boqs = await api.get(`/proj-phase2/boqs`, { params: { project_id: data.project_id } });
      const linePromises = (boqs.data || []).map((b) => api.get(`/proj-phase2/boqs/${b.id}/lines`));
      const lr = (await Promise.all(linePromises)).flatMap((r, i) =>
        (r.data || []).map((ln) => ({ ...ln, boq_no: (boqs.data || [])[i].boq_no }))
      );
      setBoqLines(lr);
    } catch (e) { toast.error(e.response?.data?.detail || "Load detail failed"); }
  };
  useEffect(() => { loadDetail(selected); }, [selected]);

  const saveHeader = async () => {
    if (!hForm.project_id) return toast.error("Project required");
    if (!hForm.title?.trim()) return toast.error("Title required");
    try {
      if (editHeader?.id) {
        await api.put(`/proj-phase3/measurements/${editHeader.id}`, hForm);
        toast.success("Updated");
      } else {
        const { data } = await api.post(`/proj-phase3/measurements`, hForm);
        toast.success(`Created ${data.measurement_no}`);
        setSelected(data.id);
      }
      setEditHeader(null); load();
      if (selected) loadDetail(selected);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const saveLine = async () => {
    if (!lForm.description?.trim()) return toast.error("Description required");
    try {
      const payload = { ...lForm, sl_no: lForm.sl_no === "" ? null : Number(lForm.sl_no),
        length: Number(lForm.length) || 0, width: Number(lForm.width) || 0,
        height: Number(lForm.height) || 0, quantity: Number(lForm.quantity) || 0,
        rate: Number(lForm.rate) || 0,
        boq_line_id: lForm.boq_line_id || null, activity_id: lForm.activity_id || null, dpr_id: lForm.dpr_id || null };
      if (editLine?.id) await api.put(`/proj-phase3/measurements/${selected}/lines/${editLine.id}`, payload);
      else await api.post(`/proj-phase3/measurements/${selected}/lines`, payload);
      toast.success("Saved"); setEditLine(null); loadDetail(selected);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const removeLine = async (l) => {
    if (!window.confirm("Delete line?")) return;
    try { await api.delete(`/proj-phase3/measurements/${selected}/lines/${l.id}`); loadDetail(selected); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const certify = async () => {
    try {
      await api.post(`/proj-phase3/measurements/${selected}/certify`, {
        line_id: certLine.id, certified_quantity: Number(cForm.certified_quantity) || 0,
        client_certification_status: cForm.client_certification_status,
        rejected_held_quantity: Number(cForm.rejected_held_quantity) || 0, remarks: cForm.remarks,
      });
      toast.success("Certification updated"); setCertLine(null); loadDetail(selected);
    } catch (e) { toast.error(e.response?.data?.detail || "Certify failed"); }
  };
  const trans = async (action, ok) => {
    try {
      const url = action === "reject"
        ? `/proj-phase3/measurements/${selected}/${action}?reason=${encodeURIComponent(window.prompt("Reason:") || "")}`
        : `/proj-phase3/measurements/${selected}/${action}`;
      await api.post(url); toast.success(ok); loadDetail(selected); load();
    } catch (e) { toast.error(e.response?.data?.detail || `${action} failed`); }
  };

  // ───── Detail view ─────
  if (selected && detail) {
    const locked = detail.status === "approved";
    return (
      <div className="p-6 space-y-4" data-testid="page-ms-detail">
        <div className="flex items-center justify-between">
          <div>
            <button onClick={() => setSelected(null)} className="text-sm text-primary inline-flex items-center mb-1" data-testid="ms-back"><ArrowLeft className="h-3.5 w-3.5 mr-1"/>Back</button>
            <h1 className="text-2xl font-bold flex items-center gap-2"><Ruler className="h-6 w-6 text-primary" /> {detail.measurement_no}
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(detail.status)}`}>{detail.status}</span></h1>
            <p className="text-sm text-muted-foreground">{detail.project_code} · {detail.title}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {!locked && canEdit && <Button size="sm" variant="outline" onClick={() => { setHForm({ ...EMPTY_H, ...detail }); setEditHeader(detail); }}><Pencil className="h-3.5 w-3.5 mr-1"/>Edit Header</Button>}
            {detail.status === "draft" && canEdit && <Button size="sm" onClick={() => trans("submit", "Submitted")} data-testid="ms-submit"><Send className="h-3.5 w-3.5 mr-1"/>Submit</Button>}
            {detail.status === "submitted" && canEdit && <Button size="sm" variant="outline" onClick={() => trans("check", "Checked")} data-testid="ms-check"><ShieldCheck className="h-3.5 w-3.5 mr-1"/>Mark Checked</Button>}
            {detail.status === "checked" && canApprove && <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => trans("approve", "Approved")} data-testid="ms-approve"><CheckCircle2 className="h-3.5 w-3.5 mr-1"/>Approve</Button>}
            {(detail.status === "submitted" || detail.status === "checked") && canApprove && <Button size="sm" variant="outline" className="text-rose-600" onClick={() => trans("reject", "Rejected")} data-testid="ms-reject"><XCircle className="h-3.5 w-3.5 mr-1"/>Reject</Button>}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Lines" value={(detail.lines || []).length} />
          <Tile label="Total Qty" value={Number(detail.total_quantity || 0).toLocaleString("en-IN")} />
          <Tile label="Total Amount" value={`₹ ${Number(detail.total_amount || 0).toLocaleString("en-IN")}`} />
          <Tile label="Certified Amount" value={`₹ ${Number(detail.certified_amount || 0).toLocaleString("en-IN")}`} highlight />
        </div>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-base">Lines</CardTitle>
            {!locked && canEdit && <Button size="sm" onClick={() => { setEditLine({}); setLForm(EMPTY_L); }} data-testid="ms-line-new"><Plus className="h-3.5 w-3.5 mr-1"/>Add Line</Button>}
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">Sl</th>
                  <th className="px-2 py-2">Description</th>
                  <th className="px-2 py-2">BOQ</th>
                  <th className="px-2 py-2">L × W × H</th>
                  <th className="px-2 py-2 text-right">Qty</th>
                  <th className="px-2 py-2">UOM</th>
                  <th className="px-2 py-2 text-right">Rate</th>
                  <th className="px-2 py-2 text-right">Amount</th>
                  <th className="px-2 py-2 text-right">Certified</th>
                  <th className="px-2 py-2 text-center">Status</th>
                  <th className="px-2 py-2 text-right w-24"></th>
                </tr></thead>
                <tbody>
                  {(detail.lines || []).length === 0 && <tr><td colSpan={11} className="text-center py-6 text-slate-400">No lines</td></tr>}
                  {(detail.lines || []).map((ln) => {
                    const bq = boqLines.find((b) => b.id === ln.boq_line_id);
                    return (
                      <tr key={ln.id} className="border-b" data-testid={`ms-line-${ln.id}`}>
                        <td className="px-2 py-1 font-mono">{ln.sl_no}</td>
                        <td className="px-2 py-1">{ln.description}</td>
                        <td className="px-2 py-1 text-xs">{bq ? `${bq.boq_no} #${bq.sl_no}` : "—"}</td>
                        <td className="px-2 py-1 text-xs font-mono">{Number(ln.length || 0)} × {Number(ln.width || 0)} × {Number(ln.height || 0)}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.quantity || 0)}</td>
                        <td className="px-2 py-1 text-xs">{ln.uom}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.rate || 0)}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.amount || 0).toLocaleString("en-IN")}</td>
                        <td className="px-2 py-1 text-right font-mono">{Number(ln.certified_quantity || 0)}</td>
                        <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase px-1 py-0.5 rounded border ${certTone(ln.client_certification_status)}`}>{ln.client_certification_status}</span></td>
                        <td className="px-2 py-1 text-right">
                          {canEdit && !locked && (
                            <div className="flex justify-end gap-1">
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditLine(ln); setLForm({ ...EMPTY_L, ...ln }); }} data-testid={`ms-line-edit-${ln.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-emerald-700" onClick={() => { setCertLine(ln); setCForm({ certified_quantity: ln.certified_quantity || ln.quantity, client_certification_status: "certified", rejected_held_quantity: 0, remarks: "" }); }} data-testid={`ms-line-cert-${ln.id}`}><ShieldCheck className="h-3.5 w-3.5" /></Button>
                              <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => removeLine(ln)} data-testid={`ms-line-del-${ln.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
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

        {/* line edit dialog */}
        <Dialog open={editLine !== null} onOpenChange={(o) => !o && setEditLine(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>{editLine?.id ? "Edit" : "Add"} Measurement Line</DialogTitle></DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <F label="BOQ Line">
                <select value={lForm.boq_line_id} onChange={(e) => { const id = e.target.value; const ln = boqLines.find((x) => x.id === id); setLForm({ ...lForm, boq_line_id: id, description: ln?.description || lForm.description, uom: ln?.uom || lForm.uom, rate: ln?.unit_rate || lForm.rate }); }}
                         className="h-9 w-full rounded-sm border px-2 text-sm">
                  <option value="">— none —</option>
                  {boqLines.map((b) => <option key={b.id} value={b.id}>{b.boq_no} #{b.sl_no} · {b.description?.slice(0, 60)}</option>)}
                </select>
              </F>
              <F label="Sl No"><Input type="number" value={lForm.sl_no} onChange={(e) => setLForm({ ...lForm, sl_no: e.target.value })} placeholder="auto" /></F>
              <F label="Description *" full><Textarea rows={2} value={lForm.description} onChange={(e) => setLForm({ ...lForm, description: e.target.value })} data-testid="ms-line-desc" /></F>
              <F label="Location"><Input value={lForm.location} onChange={(e) => setLForm({ ...lForm, location: e.target.value })} /></F>
              <F label="UOM"><Input value={lForm.uom} onChange={(e) => setLForm({ ...lForm, uom: e.target.value })} /></F>
              <F label="Length"><Input type="number" step="0.01" value={lForm.length} onChange={(e) => setLForm({ ...lForm, length: e.target.value })} /></F>
              <F label="Width"><Input type="number" step="0.01" value={lForm.width} onChange={(e) => setLForm({ ...lForm, width: e.target.value })} /></F>
              <F label="Height"><Input type="number" step="0.01" value={lForm.height} onChange={(e) => setLForm({ ...lForm, height: e.target.value })} /></F>
              <F label="Quantity (auto if blank)"><Input type="number" step="0.01" value={lForm.quantity} onChange={(e) => setLForm({ ...lForm, quantity: e.target.value })} data-testid="ms-line-qty" /></F>
              <F label="Rate"><Input type="number" step="0.01" value={lForm.rate} onChange={(e) => setLForm({ ...lForm, rate: e.target.value })} /></F>
              <F label="Remarks" full><Textarea rows={2} value={lForm.remarks} onChange={(e) => setLForm({ ...lForm, remarks: e.target.value })} /></F>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditLine(null)}>Cancel</Button>
              <Button onClick={saveLine} data-testid="ms-line-save">Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* certification dialog */}
        <Dialog open={certLine !== null} onOpenChange={(o) => !o && setCertLine(null)}>
          <DialogContent>
            <DialogHeader><DialogTitle>Client Certification</DialogTitle></DialogHeader>
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">{certLine?.description}</div>
              <div className="grid grid-cols-2 gap-3">
                <F label="Certified Qty"><Input type="number" value={cForm.certified_quantity} onChange={(e) => setCForm({ ...cForm, certified_quantity: e.target.value })} data-testid="ms-cert-qty" /></F>
                <F label="Status">
                  <select value={cForm.client_certification_status} onChange={(e) => setCForm({ ...cForm, client_certification_status: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="ms-cert-status">
                    {CERT.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </F>
                <F label="Rejected / Held"><Input type="number" value={cForm.rejected_held_quantity} onChange={(e) => setCForm({ ...cForm, rejected_held_quantity: e.target.value })} /></F>
                <F label="Remarks"><Input value={cForm.remarks} onChange={(e) => setCForm({ ...cForm, remarks: e.target.value })} /></F>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCertLine(null)}>Cancel</Button>
              <Button onClick={certify} data-testid="ms-cert-save">Save Certification</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* header dialog */}
        <Dialog open={editHeader !== null} onOpenChange={(o) => !o && setEditHeader(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>Edit Header</DialogTitle></DialogHeader>
            <HeaderForm form={hForm} setForm={setHForm} projects={projects} disableProject />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditHeader(null)}>Cancel</Button>
              <Button onClick={saveHeader}>Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ───── List view ─────
  return (
    <div className="p-6 space-y-4" data-testid="page-ms-list">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Ruler className="h-6 w-6 text-primary" /> Measurement Sheets</h1>
          <p className="text-sm text-muted-foreground">Field measurements linked to BOQ. Certified qty feeds Accounts for RA billing.</p>
        </div>
        {canEdit && <Button onClick={() => { setHForm({ ...EMPTY_H, project_id: filt.project_id || "" }); setEditHeader({}); }} data-testid="ms-new"><Plus className="h-4 w-4 mr-1" /> New Sheet</Button>}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Sheets <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex items-center gap-2 text-xs">
            <select value={filt.project_id} onChange={(e) => setFilt({ ...filt, project_id: e.target.value })} className="h-7 rounded-sm border px-2" data-testid="ms-filter-project">
              <option value="">All projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
            <select value={filt.status} onChange={(e) => setFilt({ ...filt, status: e.target.value })} className="h-7 rounded-sm border px-2">
              <option value="">All statuses</option>
              {MS_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">MS #</th>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Project</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2 text-center">Status</th>
                <th className="px-3 py-2">Prepared</th>
                <th className="px-3 py-2">Approved</th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-slate-400">No sheets</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-slate-50/50 cursor-pointer" onClick={() => setSelected(r.id)} data-testid={`ms-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono font-bold text-primary">{r.measurement_no}</td>
                    <td className="px-3 py-2 text-xs">{r.measurement_date}</td>
                    <td className="px-3 py-2 text-xs">{r.project_code}</td>
                    <td className="px-3 py-2">{r.title}</td>
                    <td className="px-3 py-2 text-center"><span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${tone(r.status)}`}>{r.status}</span></td>
                    <td className="px-3 py-2 text-xs">{r.prepared_by || "—"}</td>
                    <td className="px-3 py-2 text-xs">{r.approved_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editHeader !== null && !selected} onOpenChange={(o) => !o && setEditHeader(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>New Measurement Sheet</DialogTitle></DialogHeader>
          <HeaderForm form={hForm} setForm={setHForm} projects={projects} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditHeader(null)}>Cancel</Button>
            <Button onClick={saveHeader} data-testid="ms-header-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function HeaderForm({ form, setForm, projects, disableProject }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <F label="Project *">
        <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} disabled={disableProject} className="h-9 w-full rounded-sm border px-2 text-sm" data-testid="ms-form-project">
          <option value="">— select —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
        </select>
      </F>
      <F label="Date *"><Input type="date" value={form.measurement_date} onChange={(e) => setForm({ ...form, measurement_date: e.target.value })} /></F>
      <F label="Title *" full><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="ms-form-title" /></F>
      <F label="MS #"><Input value={form.measurement_no} onChange={(e) => setForm({ ...form, measurement_no: e.target.value })} placeholder="auto" /></F>
      <F label="Period From"><Input type="date" value={form.period_from} onChange={(e) => setForm({ ...form, period_from: e.target.value })} /></F>
      <F label="Period To"><Input type="date" value={form.period_to} onChange={(e) => setForm({ ...form, period_to: e.target.value })} /></F>
      <F label="Prepared By"><Input value={form.prepared_by} onChange={(e) => setForm({ ...form, prepared_by: e.target.value })} /></F>
      <F label="Checked By"><Input value={form.checked_by} onChange={(e) => setForm({ ...form, checked_by: e.target.value })} /></F>
      <F label="Approved By"><Input value={form.approved_by} onChange={(e) => setForm({ ...form, approved_by: e.target.value })} /></F>
      <F label="Description" full><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></F>
      <F label="Remarks" full><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
    </div>
  );
}

const TONES = { draft: "bg-slate-50 text-slate-600 border-slate-200", submitted: "bg-blue-50 text-blue-700 border-blue-200", checked: "bg-amber-50 text-amber-700 border-amber-200", approved: "bg-emerald-50 text-emerald-700 border-emerald-200", rejected: "bg-rose-50 text-rose-700 border-rose-200" };
const CTONES = { pending: "bg-slate-50 text-slate-600", certified: "bg-emerald-50 text-emerald-700", partial: "bg-amber-50 text-amber-700", rejected: "bg-rose-50 text-rose-700", held: "bg-amber-50 text-amber-700" };
function tone(s) { return TONES[s] || TONES.draft; }
function certTone(s) { return (CTONES[s] || CTONES.pending) + " border"; }
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
function Tile({ label, value, highlight }) { return <div className={`border rounded-sm p-3 ${highlight ? "bg-primary/5 border-primary/30" : ""}`}><div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div><div className={`text-xl font-bold ${highlight ? "text-primary" : ""}`}>{value}</div></div>; }
