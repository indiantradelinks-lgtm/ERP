/**
 * Internal Project Review & Status Update — Iter 120
 * Projects & Operations dedicated page. 7 factor cards + critical issues
 * + action items + decision log.
 * Backend: /api/internal-reviews · /api/action-items/inbox
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { RefreshCcw, Plus, ListTodo, AlertTriangle, Users, Boxes, ClipboardList, ShieldCheck, ShieldAlert, Receipt, Wallet, Activity } from "lucide-react";

const FACTORS = [
  { key: "manpower",          label: "Manpower",          icon: Users },
  { key: "material",          label: "Material",          icon: Boxes },
  { key: "planning",          label: "Planning",          icon: ClipboardList },
  { key: "hr_compliance",     label: "HR Compliance",     icon: ShieldCheck },
  { key: "safety_compliance", label: "Safety",            icon: ShieldAlert },
  { key: "billing",           label: "Billing",           icon: Receipt },
  { key: "payment",           label: "Payment",           icon: Wallet },
];
const STATUS_COLORS = {
  on_track: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30",
  attention_required: "bg-amber-500/10 text-amber-500 border-amber-500/30",
  delayed: "bg-orange-500/10 text-orange-500 border-orange-500/30",
  critical: "bg-red-500/10 text-red-500 border-red-500/30 animate-pulse",
  hold: "bg-purple-500/10 text-purple-500 border-purple-500/30",
  completed: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30",
  pending: "bg-muted text-muted-foreground border-border",
};
const STATUSES = ["on_track", "attention_required", "delayed", "critical", "hold", "completed", "pending"];

export default function InternalProjectReview() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [reviews, setReviews] = useState([]);
  const [currentReview, setCurrentReview] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [actionInbox, setActionInbox] = useState([]);
  const [openCreate, setOpenCreate] = useState(false);
  const [form, setForm] = useState(defaultForm());
  const [factorDlg, setFactorDlg] = useState(null);
  const [aiDlg, setAiDlg] = useState(false);
  const [aiForm, setAiForm] = useState({ title: "", related_factor: "", assigned_to: "", due_date: "", priority: "medium", remarks: "" });
  const [decDlg, setDecDlg] = useState(false);
  const [decForm, setDecForm] = useState({ decision: "", taken_by: "", impact: "medium", remarks: "" });
  const [issDlg, setIssDlg] = useState(false);
  const [issForm, setIssForm] = useState({ title: "", category: "manpower", impact: "high", description: "", responsible: "", target_resolution_date: "" });

  function defaultForm() {
    return { project_id: "", review_type: "daily", overall_status: "on_track", summary: "",
              key_decisions: "", next_review_date: "", factors: {} };
  }

  const load = async () => {
    try {
      const [pj, kp, ai] = await Promise.all([
        api.get("/projects"),
        api.get("/internal-reviews/dashboard"),
        api.get("/action-items/inbox?view=pending"),
      ]);
      setProjects(pj.data || []);
      setKpis(kp.data); setActionInbox(ai.data?.rows || []);
    } catch (e) { toast.error("Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!projectId) { setReviews([]); setCurrentReview(null); return; }
    api.get(`/internal-reviews?project_id=${projectId}`).then((r) => {
      setReviews(r.data || []);
      if ((r.data || [])[0]) setCurrentReview(r.data[0]);
    });
  }, [projectId]);

  const createReview = async () => {
    if (!projectId) { toast.error("Pick a project first"); return; }
    try {
      const payload = { ...form, project_id: projectId };
      const r = await api.post("/internal-reviews", payload);
      toast.success("Review created");
      setReviews([r.data, ...reviews]); setCurrentReview(r.data);
      setOpenCreate(false); setForm(defaultForm());
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const saveFactor = async (factorKey, data) => {
    if (!currentReview) return;
    try {
      const r = await api.patch(`/internal-reviews/${currentReview.id}`, {
        factors: { [factorKey]: data },
      });
      setCurrentReview(r.data); setFactorDlg(null);
      toast.success(`${factorKey.replace("_", " ")} updated`);
    } catch (e) { toast.error("Failed"); }
  };

  const addActionItem = async () => {
    if (!currentReview) return;
    if ((aiForm.title || "").length < 3) { toast.error("Title min 3 chars"); return; }
    try {
      await api.post(`/internal-reviews/${currentReview.id}/action-items`, aiForm);
      toast.success("Action item added"); setAiDlg(false);
      setAiForm({ title: "", related_factor: "", assigned_to: "", due_date: "", priority: "medium", remarks: "" });
      const r = await api.get(`/internal-reviews/${currentReview.id}`);
      setCurrentReview(r.data); load();
    } catch (e) { toast.error("Failed"); }
  };

  const addDecision = async () => {
    if (!currentReview) return;
    if ((decForm.decision || "").length < 3) { toast.error("Decision min 3 chars"); return; }
    try {
      await api.post(`/internal-reviews/${currentReview.id}/decisions`, decForm);
      toast.success("Decision logged"); setDecDlg(false);
      setDecForm({ decision: "", taken_by: "", impact: "medium", remarks: "" });
    } catch (e) { toast.error("Failed"); }
  };

  const addCriticalIssue = async () => {
    if (!currentReview) return;
    if (!issForm.title) { toast.error("Title required"); return; }
    try {
      await api.post(`/internal-reviews/${currentReview.id}/critical-issues`, issForm);
      toast.success("Critical issue raised"); setIssDlg(false);
      const r = await api.get(`/internal-reviews/${currentReview.id}`);
      setCurrentReview(r.data); load();
      setIssForm({ title: "", category: "manpower", impact: "high", description: "", responsible: "", target_resolution_date: "" });
    } catch (e) { toast.error("Failed"); }
  };

  const factorStatus = (key) => currentReview?.factors?.[key]?.status || "pending";

  return (
    <div className="space-y-4" data-testid="page-internal-review">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Internal Project Review & Status Update</h1>
          <p className="text-sm text-muted-foreground">Daily / weekly review · 7 factor cards · action items · decisions · critical issues</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/internal-reviews/export.xlsx${projectId ? `?project_id=${projectId}` : ""}`, "_blank"); toast.success("Excel export started"); }} data-testid="btn-export-xlsx"><Activity className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" size="sm" onClick={() => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/internal-reviews/export.csv${projectId ? `?project_id=${projectId}` : ""}`, "_blank"); toast.success("CSV export started"); }} data-testid="btn-export-csv">CSV</Button>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-4 w-4 mr-1" /> Reload</Button>
        </div>
      </div>

      {/* KPIs */}
      {kpis && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card data-testid="kpi-open-issues"><CardContent className="p-3"><div className="text-[10px] uppercase text-muted-foreground">Open Critical Issues</div><div className="text-xl font-semibold text-red-500">{kpis.open_critical_issues}</div></CardContent></Card>
          <Card data-testid="kpi-overdue-actions"><CardContent className="p-3"><div className="text-[10px] uppercase text-muted-foreground">Overdue Actions</div><div className="text-xl font-semibold text-amber-500">{kpis.overdue_action_items}</div></CardContent></Card>
          <Card data-testid="kpi-pending-actions"><CardContent className="p-3"><div className="text-[10px] uppercase text-muted-foreground">Pending Actions</div><div className="text-xl font-semibold">{kpis.pending_action_items}</div></CardContent></Card>
          <Card data-testid="kpi-reviews-today"><CardContent className="p-3"><div className="text-[10px] uppercase text-muted-foreground">Reviews Due Today</div><div className="text-xl font-semibold">{kpis.reviews_due_today}</div></CardContent></Card>
          <Card data-testid="kpi-status-breakdown"><CardContent className="p-3"><div className="text-[10px] uppercase text-muted-foreground">By Status</div><div className="text-xs mt-1 space-y-0.5">{Object.entries(kpis.by_overall_status || {}).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k.replace("_", " ")}</span><span className="font-medium">{v}</span></div>)}</div></CardContent></Card>
        </div>
      )}

      {/* Project picker + create */}
      <Card><CardContent className="p-3 flex flex-wrap items-center gap-3">
        <Select value={projectId} onValueChange={setProjectId}>
          <SelectTrigger className="w-72" data-testid="sel-project"><SelectValue placeholder="Select project…" /></SelectTrigger>
          <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}</SelectContent>
        </Select>
        <Button variant="outline" disabled={!projectId} onClick={() => setOpenCreate(true)} data-testid="btn-new-review"><Plus className="h-4 w-4 mr-1" /> New Review</Button>
        <div className="text-xs text-muted-foreground ml-auto">{reviews.length} prior review(s)</div>
      </CardContent></Card>

      {currentReview && (
        <>
          <Card><CardContent className="p-3">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-xs text-muted-foreground">{currentReview.review_type} · {currentReview.review_date}</div>
                <div className="text-sm font-medium">{currentReview.summary || "No summary"}</div>
              </div>
              <Badge className={STATUS_COLORS[currentReview.overall_status] || ""} data-testid="badge-overall-status">
                {(currentReview.overall_status || "").replace("_", " ")}
              </Badge>
            </div>
            {currentReview.next_review_date && <div className="text-[10px] uppercase text-muted-foreground">Next review: <span className="text-foreground">{currentReview.next_review_date}</span></div>}
          </CardContent></Card>

          {/* 7 factor cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="factor-grid">
            {FACTORS.map((f) => {
              const st = factorStatus(f.key);
              return (
                <Card key={f.key} className={`cursor-pointer border ${STATUS_COLORS[st]}`} onClick={() => setFactorDlg({ key: f.key, ...currentReview.factors?.[f.key] })} data-testid={`factor-${f.key}`}>
                  <CardContent className="p-3">
                    <div className="flex items-center gap-2">
                      <f.icon className="h-4 w-4" />
                      <span className="text-sm font-medium">{f.label}</span>
                    </div>
                    <Badge className={`mt-2 ${STATUS_COLORS[st]}`}>{st.replace("_", " ")}</Badge>
                    {currentReview.factors?.[f.key]?.summary && <div className="text-[10px] mt-2 text-muted-foreground line-clamp-2">{currentReview.factors[f.key].summary}</div>}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Tabs: Action Items · Decisions · Critical Issues · History */}
          <Tabs defaultValue="actions" className="mt-4">
            <TabsList>
              <TabsTrigger value="actions" data-testid="tab-actions"><ListTodo className="h-3.5 w-3.5 mr-1" /> Action Items</TabsTrigger>
              <TabsTrigger value="decisions" data-testid="tab-decisions">Decisions</TabsTrigger>
              <TabsTrigger value="issues" data-testid="tab-issues"><AlertTriangle className="h-3.5 w-3.5 mr-1" /> Critical Issues</TabsTrigger>
              <TabsTrigger value="history" data-testid="tab-history">Review History</TabsTrigger>
            </TabsList>

            <TabsContent value="actions" className="mt-3">
              <Card><CardContent className="p-3">
                <div className="flex justify-end mb-2"><Button size="sm" variant="outline" onClick={() => setAiDlg(true)} data-testid="btn-add-action"><Plus className="h-3.5 w-3.5 mr-1" /> Add</Button></div>
                <ActionItemList reviewId={currentReview.id} />
              </CardContent></Card>
            </TabsContent>
            <TabsContent value="decisions" className="mt-3">
              <Card><CardContent className="p-3">
                <div className="flex justify-end mb-2"><Button size="sm" variant="outline" onClick={() => setDecDlg(true)} data-testid="btn-add-decision"><Plus className="h-3.5 w-3.5 mr-1" /> Add</Button></div>
                <DecisionList reviewId={currentReview.id} />
              </CardContent></Card>
            </TabsContent>
            <TabsContent value="issues" className="mt-3">
              <Card><CardContent className="p-3">
                <div className="flex justify-end mb-2"><Button size="sm" variant="outline" onClick={() => setIssDlg(true)} data-testid="btn-add-issue"><AlertTriangle className="h-3.5 w-3.5 mr-1" /> Raise</Button></div>
                <IssueList projectId={projectId} />
              </CardContent></Card>
            </TabsContent>
            <TabsContent value="history" className="mt-3">
              <Card><CardContent className="p-3">
                <ul className="divide-y divide-border text-sm">
                  {reviews.map((r) => (
                    <li key={r.id} className="py-2 cursor-pointer hover:bg-muted/40 px-2" onClick={() => setCurrentReview(r)} data-testid={`history-${r.id}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{r.review_type} · {r.review_date}</span>
                        <Badge className={STATUS_COLORS[r.overall_status]}>{(r.overall_status || "").replace("_", " ")}</Badge>
                      </div>
                      <div className="text-xs text-muted-foreground">by {r.conducted_by}</div>
                    </li>
                  ))}
                </ul>
              </CardContent></Card>
            </TabsContent>
          </Tabs>
        </>
      )}

      {/* My pending action items panel */}
      {!currentReview && actionInbox.length > 0 && (
        <Card><CardContent className="p-3">
          <div className="text-sm font-medium mb-2">My pending action items ({actionInbox.length})</div>
          <ul className="divide-y divide-border text-xs">
            {actionInbox.map((a) => (
              <li key={a.id} className={`py-2 ${a._overdue ? "text-red-500" : ""}`}>
                <div className="font-medium">{a.title}</div>
                <div className="text-muted-foreground">{a.related_factor} · due {a.due_date || "-"} · {a.priority}</div>
              </li>
            ))}
          </ul>
        </CardContent></Card>
      )}

      {/* === Dialogs === */}
      <Dialog open={openCreate} onOpenChange={setOpenCreate}>
        <DialogContent data-testid="dialog-new-review">
          <DialogHeader><DialogTitle>New Internal Review</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Select value={form.review_type} onValueChange={(v) => setForm({ ...form, review_type: v })}>
              <SelectTrigger><SelectValue placeholder="Type" /></SelectTrigger>
              <SelectContent>{["daily", "weekly", "management", "site", "billing", "payment", "safety", "emergency"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={form.overall_status} onValueChange={(v) => setForm({ ...form, overall_status: v })}>
              <SelectTrigger><SelectValue placeholder="Overall status" /></SelectTrigger>
              <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s.replace("_", " ")}</SelectItem>)}</SelectContent>
            </Select>
            <Textarea placeholder="Summary" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} />
            <Input type="date" placeholder="Next review date" value={form.next_review_date} onChange={(e) => setForm({ ...form, next_review_date: e.target.value })} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenCreate(false)}>Cancel</Button>
            <Button onClick={createReview} data-testid="btn-save-review">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {factorDlg && (
        <Dialog open={!!factorDlg} onOpenChange={() => setFactorDlg(null)}>
          <DialogContent data-testid={`dialog-factor-${factorDlg.key}`}>
            <DialogHeader><DialogTitle>Update {factorDlg.key.replace("_", " ").toUpperCase()}</DialogTitle></DialogHeader>
            <FactorEditor factor={factorDlg} onSave={(d) => saveFactor(factorDlg.key, d)} onCancel={() => setFactorDlg(null)} />
          </DialogContent>
        </Dialog>
      )}

      <Dialog open={aiDlg} onOpenChange={setAiDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Action Item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Title" value={aiForm.title} onChange={(e) => setAiForm({ ...aiForm, title: e.target.value })} data-testid="input-ai-title" />
            <Select value={aiForm.related_factor || ""} onValueChange={(v) => setAiForm({ ...aiForm, related_factor: v })}>
              <SelectTrigger><SelectValue placeholder="Related factor" /></SelectTrigger>
              <SelectContent>{FACTORS.map((f) => <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>)}</SelectContent>
            </Select>
            <Input placeholder="Assigned to" value={aiForm.assigned_to} onChange={(e) => setAiForm({ ...aiForm, assigned_to: e.target.value })} />
            <Input type="date" value={aiForm.due_date} onChange={(e) => setAiForm({ ...aiForm, due_date: e.target.value })} />
            <Select value={aiForm.priority} onValueChange={(v) => setAiForm({ ...aiForm, priority: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{["low", "medium", "high", "critical"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAiDlg(false)}>Cancel</Button>
            <Button onClick={addActionItem} data-testid="btn-save-ai">Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={decDlg} onOpenChange={setDecDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Log Decision</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Textarea placeholder="Decision taken" value={decForm.decision} onChange={(e) => setDecForm({ ...decForm, decision: e.target.value })} data-testid="input-dec-text" />
            <Input placeholder="Taken by" value={decForm.taken_by} onChange={(e) => setDecForm({ ...decForm, taken_by: e.target.value })} />
            <Select value={decForm.impact} onValueChange={(v) => setDecForm({ ...decForm, impact: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{["low", "medium", "high"].map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setDecDlg(false)}>Cancel</Button><Button onClick={addDecision} data-testid="btn-save-dec">Log</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={issDlg} onOpenChange={setIssDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Raise Critical Issue</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Title" value={issForm.title} onChange={(e) => setIssForm({ ...issForm, title: e.target.value })} data-testid="input-iss-title" />
            <Textarea placeholder="Description" value={issForm.description} onChange={(e) => setIssForm({ ...issForm, description: e.target.value })} />
            <Select value={issForm.category} onValueChange={(v) => setIssForm({ ...issForm, category: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{["manpower", "material", "planning", "hr", "safety", "billing", "payment", "client", "site", "commercial", "other"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={issForm.impact} onValueChange={(v) => setIssForm({ ...issForm, impact: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{["low", "medium", "high", "critical"].map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}</SelectContent>
            </Select>
            <Input placeholder="Responsible" value={issForm.responsible} onChange={(e) => setIssForm({ ...issForm, responsible: e.target.value })} />
            <Input type="date" placeholder="Target resolution" value={issForm.target_resolution_date} onChange={(e) => setIssForm({ ...issForm, target_resolution_date: e.target.value })} />
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setIssDlg(false)}>Cancel</Button><Button onClick={addCriticalIssue} data-testid="btn-save-iss">Raise</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function FactorEditor({ factor, onSave, onCancel }) {
  const [data, setData] = useState({
    status: factor.status || "pending",
    summary: factor.summary || "",
    responsible: factor.responsible || "",
    remarks: factor.remarks || "",
    metrics: factor.metrics || {},
  });
  return (
    <>
      <div className="space-y-3">
        <Select value={data.status} onValueChange={(v) => setData({ ...data, status: v })}>
          <SelectTrigger data-testid={`sel-factor-status-${factor.key}`}><SelectValue /></SelectTrigger>
          <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s.replace("_", " ")}</SelectItem>)}</SelectContent>
        </Select>
        <Input placeholder="Summary" value={data.summary} onChange={(e) => setData({ ...data, summary: e.target.value })} />
        <Input placeholder="Responsible" value={data.responsible} onChange={(e) => setData({ ...data, responsible: e.target.value })} />
        <Textarea placeholder="Remarks" value={data.remarks} onChange={(e) => setData({ ...data, remarks: e.target.value })} />
      </div>
      <DialogFooter className="mt-3">
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={() => onSave(data)} data-testid="btn-factor-save">Save</Button>
      </DialogFooter>
    </>
  );
}

function ActionItemList({ reviewId }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/action-items/inbox?view=all").then((r) =>
      setRows((r.data?.rows || []).filter((a) => a.review_id === reviewId))
    );
  }, [reviewId]);
  const setStatus = async (aid, status) => {
    await api.patch(`/action-items/${aid}`, { status });
    setRows(rows.map((a) => a.id === aid ? { ...a, status } : a));
    toast.success(`Marked ${status}`);
  };
  if (rows.length === 0) return <div className="text-xs text-muted-foreground text-center py-3">No action items yet.</div>;
  return (
    <ul className="divide-y divide-border text-sm">
      {rows.map((a) => (
        <li key={a.id} className="py-2 flex items-center justify-between" data-testid={`ai-${a.id}`}>
          <div>
            <div className="font-medium">{a.title}</div>
            <div className="text-xs text-muted-foreground">{a.related_factor || "-"} · due {a.due_date || "-"} · {a.priority}</div>
          </div>
          <div className="space-x-1">
            <Badge variant={a.status === "completed" ? "default" : "outline"}>{a.status}</Badge>
            {a.status !== "completed" && <Button size="sm" variant="ghost" onClick={() => setStatus(a.id, "completed")} data-testid={`btn-ai-done-${a.id}`}>Done</Button>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function DecisionList({ reviewId }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    // Decision log is currently nested via review fetch; for simplicity reuse review get
    api.get(`/internal-reviews/${reviewId}`).then(() => setRows([])); // placeholder
  }, [reviewId]);
  return <div className="text-xs text-muted-foreground text-center py-3">Decisions are appended to the review (see Review History).</div>;
}

function IssueList({ projectId }) {
  return <div className="text-xs text-muted-foreground text-center py-3">Open critical issues for this project are visible in the dashboard counter above.</div>;
}
