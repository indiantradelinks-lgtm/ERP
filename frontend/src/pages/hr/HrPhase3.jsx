// HR Phase 3 — Manpower Planning · Deployment · Mobilization · Demobilization
// · Replacement · Project/Site rollups
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { api, apiErrorMessage } from "@/lib/api";
import { ProjectSelect, ClientSelect } from "@/components/MasterSelect";
import { toast } from "sonner";
import {
  Users, Briefcase, MapPin, Plus, RefreshCw, Check, X,
  Calendar, AlertTriangle, ArrowRightLeft, Activity, ClipboardList, Filter,
} from "lucide-react";

const today = () => new Date().toISOString().slice(0, 10);

const StatusBadge = ({ value }) => {
  const tone = {
    planned: "bg-slate-100 text-slate-800",
    approved: "bg-blue-100 text-blue-900",
    mobilized: "bg-violet-100 text-violet-900",
    active: "bg-emerald-100 text-emerald-900",
    demobilized: "bg-amber-100 text-amber-900",
    returned: "bg-amber-100 text-amber-900",
    closed: "bg-slate-200 text-slate-700",
    pending: "bg-amber-100 text-amber-900",
    approved_: "bg-emerald-100 text-emerald-900",
    rejected: "bg-rose-100 text-rose-900",
    open: "bg-blue-100 text-blue-900",
    ok: "bg-emerald-100 text-emerald-900",
    in_progress: "bg-amber-100 text-amber-900",
    not_required: "bg-slate-100 text-slate-600",
    failed: "bg-rose-100 text-rose-900",
  }[value] || "bg-slate-100 text-slate-700";
  return <Badge className={`text-xs border ${tone}`} data-testid={`status-${value}`}>{value || "—"}</Badge>;
};

const Field = ({ label, children }) => (
  <div className="space-y-1">
    <Label className="text-xs">{label}</Label>
    {children}
  </div>
);

function Tile({ label, value, testid, color = "text-slate-900" }) {
  return (
    <Card data-testid={testid}><CardContent className="p-4">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
    </CardContent></Card>
  );
}

// ─────────── DASHBOARD ───────────
function DashboardView() {
  const [d, setD] = useState(null);
  useEffect(() => { (async () => {
    try { setD((await api.get("/hr3/dashboard")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  })(); }, []);
  if (!d) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
      <Tile label="Open Requirements" value={d.open_requirements} testid="hr3-tile-open-reqs" />
      <Tile label="Total Shortage" value={d.total_shortage} testid="hr3-tile-shortage" color="text-rose-700" />
      <Tile label="Active Deployments" value={d.active_deployments} testid="hr3-tile-active" color="text-emerald-700" />
      <Tile label="Planned" value={d.planned_deployments} testid="hr3-tile-planned" />
      <Tile label="Mob Open" value={d.mobilizations_open} testid="hr3-tile-mob-open" />
      <Tile label="Demob Open" value={d.demobilizations_open} testid="hr3-tile-demob-open" />
      <Tile label="Replacements Open" value={d.replacements_open} testid="hr3-tile-rep-open" />
    </div>
  );
}

// ─────────── MANPOWER REQUIREMENTS ───────────
function RequirementsView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ service_type: "manpower", priority: "medium", billing_basis: "day", lines: [{ skill: "", required_headcount: 1 }] });

  const load = async () => {
    try { setRows((await api.get("/hr3/manpower-requirements")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    try {
      const payload = { ...form, lines: form.lines.filter(l => l.skill && l.required_headcount > 0) };
      if (!payload.project_code) { toast.error("Project code required"); return; }
      if (!payload.lines.length) { toast.error("At least one line required"); return; }
      await api.post("/hr3/manpower-requirements", payload);
      toast.success("Manpower requirement created");
      setOpen(false); setForm({ service_type: "manpower", priority: "medium", billing_basis: "day", lines: [{ skill: "", required_headcount: 1 }] });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const refresh = async (rid) => {
    try {
      await api.post(`/hr3/manpower-requirements/${rid}/refresh`);
      toast.success("Availability refreshed");
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (rid, decision) => {
    try {
      await api.post(`/hr3/manpower-requirements/${rid}/approve`, { decision });
      toast.success(`Requirement ${decision}d`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const setLine = (i, k, v) => {
    const ls = [...form.lines]; ls[i] = { ...ls[i], [k]: v };
    setForm({ ...form, lines: ls });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><ClipboardList className="h-4 w-4" /> Manpower Requirements</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr3-mr-new"><Plus className="h-4 w-4 mr-1" /> New Requirement</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>MR No</TableHead><TableHead>Project</TableHead>
            <TableHead>Client</TableHead><TableHead>Service</TableHead>
            <TableHead>Required</TableHead><TableHead>Available</TableHead>
            <TableHead>Shortage</TableHead><TableHead>Priority</TableHead>
            <TableHead>Approval</TableHead><TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-6">No requirements yet</TableCell></TableRow>
            )}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`mr-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.requirement_no}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                <TableCell>{r.client || "—"}</TableCell>
                <TableCell>{r.service_type}</TableCell>
                <TableCell>{r.total_required || 0}</TableCell>
                <TableCell>{r.total_available || 0}</TableCell>
                <TableCell className={r.total_shortage > 0 ? "text-rose-700 font-semibold" : ""}>{r.total_shortage || 0}</TableCell>
                <TableCell><Badge variant="outline" className="text-xs">{r.priority}</Badge></TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell className="flex gap-1">
                  <Button size="sm" variant="outline" onClick={() => refresh(r.id)} data-testid={`mr-refresh-${r.id}`}><RefreshCw className="h-3 w-3" /></Button>
                  {r.approval_status === "pending" && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve")} data-testid={`mr-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`mr-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New Manpower Requirement</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Project Code"><ProjectSelect value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} valueKey="code" label={null} testid="mr-project" /></Field>
            <Field label="Client"><ClientSelect value={form.client || ""} onChange={v => setForm({ ...form, client: v })} valueKey="name" label={null} /></Field>
            <Field label="Site Location"><Input value={form.site_location || ""} onChange={e => setForm({ ...form, site_location: e.target.value })} /></Field>
            <Field label="Service Type">
              <Select value={form.service_type} onValueChange={v => setForm({ ...form, service_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["scaffolding", "painting", "roof_sheeting", "rope_access", "manpower", "other"].map(s =>
                    <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Work Order No"><Input value={form.work_order_no || ""} onChange={e => setForm({ ...form, work_order_no: e.target.value })} /></Field>
            <Field label="Priority">
              <Select value={form.priority} onValueChange={v => setForm({ ...form, priority: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["low", "medium", "high", "critical"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Expected Start Date"><Input type="date" value={form.expected_start_date || ""} onChange={e => setForm({ ...form, expected_start_date: e.target.value })} /></Field>
            <Field label="Duration (days)"><Input type="number" value={form.expected_duration_days || ""} onChange={e => setForm({ ...form, expected_duration_days: parseInt(e.target.value) || null })} /></Field>
            <Field label="Billing Basis">
              <Select value={form.billing_basis || "day"} onValueChange={v => setForm({ ...form, billing_basis: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["day", "month", "team", "shift", "qty", "lumpsum"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <div className="col-span-2">
              <Label className="text-xs">Remarks</Label>
              <Textarea rows={2} value={form.remarks || ""} onChange={e => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>

          <div className="mt-4 border-t pt-3">
            <div className="flex justify-between items-center mb-2">
              <Label className="text-sm font-semibold">Skill Lines</Label>
              <Button size="sm" variant="outline" onClick={() => setForm({ ...form, lines: [...form.lines, { skill: "", required_headcount: 1 }] })}><Plus className="h-3 w-3 mr-1" /> Line</Button>
            </div>
            {form.lines.map((l, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-end">
                <div className="col-span-4"><Field label="Skill"><Input value={l.skill} onChange={e => setLine(i, "skill", e.target.value)} data-testid={`mr-line-skill-${i}`} /></Field></div>
                <div className="col-span-2"><Field label="Headcount"><Input type="number" value={l.required_headcount} onChange={e => setLine(i, "required_headcount", parseInt(e.target.value) || 0)} data-testid={`mr-line-hc-${i}`} /></Field></div>
                <div className="col-span-2"><Field label="Required Date"><Input type="date" value={l.required_date || ""} onChange={e => setLine(i, "required_date", e.target.value)} /></Field></div>
                <div className="col-span-3"><Field label="Qualification"><Input value={l.qualification || ""} onChange={e => setLine(i, "qualification", e.target.value)} /></Field></div>
                <div className="col-span-1 flex justify-end">
                  {form.lines.length > 1 && <Button size="sm" variant="outline" onClick={() => setForm({ ...form, lines: form.lines.filter((_, j) => j !== i) })}><X className="h-3 w-3" /></Button>}
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} data-testid="mr-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── AVAILABILITY ───────────
function AvailabilityView() {
  const [data, setData] = useState(null);
  const [skill, setSkill] = useState("");
  const load = async () => {
    try {
      const params = skill ? { skill } : {};
      setData((await api.get("/hr3/availability", { params })).data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Users className="h-4 w-4" /> Skill-wise Availability</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="Skill filter" value={skill} onChange={e => setSkill(e.target.value)} className="w-40" data-testid="avail-skill" />
          <Button size="sm" onClick={load} data-testid="avail-apply"><Filter className="h-4 w-4 mr-1" /> Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        {!data?.rows?.length && <div className="text-sm text-muted-foreground py-4 text-center">No skill data. Workers/employees need `skill_name` or `designation` set.</div>}
        {!!data?.rows?.length && (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Skill / Trade</TableHead><TableHead>Active</TableHead>
              <TableHead>Deployed</TableHead><TableHead>Available</TableHead>
              <TableHead>Docs Block</TableHead><TableHead>Medical Block</TableHead>
              <TableHead>Safety Block</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.rows.map(r => (
                <TableRow key={r.skill} data-testid={`avail-row-${r.skill}`}>
                  <TableCell className="font-medium">{r.skill}</TableCell>
                  <TableCell>{r.total_active}</TableCell>
                  <TableCell>{r.currently_deployed}</TableCell>
                  <TableCell className="text-emerald-700 font-semibold">{r.available}</TableCell>
                  <TableCell className="text-rose-700">{r.blocked_documents}</TableCell>
                  <TableCell className="text-rose-700">{r.blocked_medical}</TableCell>
                  <TableCell className="text-rose-700">{r.blocked_safety}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────── DEPLOYMENTS ───────────
function DeploymentsView() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ person_type: "employee", service_type: "manpower", deployment_start_date: today(), ppe_required: true });
  const create = async () => {
    try {
      if (!form.project_code) { toast.error("project_code required"); return; }
      if (!form.person_id) { toast.error("person_id required"); return; }
      const r = await api.post("/hr3/deployments", form);
      toast.success(`Deployment ${r.data.deployment_no} created`);
      setOpen(false);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Briefcase className="h-4 w-4" /> Deployments</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr3-dep-new"><Plus className="h-4 w-4 mr-1" /> New Deployment</Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">Use the existing <a href="/app/deployments" className="underline">Deployments register</a> to view, filter and manage all deployment records (same data, same `deployments` collection). New deployments created here run the full HR-Phase-3 validation chain (active-deployment guard, medical/safety/document checks, allow_multi_site override).</p>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New Deployment (Phase 3 — full compliance checks)</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Person Type">
              <Select value={form.person_type} onValueChange={v => setForm({ ...form, person_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="employee">Employee</SelectItem>
                  <SelectItem value="worker">Worker</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Person ID (employee/worker.id)"><Input value={form.person_id || ""} onChange={e => setForm({ ...form, person_id: e.target.value })} data-testid="dep-pid" /></Field>
            <Field label="Employee Code"><Input value={form.employee_code || ""} onChange={e => setForm({ ...form, employee_code: e.target.value })} /></Field>
            <Field label="Project Code"><ProjectSelect value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} valueKey="code" label={null} testid="dep-project" /></Field>
            <Field label="Client"><ClientSelect value={form.client || ""} onChange={v => setForm({ ...form, client: v })} valueKey="name" label={null} /></Field>
            <Field label="Site Location"><Input value={form.site_location || ""} onChange={e => setForm({ ...form, site_location: e.target.value })} /></Field>
            <Field label="Service Type">
              <Select value={form.service_type} onValueChange={v => setForm({ ...form, service_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["scaffolding", "painting", "roof_sheeting", "rope_access", "manpower", "other"].map(s =>
                    <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Skill / Trade"><Input value={form.skill || ""} onChange={e => setForm({ ...form, skill: e.target.value })} /></Field>
            <Field label="Start Date"><Input type="date" value={form.deployment_start_date} onChange={e => setForm({ ...form, deployment_start_date: e.target.value })} /></Field>
            <Field label="Expected End Date"><Input type="date" value={form.expected_end_date || ""} onChange={e => setForm({ ...form, expected_end_date: e.target.value })} /></Field>
            <Field label="Reporting Person"><Input value={form.reporting_person || ""} onChange={e => setForm({ ...form, reporting_person: e.target.value })} /></Field>
            <Field label="Multi-Site Allowed?">
              <Select value={String(form.allow_multi_site || false)} onValueChange={v => setForm({ ...form, allow_multi_site: v === "true" })}>
                <SelectTrigger data-testid="dep-allow_multi_site"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="false">No</SelectItem>
                  <SelectItem value="true">Yes</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div className="col-span-2 grid grid-cols-4 gap-2">
              {["accommodation_required", "travel_required", "ppe_required", "tool_required"].map(k => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form[k]} onChange={e => setForm({ ...form, [k]: e.target.checked })} data-testid={`dep-${k}`} />
                  {k.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} data-testid="dep-save-btn">Create Deployment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── MOBILIZATION ───────────
function MobilizationsView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ travel_required: false, accommodation_required: false, ppe_required: true });

  const load = async () => {
    try { setRows((await api.get("/hr3/mobilizations")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/hr3/mobilizations", form);
      toast.success("Mobilization created");
      setOpen(false); setForm({ travel_required: false, accommodation_required: false, ppe_required: true });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const updateSec = async (mid, section, status) => {
    try {
      await api.post(`/hr3/mobilizations/${mid}/section`, { section, status });
      toast.success(`${section} → ${status}`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const close = async (mid) => {
    try {
      await api.post(`/hr3/mobilizations/${mid}/close`);
      toast.success("Mobilization closed");
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><ArrowRightLeft className="h-4 w-4" /> Mobilizations</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr3-mob-new"><Plus className="h-4 w-4 mr-1" /> New Mobilization</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>MOB No</TableHead><TableHead>Deployment</TableHead>
            <TableHead>Employee</TableHead><TableHead>Project</TableHead>
            <TableHead>Logistics</TableHead><TableHead>Store</TableHead>
            <TableHead>Safety</TableHead><TableHead>Status</TableHead>
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-6">No mobilizations</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`mob-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.mobilization_no}</TableCell>
                <TableCell className="font-mono text-xs">{r.deployment_no}</TableCell>
                <TableCell>{r.employee_name}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                <TableCell>
                  <Select value={r.logistics_status || "pending"} onValueChange={v => updateSec(r.id, "logistics", v)}>
                    <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>{["pending", "in_progress", "ok", "failed", "not_required"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Select value={r.store_status || "pending"} onValueChange={v => updateSec(r.id, "store", v)}>
                    <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>{["pending", "in_progress", "ok", "failed", "not_required"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Select value={r.safety_status || "pending"} onValueChange={v => updateSec(r.id, "safety", v)}>
                    <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>{["pending", "in_progress", "ok", "failed", "not_required"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </TableCell>
                <TableCell><StatusBadge value={r.status} /></TableCell>
                <TableCell>
                  {r.status === "open" && <Button size="sm" variant="outline" onClick={() => close(r.id)} data-testid={`mob-close-${r.id}`}>Close</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Mobilization</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Field label="Deployment ID"><Input value={form.deployment_id || ""} onChange={e => setForm({ ...form, deployment_id: e.target.value })} data-testid="mob-dep-id" /></Field></div>
            <Field label="Travel Date"><Input type="date" value={form.travel_date || ""} onChange={e => setForm({ ...form, travel_date: e.target.value })} /></Field>
            <Field label="Reporting Date"><Input type="date" value={form.reporting_date || ""} onChange={e => setForm({ ...form, reporting_date: e.target.value })} /></Field>
            <div className="col-span-2 grid grid-cols-4 gap-2">
              {["travel_required", "accommodation_required", "ppe_required", "tool_required"].map(k => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form[k]} onChange={e => setForm({ ...form, [k]: e.target.checked })} />
                  {k.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} data-testid="mob-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── DEMOBILIZATION ───────────
function DemobilizationsView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ ppe_return_required: true });

  const load = async () => {
    try { setRows((await api.get("/hr3/demobilizations")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/hr3/demobilizations", form);
      toast.success("Demobilization initiated");
      setOpen(false); setForm({ ppe_return_required: true });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const setClear = async (did, section, status) => {
    try {
      await api.post(`/hr3/demobilizations/${did}/clearance`, { section, status });
      toast.success(`${section} → ${status}`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const close = async (did) => {
    try {
      await api.post(`/hr3/demobilizations/${did}/close`);
      toast.success("Demob closed; worker available");
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><MapPin className="h-4 w-4" /> Demobilizations</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr3-demob-new"><Plus className="h-4 w-4 mr-1" /> New Demobilization</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>DMB No</TableHead><TableHead>Employee</TableHead>
            <TableHead>Project</TableHead><TableHead>Store</TableHead>
            <TableHead>Safety</TableHead><TableHead>Project</TableHead>
            <TableHead>HR</TableHead><TableHead>Logistics</TableHead>
            <TableHead>Status</TableHead><TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-6">No demobilizations</TableCell></TableRow>}
            {rows.map(r => {
              const cell = (sec, val) => (
                <TableCell>
                  <Select value={val || "pending"} onValueChange={v => setClear(r.id, sec, v)}>
                    <SelectTrigger className="h-7 text-xs w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>{["pending", "in_progress", "ok", "failed", "not_required"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </TableCell>
              );
              return (
                <TableRow key={r.id} data-testid={`demob-row-${r.id}`}>
                  <TableCell className="font-mono text-xs">{r.demobilization_no}</TableCell>
                  <TableCell>{r.employee_name}</TableCell>
                  <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                  {cell("store", r.store_clearance)}
                  {cell("safety", r.safety_clearance)}
                  {cell("project", r.project_clearance)}
                  {cell("hr", r.hr_clearance)}
                  {cell("logistics", r.logistics_status)}
                  <TableCell><StatusBadge value={r.status} /></TableCell>
                  <TableCell>
                    {r.status === "open" && <Button size="sm" variant="outline" onClick={() => close(r.id)} data-testid={`demob-close-${r.id}`}>Close</Button>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Demobilization</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Field label="Deployment ID"><Input value={form.deployment_id || ""} onChange={e => setForm({ ...form, deployment_id: e.target.value })} data-testid="demob-dep-id" /></Field></div>
            <Field label="Demob Date"><Input type="date" value={form.demobilization_date || ""} onChange={e => setForm({ ...form, demobilization_date: e.target.value })} /></Field>
            <Field label="Reason"><Input value={form.reason || ""} onChange={e => setForm({ ...form, reason: e.target.value })} data-testid="demob-reason" /></Field>
            <div className="col-span-2 grid grid-cols-3 gap-2">
              {["return_travel_required", "ppe_return_required", "tool_return_required"].map(k => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form[k]} onChange={e => setForm({ ...form, [k]: e.target.checked })} />
                  {k.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} data-testid="demob-save-btn">Initiate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── REPLACEMENTS ───────────
function ReplacementsView() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ urgency: "medium" });

  const load = async () => {
    try { setRows((await api.get("/hr3/replacements")).data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/hr3/replacements", form);
      toast.success("Replacement request created");
      setOpen(false); setForm({ urgency: "medium" });
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const decide = async (rid, decision) => {
    try {
      await api.post(`/hr3/replacements/${rid}/approve`, { decision });
      toast.success(`Replacement ${decision}d`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><RefreshCw className="h-4 w-4" /> Replacement Requests</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="hr3-rep-new"><Plus className="h-4 w-4 mr-1" /> New Request</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>REP No</TableHead><TableHead>Project</TableHead>
            <TableHead>Existing</TableHead><TableHead>Required Skill</TableHead>
            <TableHead>Urgency</TableHead><TableHead>Approval</TableHead>
            <TableHead></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">No replacement requests</TableCell></TableRow>}
            {rows.map(r => (
              <TableRow key={r.id} data-testid={`rep-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.replacement_no}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                <TableCell>{r.existing_employee_id}</TableCell>
                <TableCell>{r.required_skill}</TableCell>
                <TableCell><Badge variant="outline" className="text-xs">{r.urgency}</Badge></TableCell>
                <TableCell><StatusBadge value={r.approval_status} /></TableCell>
                <TableCell className="flex gap-1">
                  {r.approval_status === "pending" && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "approve")} data-testid={`rep-approve-${r.id}`}><Check className="h-3 w-3" /></Button>
                      <Button size="sm" variant="outline" onClick={() => decide(r.id, "reject")} data-testid={`rep-reject-${r.id}`}><X className="h-3 w-3" /></Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Replacement Request</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Project Code"><ProjectSelect value={form.project_code || ""} onChange={v => setForm({ ...form, project_code: v })} valueKey="code" label={null} testid="rep-project" /></Field>
            <Field label="Site Location"><Input value={form.site_location || ""} onChange={e => setForm({ ...form, site_location: e.target.value })} /></Field>
            <Field label="Existing Employee ID"><Input value={form.existing_employee_id || ""} onChange={e => setForm({ ...form, existing_employee_id: e.target.value })} data-testid="rep-existing" /></Field>
            <Field label="Existing Deployment ID"><Input value={form.existing_deployment_id || ""} onChange={e => setForm({ ...form, existing_deployment_id: e.target.value })} /></Field>
            <Field label="Required Skill"><Input value={form.required_skill || ""} onChange={e => setForm({ ...form, required_skill: e.target.value })} data-testid="rep-skill" /></Field>
            <Field label="Required Date"><Input type="date" value={form.required_date || ""} onChange={e => setForm({ ...form, required_date: e.target.value })} /></Field>
            <Field label="Urgency">
              <Select value={form.urgency} onValueChange={v => setForm({ ...form, urgency: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["low", "medium", "high", "critical"].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Suggested Replacement ID"><Input value={form.suggested_replacement_id || ""} onChange={e => setForm({ ...form, suggested_replacement_id: e.target.value })} /></Field>
            <div className="col-span-2">
              <Label className="text-xs">Reason</Label>
              <Textarea rows={2} value={form.reason || ""} onChange={e => setForm({ ...form, reason: e.target.value })} data-testid="rep-reason" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} data-testid="rep-save-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─────────── PROJECT / SITE ROLLUPS ───────────
function RollupsView() {
  const [proj, setProj] = useState([]);
  const [site, setSite] = useState([]);
  const [shortage, setShortage] = useState([]);
  useEffect(() => { (async () => {
    try {
      const [p, s, sh] = await Promise.all([
        api.get("/hr3/project-manpower"),
        api.get("/hr3/site-manpower"),
        api.get("/hr3/shortage-report"),
      ]);
      setProj(p.data || []); setSite(s.data || []); setShortage(sh.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  })(); }, []);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Briefcase className="h-4 w-4" /> Project-wise Manpower</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Project</TableHead><TableHead>Skill</TableHead>
              <TableHead>Total</TableHead><TableHead>Active</TableHead>
              <TableHead>Mobilized</TableHead><TableHead>Planned</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {proj.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-4">No active deployments</TableCell></TableRow>}
              {proj.map((r, i) => (
                <TableRow key={`${r.project_code}-${r.skill}-${i}`} data-testid={`proj-row-${i}`}>
                  <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                  <TableCell>{r.skill || "—"}</TableCell>
                  <TableCell>{r.total}</TableCell>
                  <TableCell>{r.active}</TableCell>
                  <TableCell>{r.mobilized}</TableCell>
                  <TableCell>{r.planned}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><MapPin className="h-4 w-4" /> Site-wise Manpower</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow><TableHead>Site</TableHead><TableHead>Project</TableHead><TableHead>Headcount</TableHead></TableRow></TableHeader>
            <TableBody>
              {site.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-sm text-muted-foreground py-4">No data</TableCell></TableRow>}
              {site.map((r, i) => (
                <TableRow key={i} data-testid={`site-row-${i}`}>
                  <TableCell>{r.site_location || "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                  <TableCell>{r.headcount}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-rose-600" /> Manpower Shortage Report</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow>
              <TableHead>MR No</TableHead><TableHead>Project</TableHead>
              <TableHead>Required</TableHead><TableHead>Available</TableHead><TableHead>Shortage</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {shortage.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-4">No shortage</TableCell></TableRow>}
              {shortage.map(r => (
                <TableRow key={r.id} data-testid={`shortage-row-${r.id}`}>
                  <TableCell className="font-mono text-xs">{r.requirement_no}</TableCell>
                  <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                  <TableCell>{r.total_required}</TableCell>
                  <TableCell>{r.total_available}</TableCell>
                  <TableCell className="text-rose-700 font-semibold">{r.total_shortage}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────── DEPLOYMENT CALENDAR ───────────
function CalendarView() {
  const fromD = (() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  })();
  const toD = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 60);
    return d.toISOString().slice(0, 10);
  })();
  const [from_date, setFrom] = useState(fromD);
  const [to_date, setTo] = useState(toD);
  const [rows, setRows] = useState([]);
  const load = async () => {
    try {
      const r = await api.get("/hr3/deployment-calendar", { params: { from_date, to_date } });
      setRows(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);  // eslint-disable-line
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-sm flex items-center gap-2"><Calendar className="h-4 w-4" /> Deployment Calendar</CardTitle>
        <div className="flex gap-2">
          <Input type="date" value={from_date} onChange={e => setFrom(e.target.value)} className="w-36" />
          <Input type="date" value={to_date} onChange={e => setTo(e.target.value)} className="w-36" />
          <Button size="sm" onClick={load} data-testid="cal-apply"><Filter className="h-4 w-4 mr-1" /> Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Deployment</TableHead><TableHead>Employee</TableHead>
            <TableHead>Project</TableHead><TableHead>Site</TableHead>
            <TableHead>Skill</TableHead><TableHead>Start</TableHead>
            <TableHead>End</TableHead><TableHead>Status</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-6">No deployments in range</TableCell></TableRow>}
            {rows.map((r, i) => (
              <TableRow key={`${r.deployment_no}-${i}`} data-testid={`cal-row-${i}`}>
                <TableCell className="font-mono text-xs">{r.deployment_no}</TableCell>
                <TableCell>{r.employee}</TableCell>
                <TableCell className="font-mono text-xs">{r.project_code}</TableCell>
                <TableCell>{r.site_location}</TableCell>
                <TableCell>{r.skill}</TableCell>
                <TableCell>{r.start}</TableCell>
                <TableCell>{r.end || "—"}</TableCell>
                <TableCell><StatusBadge value={r.status} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─────────── PARENT HUB ───────────
export default function HrPhase3() {
  const [tab, setTab] = useState("dashboard");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Activity className="h-5 w-5" /> Manpower Planning · Deployment · Mobilization
        </h1>
        <p className="text-sm text-muted-foreground">Phase 3 — Sales→HR manpower planning, smart deployment workflow, mobilization &amp; demobilization clearances</p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="dashboard" data-testid="hr3-tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="requirements" data-testid="hr3-tab-requirements">Requirements</TabsTrigger>
          <TabsTrigger value="availability" data-testid="hr3-tab-availability">Availability</TabsTrigger>
          <TabsTrigger value="deployments" data-testid="hr3-tab-deployments">Deployment</TabsTrigger>
          <TabsTrigger value="mobilization" data-testid="hr3-tab-mobilization">Mobilization</TabsTrigger>
          <TabsTrigger value="demobilization" data-testid="hr3-tab-demobilization">Demobilization</TabsTrigger>
          <TabsTrigger value="replacement" data-testid="hr3-tab-replacement">Replacement</TabsTrigger>
          <TabsTrigger value="rollups" data-testid="hr3-tab-rollups">Project/Site</TabsTrigger>
          <TabsTrigger value="calendar" data-testid="hr3-tab-calendar">Calendar</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><DashboardView /></TabsContent>
        <TabsContent value="requirements"><RequirementsView /></TabsContent>
        <TabsContent value="availability"><AvailabilityView /></TabsContent>
        <TabsContent value="deployments"><DeploymentsView /></TabsContent>
        <TabsContent value="mobilization"><MobilizationsView /></TabsContent>
        <TabsContent value="demobilization"><DemobilizationsView /></TabsContent>
        <TabsContent value="replacement"><ReplacementsView /></TabsContent>
        <TabsContent value="rollups"><RollupsView /></TabsContent>
        <TabsContent value="calendar"><CalendarView /></TabsContent>
      </Tabs>
    </div>
  );
}
