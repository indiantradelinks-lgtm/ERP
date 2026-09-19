/**
 * Project Closure Center · P&O Phase 5
 *
 * Single workbench that finalizes a project. Five tabs:
 *   • Closure Checklist (18 auto-evaluated items + manual override)
 *   • RA Billing Support (live computed + draft → submit → invoiced)
 *   • Profitability (revenue / cost / margin / status badge)
 *   • Client Handover + JCC (create + issue)
 *   • Reports Center (20 named Excel exports for this project)
 *   • Audit Trail (chronological project log)
 *
 * Backend: /api/proj-phase5/*
 */
import { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ClipboardCheck, DollarSign, TrendingUp, Award, FileSpreadsheet, History, CheckCircle2, RefreshCcw, Download, Send, FileCheck2, AlertTriangle, Lock } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

export default function ProjectClosureCenter() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [tab, setTab] = useState("checklist");

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="page-closure-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Lock className="h-6 w-6 text-primary" /> Project Closure Center</h1>
          <p className="text-sm text-muted-foreground">RA billing · Closure checklist · Profitability · Handover · JCC · Reports · Audit — final-mile workbench.</p>
        </div>
        <Select value={projectId || undefined} onValueChange={(v) => setProjectId(v)}>
          <SelectTrigger className="h-9 min-w-[280px]" data-testid="closure-project-select">
            <SelectValue placeholder="— select project —" />
          </SelectTrigger>
          <SelectContent>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id} data-testid={`closure-project-opt-${p.id}`}>
                {p.code} · {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!projectId && <Card><CardContent className="py-12 text-center text-slate-400">Select a project to open its closure workbench.</CardContent></Card>}

      {projectId && (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="checklist" data-testid="closure-tab-checklist"><ClipboardCheck className="h-3.5 w-3.5 mr-1" />Checklist</TabsTrigger>
            <TabsTrigger value="ra" data-testid="closure-tab-ra"><DollarSign className="h-3.5 w-3.5 mr-1" />RA Billing</TabsTrigger>
            <TabsTrigger value="profit" data-testid="closure-tab-profit"><TrendingUp className="h-3.5 w-3.5 mr-1" />Profitability</TabsTrigger>
            <TabsTrigger value="handover" data-testid="closure-tab-handover"><Award className="h-3.5 w-3.5 mr-1" />Handover &amp; JCC</TabsTrigger>
            <TabsTrigger value="reports" data-testid="closure-tab-reports"><FileSpreadsheet className="h-3.5 w-3.5 mr-1" />Reports</TabsTrigger>
            <TabsTrigger value="audit" data-testid="closure-tab-audit"><History className="h-3.5 w-3.5 mr-1" />Audit Trail</TabsTrigger>
          </TabsList>
          <TabsContent value="checklist"><ChecklistView projectId={projectId} /></TabsContent>
          <TabsContent value="ra"><RAView projectId={projectId} /></TabsContent>
          <TabsContent value="profit"><ProfitView projectId={projectId} /></TabsContent>
          <TabsContent value="handover"><HandoverView projectId={projectId} /></TabsContent>
          <TabsContent value="reports"><ReportsView projectId={projectId} /></TabsContent>
          <TabsContent value="audit"><AuditView projectId={projectId} /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function ChecklistView({ projectId }) {
  const [data, setData] = useState(null);
  const load = async () => {
    try { const { data } = await api.get(`/proj-phase5/closure/${projectId}/checklist`); setData(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); }, [projectId]);
  const toggle = async (it) => {
    try {
      await api.post(`/proj-phase5/closure/${projectId}/mark-item`, { key: it.key, complete: !it.complete });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const finalClose = async () => {
    const reason = window.prompt("Closure override reason (leave blank if no blockers):") ?? "";
    try {
      await api.post(`/proj-phase5/closure/${projectId}/complete`, null, { params: { override_reason: reason || undefined } });
      toast.success("Project closed"); load();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === "object" ? `${d.message}: ${JSON.stringify(d.blockers)}` : (d || "Failed"));
    }
  };
  if (!data) return <div className="py-8 text-center text-slate-400">Loading…</div>;
  return (
    <Card className="mt-3">
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-base">Closure Checklist · <span className="text-primary">{data.done}/{data.total}</span> complete ({data.completion_pct}%)</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={finalClose} data-testid="closure-final"><Lock className="h-3.5 w-3.5 mr-1" />Close Project</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {data.items.map((it) => (
            <button key={it.key} onClick={() => toggle(it)} data-testid={`closure-item-${it.key}`}
                     className={`text-left border rounded-sm p-2 flex items-center justify-between hover:bg-slate-50 ${it.complete ? "border-emerald-300 bg-emerald-50/50" : ""}`}>
              <span className="text-sm">{it.label}{it.hint === "manual" && <span className="ml-2 text-[10px] uppercase text-amber-700">manual</span>}</span>
              {it.complete ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <span className="text-xs text-slate-400">incomplete</span>}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function RAView({ projectId }) {
  const [data, setData] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [form, setForm] = useState({ retention_pct: 5, gst_pct: 18, tds_pct: 0, billing_period_from: "", billing_period_to: "", remarks: "" });
  const load = async () => {
    try {
      const [c, d] = await Promise.all([
        api.get(`/proj-phase5/ra-billing/${projectId}/computed`),
        api.get(`/proj-phase5/ra-billing`, { params: { project_id: projectId } }),
      ]);
      setData(c.data); setDrafts(d.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); }, [projectId]);
  const createDraft = async () => {
    try { await api.post(`/proj-phase5/ra-billing`, { project_id: projectId, ...form, retention_pct: Number(form.retention_pct) || 0, gst_pct: Number(form.gst_pct) || 0, tds_pct: Number(form.tds_pct) || 0 }); toast.success("RA draft created"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const submitDraft = async (id) => { try { await api.post(`/proj-phase5/ra-billing/${id}/submit`); load(); } catch (e) { toast.error(e.response?.data?.detail); } };
  if (!data) return <div className="py-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="space-y-4 mt-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Computed Billing Position</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
          <KV k="Work Order" v={`₹ ${Number(data.work_order_value).toLocaleString("en-IN")}`} />
          <KV k="Previous Billed" v={`₹ ${Number(data.previous_billed).toLocaleString("en-IN")}`} />
          <KV k="Certified Subtotal" v={`₹ ${Number(data.certified_subtotal).toLocaleString("en-IN")}`} highlight />
          <KV k="Current Billing" v={`₹ ${Number(data.current_billing).toLocaleString("en-IN")}`} highlight />
          <KV k="Balance" v={`₹ ${Number(data.balance_after_billing).toLocaleString("en-IN")}`} />
          {data.exceeds_wo_value && <div className="md:col-span-5 text-rose-700 text-sm flex items-center gap-1"><AlertTriangle className="h-4 w-4" />Billing exceeds Work Order value — approved variation/exception required.</div>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Create New RA Draft</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <F label="Period From"><Input type="date" value={form.billing_period_from} onChange={(e) => setForm({ ...form, billing_period_from: e.target.value })} /></F>
          <F label="Period To"><Input type="date" value={form.billing_period_to} onChange={(e) => setForm({ ...form, billing_period_to: e.target.value })} /></F>
          <F label="Retention %"><Input type="number" value={form.retention_pct} onChange={(e) => setForm({ ...form, retention_pct: e.target.value })} /></F>
          <F label="GST %"><Input type="number" value={form.gst_pct} onChange={(e) => setForm({ ...form, gst_pct: e.target.value })} /></F>
          <F label="TDS %"><Input type="number" value={form.tds_pct} onChange={(e) => setForm({ ...form, tds_pct: e.target.value })} /></F>
          <F label="Remarks" full><Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
          <div className="md:col-span-5"><Button onClick={createDraft} data-testid="ra-create">Create RA Draft</Button></div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Drafts · {drafts.length}</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-2 py-2">RA #</th><th className="px-2 py-2">Period</th><th className="px-2 py-2 text-right">Current</th><th className="px-2 py-2 text-right">Net Payable</th><th className="px-2 py-2">Status</th><th className="px-2 py-2 text-right"></th>
            </tr></thead>
            <tbody>
              {drafts.length === 0 && <tr><td colSpan={6} className="text-center py-4 text-slate-400">No drafts</td></tr>}
              {drafts.map((d) => (
                <tr key={d.id} className="border-b" data-testid={`ra-row-${d.id}`}>
                  <td className="px-2 py-1 font-mono font-bold text-primary">{d.ra_no}</td>
                  <td className="px-2 py-1 text-xs">{d.billing_period_from} → {d.billing_period_to}</td>
                  <td className="px-2 py-1 text-right font-mono">₹ {Number(d.current_billing).toLocaleString("en-IN")}</td>
                  <td className="px-2 py-1 text-right font-mono">₹ {Number(d.net_payable).toLocaleString("en-IN")}</td>
                  <td className="px-2 py-1 text-xs">{d.status}</td>
                  <td className="px-2 py-1 text-right">{d.status === "draft" && <Button size="sm" variant="outline" onClick={() => submitDraft(d.id)} data-testid={`ra-submit-${d.id}`}><Send className="h-3.5 w-3.5 mr-1" />Submit</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function ProfitView({ projectId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get(`/proj-phase5/profitability/${projectId}`).then((r) => setData(r.data)).catch((e) => toast.error(e.response?.data?.detail || "Failed"));
  }, [projectId]);
  if (!data) return <div className="py-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
      <Card><CardHeader className="pb-2"><CardTitle className="text-base">Revenue</CardTitle></CardHeader><CardContent className="text-sm space-y-1">
        <KV k="Work Order Value" v={`₹ ${Number(data.revenue.work_order_value).toLocaleString("en-IN")}`} />
        <KV k="Invoice Raised" v={`₹ ${Number(data.revenue.invoice_raised).toLocaleString("en-IN")}`} />
        <KV k="Collection" v={`₹ ${Number(data.revenue.collection).toLocaleString("en-IN")}`} />
        <KV k="Outstanding" v={`₹ ${Number(data.revenue.outstanding).toLocaleString("en-IN")}`} />
        <KV k="Pending Billing" v={`₹ ${Number(data.revenue.pending_billing).toLocaleString("en-IN")}`} />
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle className="text-base">Cost</CardTitle></CardHeader><CardContent className="text-sm space-y-1">
        <KV k="Total Cost" v={`₹ ${Number(data.cost.total).toLocaleString("en-IN")}`} />
        <KV k="Approved Budget" v={`₹ ${Number(data.cost.budget).toLocaleString("en-IN")}`} />
        <KV k="Variance" v={`₹ ${Number(data.cost.variance).toLocaleString("en-IN")}`} />
      </CardContent></Card>
      <Card className={data.profitability.status === "loss" ? "border-rose-300" : ""}><CardHeader className="pb-2"><CardTitle className="text-base">Profitability</CardTitle></CardHeader><CardContent className="text-sm space-y-1">
        <KV k="Gross Profit" v={`₹ ${Number(data.profitability.gross_profit).toLocaleString("en-IN")}`} highlight />
        <KV k="Margin %" v={`${data.profitability.margin_pct}%`} highlight />
        <div className="mt-2"><span className={`text-xs uppercase tracking-wider px-2 py-1 rounded border ${profitTone(data.profitability.status)}`}>{data.profitability.status}</span></div>
        <KV k="Health" v={data.profitability.health} />
      </CardContent></Card>
    </div>
  );
}

function HandoverView({ projectId }) {
  const [hos, setHos] = useState([]);
  const [jccs, setJccs] = useState([]);
  const [hoForm, setHoForm] = useState({ project_id: projectId, handover_date: new Date().toISOString().slice(0, 10), work_completed: "", pending_points: "", client_representative: "", itl_representative: "", documents_submitted: "", final_acceptance_status: "pending", remarks: "" });
  const [jccForm, setJccForm] = useState({ project_id: projectId, jcc_date: new Date().toISOString().slice(0, 10), issued_to: "", scope_summary: "", completion_date: "", defect_liability_period: "" });
  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get(`/proj-phase5/handovers/client`, { params: { project_id: projectId } }),
        api.get(`/proj-phase5/handovers/jcc`, { params: { project_id: projectId } }),
      ]);
      setHos(a.data || []); setJccs(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); setHoForm((f) => ({ ...f, project_id: projectId })); setJccForm((f) => ({ ...f, project_id: projectId })); }, [projectId]);
  const createHo = async () => { try { await api.post(`/proj-phase5/handovers/client`, hoForm); toast.success("Handover created"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const createJcc = async () => { try { await api.post(`/proj-phase5/handovers/jcc`, jccForm); toast.success("JCC created"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  const issueJcc = async (id) => { try { await api.post(`/proj-phase5/handovers/jcc/${id}/issue`); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); } };
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Client Handover</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <F label="Date"><Input type="date" value={hoForm.handover_date} onChange={(e) => setHoForm({ ...hoForm, handover_date: e.target.value })} /></F>
            <F label="Client Rep"><Input value={hoForm.client_representative} onChange={(e) => setHoForm({ ...hoForm, client_representative: e.target.value })} /></F>
            <F label="ITL Rep"><Input value={hoForm.itl_representative} onChange={(e) => setHoForm({ ...hoForm, itl_representative: e.target.value })} /></F>
            <F label="Acceptance">
              <select value={hoForm.final_acceptance_status} onChange={(e) => setHoForm({ ...hoForm, final_acceptance_status: e.target.value })} className="h-9 w-full rounded-sm border px-2 text-sm">
                <option value="pending">pending</option><option value="accepted">accepted</option><option value="conditional">conditional</option><option value="rejected">rejected</option>
              </select>
            </F>
          </div>
          <F label="Work Completed" full><Textarea rows={2} value={hoForm.work_completed} onChange={(e) => setHoForm({ ...hoForm, work_completed: e.target.value })} /></F>
          <F label="Pending Points" full><Textarea rows={2} value={hoForm.pending_points} onChange={(e) => setHoForm({ ...hoForm, pending_points: e.target.value })} /></F>
          <Button onClick={createHo} data-testid="ho-create">Create Handover</Button>
          <div className="mt-3 max-h-40 overflow-y-auto">
            {hos.map((h) => (
              <div key={h.id} className="border-b py-1 text-xs" data-testid={`ho-row-${h.id}`}><span className="font-mono font-bold text-primary mr-1">{h.handover_no}</span>{h.handover_date} · {h.final_acceptance_status}</div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Job Completion Certificate (JCC)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <F label="JCC Date"><Input type="date" value={jccForm.jcc_date} onChange={(e) => setJccForm({ ...jccForm, jcc_date: e.target.value })} /></F>
            <F label="Completion Date"><Input type="date" value={jccForm.completion_date} onChange={(e) => setJccForm({ ...jccForm, completion_date: e.target.value })} /></F>
            <F label="Issued To"><Input value={jccForm.issued_to} onChange={(e) => setJccForm({ ...jccForm, issued_to: e.target.value })} /></F>
            <F label="Defect Liability"><Input value={jccForm.defect_liability_period} onChange={(e) => setJccForm({ ...jccForm, defect_liability_period: e.target.value })} placeholder="e.g. 12 months" /></F>
          </div>
          <F label="Scope Summary" full><Textarea rows={2} value={jccForm.scope_summary} onChange={(e) => setJccForm({ ...jccForm, scope_summary: e.target.value })} /></F>
          <Button onClick={createJcc} data-testid="jcc-create">Create JCC</Button>
          <div className="mt-3 max-h-40 overflow-y-auto">
            {jccs.map((j) => (
              <div key={j.id} className="border-b py-1 text-xs flex items-center justify-between" data-testid={`jcc-row-${j.id}`}>
                <span><span className="font-mono font-bold text-primary mr-1">{j.jcc_no}</span>{j.jcc_date} · {j.status}</span>
                {j.status === "draft" && <Button size="sm" variant="ghost" onClick={() => issueJcc(j.id)} data-testid={`jcc-issue-${j.id}`}><FileCheck2 className="h-3.5 w-3.5" /></Button>}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ReportsView({ projectId }) {
  const [reports, setReports] = useState([]);
  useEffect(() => { api.get("/proj-phase5/reports").then((r) => setReports(r.data || [])).catch(() => {}); }, []);
  const dl = (rt) => window.open(`${API}/proj-phase5/reports/${rt}?project_id=${projectId}`, "_blank");
  return (
    <Card className="mt-3">
      <CardHeader className="pb-2"><CardTitle className="text-base">Project Reports (Excel) · {reports.length}</CardTitle></CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {reports.map((r) => (
            <button key={r.report_type} onClick={() => dl(r.report_type)} className="text-left border rounded-sm p-2 hover:bg-slate-50 flex items-center justify-between text-sm" data-testid={`report-${r.report_type}`}>
              <span>{r.label}</span><Download className="h-3.5 w-3.5 text-primary" />
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function AuditView({ projectId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get(`/proj-phase5/audit/${projectId}`).then((r) => setData(r.data)).catch(() => setData({ rows: [], count: 0 }));
  }, [projectId]);
  if (!data) return <div className="py-8 text-center text-slate-400">Loading…</div>;
  return (
    <Card className="mt-3">
      <CardHeader className="pb-2"><CardTitle className="text-base">Audit Trail · {data.count} entries</CardTitle></CardHeader>
      <CardContent>
        {data.rows.length === 0 ? <div className="text-slate-400 text-sm">No audit entries for this project.</div> : (
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background"><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">When</th><th className="px-2 py-2">User</th><th className="px-2 py-2">Action</th><th className="px-2 py-2">Resource</th><th className="px-2 py-2">Record</th>
              </tr></thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={r.id || i} className="border-b" data-testid={`audit-row-${i}`}>
                    <td className="px-2 py-1 text-xs whitespace-nowrap">{r.ts || r.at || "—"}</td>
                    <td className="px-2 py-1 text-xs">{r.actor_name || r.user_name || r.user_email || "—"}</td>
                    <td className="px-2 py-1 text-xs font-medium">{r.action}</td>
                    <td className="px-2 py-1 text-xs">{r.resource}</td>
                    <td className="px-2 py-1 text-xs font-mono">{r.record_id || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const PROFIT_TONES = { profitable: "bg-emerald-50 text-emerald-700 border-emerald-200", low_margin: "bg-amber-50 text-amber-700 border-amber-200", at_risk: "bg-orange-50 text-orange-700 border-orange-200", loss: "bg-rose-50 text-rose-700 border-rose-200" };
function profitTone(s) { return PROFIT_TONES[s] || PROFIT_TONES.profitable; }
function F({ label, full, children }) { return <div className={full ? "md:col-span-2" : ""}><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>; }
function KV({ k, v, highlight }) {
  return (
    <div className="flex justify-between">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{k}</span>
      <span className={`font-mono ${highlight ? "font-bold text-primary" : ""}`}>{v || "—"}</span>
    </div>
  );
}
