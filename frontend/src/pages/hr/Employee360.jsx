import { useEffect, useMemo, useState } from "react";
import {
  User, Award, Shield, MapPinned, Clock, Wallet, FolderArchive,
  Search, Plus, Trash2, CalendarDays, BadgeCheck, AlertTriangle, ScrollText,
  Upload, ScanLine, FileCheck2, CheckCircle2, XCircle, MinusCircle, Loader2, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { api, apiErrorMessage, stripEmpty, API } from "@/lib/api";
import { toast } from "sonner";

const LEVELS = ["beginner", "intermediate", "expert"];
const EXP_TONE = {
  expired: "bg-red-100 text-red-900 border-red-300",
  expiring_soon: "bg-amber-100 text-amber-900 border-amber-300",
  valid: "bg-emerald-100 text-emerald-900 border-emerald-300",
  unknown: "bg-secondary text-muted-foreground border-border",
};

export default function Employee360() {
  const [employees, setEmployees] = useState([]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("personal");
  const [skillForm, setSkillForm] = useState({ skill: "", level: "intermediate", years: 0, notes: "" });
  const [skillOpen, setSkillOpen] = useState(false);
  const [certForm, setCertForm] = useState({ name: "", issuer: "", issue_date: "", expiry_date: "", cert_no: "", notes: "" });
  const [certOpen, setCertOpen] = useState(false);

  // Documents
  const [docTypes, setDocTypes] = useState([]);
  const [docs, setDocs] = useState([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ doc_type: "aadhaar", label: "", file: null });
  const [scanning, setScanning] = useState({});

  useEffect(() => {
    api.get("/hr/document-types").then((r) => setDocTypes(r.data || [])).catch(() => {});
  }, []);

  const loadDocs = async (eid) => {
    try {
      const r = await api.get(`/hr/employees/${eid}/documents`);
      setDocs(r.data || []);
    } catch (e) { /* silent */ }
  };

  const loadEmps = async () => {
    try {
      const r = await api.get("/employees");
      setEmployees(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e, "Load employees failed")); }
  };
  useEffect(() => { loadEmps(); }, []);

  const filtered = useMemo(() => {
    if (!q.trim()) return employees;
    const s = q.toLowerCase();
    return employees.filter((e) =>
      [e.name, e.emp_code, e.department, e.role, e.email].some((v) => (v || "").toLowerCase().includes(s))
    );
  }, [employees, q]);

  const load360 = async (emp) => {
    setSelected(emp);
    setData(null);
    try {
      const r = await api.get(`/hr/employee-360/${emp.id}`);
      setData(r.data);
      loadDocs(emp.id);
    } catch (e) { toast.error(apiErrorMessage(e, "Load 360 failed")); }
  };

  const uploadDoc = async () => {
    if (!uploadForm.file) { toast.error("Pick a file"); return; }
    const fd = new FormData();
    fd.append("file", uploadForm.file);
    fd.append("doc_type", uploadForm.doc_type);
    fd.append("label", uploadForm.label);
    try {
      await api.post(`/hr/employees/${selected.id}/documents`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document uploaded");
      setUploadOpen(false);
      setUploadForm({ doc_type: "aadhaar", label: "", file: null });
      loadDocs(selected.id);
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Upload failed")); }
  };

  const scanDoc = async (doc_id) => {
    setScanning((s) => ({ ...s, [doc_id]: true }));
    try {
      const r = await api.post(`/hr/employees/${selected.id}/documents/${doc_id}/scan`, { apply_autofill: true });
      const v = r.data?.verification;
      const counts = v?.counts || {};
      const auto = Object.keys(r.data?.autofill_applied || {});
      toast.success(
        `Scanned. ${counts.match || 0} match · ${counts.mismatch || 0} mismatch` +
        (auto.length ? ` · auto-filled: ${auto.join(", ")}` : "")
      );
      loadDocs(selected.id);
      load360(selected);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Scan failed"));
    } finally {
      setScanning((s) => { const n = { ...s }; delete n[doc_id]; return n; });
    }
  };

  const deleteDoc = async (doc_id) => {
    if (!window.confirm("Delete this document?")) return;
    try {
      await api.delete(`/hr/employees/${selected.id}/documents/${doc_id}`);
      toast.success("Deleted");
      loadDocs(selected.id);
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  const addSkill = async () => {
    if (!skillForm.skill.trim()) { toast.error("Skill name required"); return; }
    try {
      await api.post(`/hr/employees/${selected.id}/skills`, skillForm);
      toast.success("Skill added"); setSkillOpen(false);
      setSkillForm({ skill: "", level: "intermediate", years: 0, notes: "" });
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Add skill failed")); }
  };
  const removeSkill = async (sid) => {
    if (!window.confirm("Remove this skill?")) return;
    try {
      await api.delete(`/hr/employees/${selected.id}/skills/${sid}`);
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  const addCert = async () => {
    if (!certForm.name.trim()) { toast.error("Cert name required"); return; }
    try {
      await api.post(`/hr/employees/${selected.id}/certifications`, certForm);
      toast.success("Certification added"); setCertOpen(false);
      setCertForm({ name: "", issuer: "", issue_date: "", expiry_date: "", cert_no: "", notes: "" });
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Add cert failed")); }
  };
  const removeCert = async (cid) => {
    if (!window.confirm("Remove this certification?")) return;
    try {
      await api.delete(`/hr/employees/${selected.id}/certifications/${cid}`);
      load360(selected);
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  if (!selected) {
    return (
      <div className="space-y-6" data-testid="hr-emp360-page">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <User className="h-3 w-3" /> Human Resources
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Employee 360</h1>
          <p className="text-sm text-muted-foreground mt-1">Pick an employee to see their unified profile — skills, certs, PPE, trainings, deployments, attendance, payroll and documents.</p>
        </div>
        <div className="bg-card border border-border rounded-sm">
          <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
            <div className="relative w-72">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9 h-9 rounded-sm" placeholder="Search by name, code, dept…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="emp360-search" />
            </div>
            <span className="text-[11px] text-muted-foreground">{filtered.length} of {employees.length}</span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((e) => (
                <TableRow key={e.id} data-testid={`emp360-row-${e.id}`}>
                  <TableCell className="font-mono text-[11px]">{e.emp_code}</TableCell>
                  <TableCell className="font-semibold">{e.name}</TableCell>
                  <TableCell>{e.role}</TableCell>
                  <TableCell>{e.department}</TableCell>
                  <TableCell>
                    {e.status === "active"
                      ? <Badge className="bg-emerald-100 text-emerald-900 border-emerald-300 rounded-sm">Active</Badge>
                      : <Badge variant="outline" className="rounded-sm">{e.status}</Badge>}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => load360(e)} data-testid={`emp360-open-${e.id}`}>
                      View 360
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    );
  }

  const p = data?.personal;

  return (
    <div className="space-y-6" data-testid="hr-emp360-detail">
      <div className="flex items-start gap-4">
        <Button variant="outline" className="rounded-sm h-9" onClick={() => { setSelected(null); setData(null); }} data-testid="emp360-back">← Back</Button>
        <div className="flex-1">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1 flex items-center gap-2">
            <User className="h-3 w-3" /> Employee 360 · <span className="font-mono">{p?.emp_code}</span>
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">{p?.name || "—"}</h1>
          <div className="text-sm text-muted-foreground mt-1 flex items-center gap-2 flex-wrap">
            <span>{p?.designation || p?.role} · {p?.department || "—"} · Joined {p?.joining_date || "—"}</span>
            {p?.verification_status === "verified" && (
              <Badge className="rounded-sm border bg-emerald-100 text-emerald-900 border-emerald-300">
                <ShieldCheck className="h-3 w-3 mr-1 inline" /> KYC Verified
              </Badge>
            )}
            {p?.verification_status === "pending" && (
              <Badge className="rounded-sm border bg-amber-100 text-amber-900 border-amber-300">
                <AlertTriangle className="h-3 w-3 mr-1 inline" /> Verification Pending
              </Badge>
            )}
          </div>
        </div>
      </div>

      {data && (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="rounded-sm">
            <TabsTrigger value="personal" data-testid="emp360-tab-personal"><User className="h-3.5 w-3.5 mr-1" />Personal</TabsTrigger>
            <TabsTrigger value="skills" data-testid="emp360-tab-skills"><Award className="h-3.5 w-3.5 mr-1" />Skills & Certs</TabsTrigger>
            <TabsTrigger value="ppe" data-testid="emp360-tab-ppe"><Shield className="h-3.5 w-3.5 mr-1" />PPE & Training</TabsTrigger>
            <TabsTrigger value="deployments" data-testid="emp360-tab-deployments"><MapPinned className="h-3.5 w-3.5 mr-1" />Deployments</TabsTrigger>
            <TabsTrigger value="attendance" data-testid="emp360-tab-attendance"><Clock className="h-3.5 w-3.5 mr-1" />Attendance & Leave</TabsTrigger>
            <TabsTrigger value="payroll" data-testid="emp360-tab-payroll"><Wallet className="h-3.5 w-3.5 mr-1" />Payroll</TabsTrigger>
            <TabsTrigger value="docs" data-testid="emp360-tab-docs"><FolderArchive className="h-3.5 w-3.5 mr-1" />Documents</TabsTrigger>
          </TabsList>

          <TabsContent value="personal" className="mt-4">
            <Card>
              <KV label="Name" value={p?.name} />
              <KV label="Code" value={p?.emp_code} />
              <KV label="Role" value={p?.role} />
              <KV label="Department" value={p?.department} />
              <KV label="Designation" value={p?.designation} />
              <KV label="Joining" value={p?.joining_date} />
              <KV label="Email" value={p?.email} />
              <KV label="Phone" value={p?.phone} />
              <KV label="Salary" value={p?.salary ? `₹ ${Number(p.salary).toLocaleString("en-IN")}` : "—"} />
              <KV label="Status" value={p?.status} />
            </Card>
          </TabsContent>

          <TabsContent value="skills" className="mt-4 space-y-4">
            <Section title="Skills" icon={Award} onAdd={() => setSkillOpen(true)} addTestid="emp360-skill-add">
              {(data.skills || []).length === 0 && <Empty text="No skills recorded." />}
              <div className="flex flex-wrap gap-2">
                {(data.skills || []).map((s) => (
                  <div key={s.id} className="bg-secondary/40 border border-border rounded-sm px-3 py-2 flex items-center gap-2 group">
                    <BadgeCheck className="h-4 w-4 text-primary" />
                    <div>
                      <div className="text-sm font-semibold">{s.skill}</div>
                      <div className="text-[11px] text-muted-foreground">{s.level}{s.years ? ` · ${s.years}y` : ""}</div>
                    </div>
                    <button onClick={() => removeSkill(s.id)} className="opacity-0 group-hover:opacity-100 text-destructive" data-testid={`emp360-skill-del-${s.id}`}>
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </Section>

            <Section title="Certifications" icon={ScrollText} onAdd={() => setCertOpen(true)} addTestid="emp360-cert-add">
              {(data.certifications || []).length === 0 && <Empty text="No certifications." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Name</TableHead><TableHead>Issuer</TableHead><TableHead>Issue</TableHead>
                  <TableHead>Expiry</TableHead><TableHead>Status</TableHead><TableHead></TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.certifications || []).map((c) => (
                    <TableRow key={c.id} data-testid={`emp360-cert-row-${c.id}`}>
                      <TableCell className="font-semibold">{c.name}</TableCell>
                      <TableCell className="text-[12px]">{c.issuer || "—"}</TableCell>
                      <TableCell className="text-[12px]">{c.issue_date || "—"}</TableCell>
                      <TableCell className="text-[12px]">{c.expiry_date || "—"}</TableCell>
                      <TableCell>
                        <Badge className={`rounded-sm border ${EXP_TONE[c.expiry_status]}`}>
                          {c.expiry_status === "expiring_soon" ? <AlertTriangle className="h-3 w-3 mr-1 inline" /> : null}
                          {c.expiry_status === "valid" ? `${c.expires_in_days}d left` : c.expiry_status.replace("_", " ")}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => removeCert(c.id)} data-testid={`emp360-cert-del-${c.id}`}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </TabsContent>

          <TabsContent value="ppe" className="mt-4 space-y-4">
            <Section title="PPE Issuance History" icon={Shield}>
              {(data.ppe_history || []).length === 0 && <Empty text="No PPE records." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Issue #</TableHead><TableHead>Date</TableHead><TableHead>Items</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.ppe_history || []).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-mono text-[11px]">{r.issue_no}</TableCell>
                      <TableCell className="text-[12px]">{r.issue_date}</TableCell>
                      <TableCell className="text-[12px]">{(r.items || []).map((it) => `${it.item} × ${it.qty}`).join(", ")}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm">{r.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>

            <Section title="Trainings & Toolbox Talks" icon={Award}>
              {(data.trainings || []).length === 0 && <Empty text="No training records." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Title</TableHead><TableHead>Type</TableHead><TableHead>Date</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.trainings || []).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-semibold">{r.title || r.topic || "—"}</TableCell>
                      <TableCell className="text-[12px]">{r.type || "toolbox_talk"}</TableCell>
                      <TableCell className="text-[12px]">{r.scheduled_date || r.talk_date || "—"}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm">{r.status || "done"}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </TabsContent>

          <TabsContent value="deployments" className="mt-4">
            <Section title="Site Deployments" icon={MapPinned}>
              {(data.deployments || []).length === 0 && <Empty text="No deployment history." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Project</TableHead><TableHead>Site</TableHead><TableHead>From</TableHead><TableHead>To</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.deployments || []).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.project || r.project_name || "—"}</TableCell>
                      <TableCell className="text-[12px]">{r.site || r.site_name || "—"}</TableCell>
                      <TableCell className="text-[12px]">{r.from_date || r.start_date || "—"}</TableCell>
                      <TableCell className="text-[12px]">{r.to_date || r.end_date || "—"}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm">{r.status || "—"}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </TabsContent>

          <TabsContent value="attendance" className="mt-4 space-y-4">
            <Section title="Attendance Summary — Last 30 Days" icon={Clock}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatBox label="Present" value={data.attendance_30d?.present || 0} tone="emerald" />
                <StatBox label="Absent" value={data.attendance_30d?.absent || 0} tone="red" />
                <StatBox label="On Leave" value={data.attendance_30d?.leave || 0} tone="amber" />
                <StatBox label="Total Hours" value={Math.round(data.attendance_30d?.total_hours || 0)} tone="blue" />
              </div>
            </Section>

            <Section title="Leave Balances" icon={CalendarDays}>
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Type</TableHead><TableHead className="text-right">Granted</TableHead>
                  <TableHead className="text-right">Used</TableHead><TableHead className="text-right">Balance</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.leave_balances || []).map((b) => (
                    <TableRow key={b.id}>
                      <TableCell><Badge variant="outline" className="rounded-sm font-mono">{b.leave_type}</Badge> {b.leave_type_label}</TableCell>
                      <TableCell className="text-right tabular">{b.granted}</TableCell>
                      <TableCell className="text-right tabular">{b.used}</TableCell>
                      <TableCell className="text-right tabular font-bold">{b.balance}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>

            <Section title="Recent Leaves" icon={CalendarDays}>
              {(data.recent_leaves || []).length === 0 && <Empty text="No leave applications." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Type</TableHead><TableHead>From</TableHead><TableHead>To</TableHead>
                  <TableHead className="text-right">Days</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.recent_leaves || []).map((l) => (
                    <TableRow key={l.id}>
                      <TableCell className="font-mono text-[11px]">{l.leave_type}</TableCell>
                      <TableCell className="text-[12px]">{l.from_date}</TableCell>
                      <TableCell className="text-[12px]">{l.to_date}</TableCell>
                      <TableCell className="text-right tabular">{l.days}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm">{l.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </TabsContent>

          <TabsContent value="payroll" className="mt-4">
            <Section title="Payroll — Last 3 Months" icon={Wallet}>
              {(data.payroll || []).length === 0 && <Empty text="No payroll records." />}
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Month</TableHead><TableHead className="text-right">Gross</TableHead>
                  <TableHead className="text-right">Deductions</TableHead><TableHead className="text-right">Net</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(data.payroll || []).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.month}</TableCell>
                      <TableCell className="text-right tabular">{Number(r.gross || 0).toLocaleString("en-IN")}</TableCell>
                      <TableCell className="text-right tabular">{Number(r.deductions || 0).toLocaleString("en-IN")}</TableCell>
                      <TableCell className="text-right tabular font-bold">{Number(r.net || 0).toLocaleString("en-IN")}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm">{r.status || "—"}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </TabsContent>

          <TabsContent value="docs" className="mt-4 space-y-4">
            <Section title="Documents · AI-Scanned KYC" icon={FolderArchive} onAdd={() => setUploadOpen(true)} addTestid="emp360-doc-upload">
              {(docs || []).length === 0 && <Empty text="No documents uploaded. Click + Add to upload Aadhaar / PAN / Bank / certs." />}
              {(docs || []).length > 0 && (
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Document</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Scan</TableHead>
                    <TableHead>Verification</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {docs.map((f) => (
                      <DocumentRow
                        key={f.id}
                        row={f}
                        scanning={!!scanning[f.id]}
                        onScan={() => scanDoc(f.id)}
                        onDelete={() => deleteDoc(f.id)}
                      />
                    ))}
                  </TableBody>
                </Table>
              )}
            </Section>
          </TabsContent>
        </Tabs>
      )}

      {/* Skill add */}
      <Dialog open={skillOpen} onOpenChange={setSkillOpen}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Award className="h-4 w-4 text-primary" /> Add Skill</DialogTitle>
            <DialogDescription>Capture a technical or soft skill.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Field label="Skill *" value={skillForm.skill} onChange={(v) => setSkillForm({ ...skillForm, skill: v })} testid="skill-form-name" />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Level</Label>
                <Select value={skillForm.level} onValueChange={(v) => setSkillForm({ ...skillForm, level: v })}>
                  <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="skill-form-level"><SelectValue /></SelectTrigger>
                  <SelectContent>{LEVELS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <Field label="Years" type="number" value={skillForm.years} onChange={(v) => setSkillForm({ ...skillForm, years: Number(v) })} testid="skill-form-years" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Notes</Label>
              <Textarea value={skillForm.notes} onChange={(e) => setSkillForm({ ...skillForm, notes: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="skill-form-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setSkillOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={addSkill} data-testid="skill-form-save">Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cert add */}
      <Dialog open={certOpen} onOpenChange={setCertOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><ScrollText className="h-4 w-4 text-primary" /> Add Certification</DialogTitle>
            <DialogDescription>Track license / certification with expiry alert.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Field label="Name *" value={certForm.name} onChange={(v) => setCertForm({ ...certForm, name: v })} testid="cert-form-name" />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Issuer" value={certForm.issuer} onChange={(v) => setCertForm({ ...certForm, issuer: v })} testid="cert-form-issuer" />
              <Field label="Cert #" value={certForm.cert_no} onChange={(v) => setCertForm({ ...certForm, cert_no: v })} testid="cert-form-no" />
              <Field label="Issue Date" type="date" value={certForm.issue_date} onChange={(v) => setCertForm({ ...certForm, issue_date: v })} testid="cert-form-issue" />
              <Field label="Expiry Date" type="date" value={certForm.expiry_date} onChange={(v) => setCertForm({ ...certForm, expiry_date: v })} testid="cert-form-expiry" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Notes</Label>
              <Textarea value={certForm.notes} onChange={(e) => setCertForm({ ...certForm, notes: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="cert-form-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCertOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={addCert} data-testid="cert-form-save">Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Doc upload */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Upload className="h-4 w-4 text-primary" /> Upload Document</DialogTitle>
            <DialogDescription>Upload Aadhaar / PAN / Bank statement / certificates etc. After upload, click <b>AI Scan</b> to extract & verify fields.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Document Type *</Label>
              <Select value={uploadForm.doc_type} onValueChange={(v) => setUploadForm({ ...uploadForm, doc_type: v })}>
                <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="doc-upload-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {docTypes.map((d) => (
                    <SelectItem key={d.key} value={d.key}>
                      {d.label} {d.is_key_doc && <span className="text-[10px] text-emerald-700 ml-1">· KYC key</span>}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Field label="Label (optional)" value={uploadForm.label} onChange={(v) => setUploadForm({ ...uploadForm, label: v })} testid="doc-upload-label" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">File *</Label>
              <Input type="file" accept=".jpg,.jpeg,.png,.webp,.pdf" onChange={(e) => setUploadForm({ ...uploadForm, file: e.target.files?.[0] || null })} className="h-9 rounded-sm mt-1" data-testid="doc-upload-file" />
              <div className="text-[10px] text-muted-foreground mt-1">JPG / PNG / WEBP / PDF · max 25 MB</div>
              {uploadForm.file && <div className="text-[11px] text-muted-foreground mt-1">{uploadForm.file.name} ({Math.round(uploadForm.file.size / 1024)} KB)</div>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setUploadOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={uploadDoc} data-testid="doc-upload-save">Upload</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const VSTATUS_TONE = {
  verified: "bg-emerald-100 text-emerald-900 border-emerald-300",
  mismatch: "bg-red-100 text-red-900 border-red-300",
  no_data:  "bg-secondary text-muted-foreground border-border",
};
const ITEM_TONE = {
  match:    "text-emerald-700",
  mismatch: "text-red-700",
  no_data:  "text-muted-foreground",
};

function DocumentRow({ row, scanning, onScan, onDelete }) {
  const v = row.verification;
  const overall = v?.overall;
  const c = v?.counts || {};
  return (
    <>
      <TableRow data-testid={`doc-row-${row.id}`}>
        <TableCell>
          <a href={`${API}/files/${row.id}/download`} target="_blank" rel="noreferrer" className="font-semibold hover:underline">
            {row.title || row.original_filename}
          </a>
          <div className="text-[10px] text-muted-foreground">{row.original_filename} · {Math.round((row.size || 0) / 1024)} KB</div>
        </TableCell>
        <TableCell><Badge variant="outline" className="rounded-sm font-mono text-[10px]">{row.doc_type_label || row.doc_type}</Badge></TableCell>
        <TableCell>
          {row.scan_status === "scanned"
            ? <Badge className="rounded-sm border bg-blue-100 text-blue-900 border-blue-300"><FileCheck2 className="h-3 w-3 mr-1 inline" /> Scanned</Badge>
            : <Badge variant="outline" className="rounded-sm">Not scanned</Badge>}
        </TableCell>
        <TableCell>
          {overall && (
            <div className="flex items-center gap-1.5">
              <Badge className={`rounded-sm border ${VSTATUS_TONE[overall] || ""}`}>{overall.replace("_", " ")}</Badge>
              <span className="text-[10px] text-muted-foreground">
                {c.match || 0}✓ {c.mismatch || 0}✗ {c.no_data || 0}?
              </span>
            </div>
          )}
          {!overall && <span className="text-[11px] text-muted-foreground">—</span>}
        </TableCell>
        <TableCell className="text-[11px]">{(row.created_at || "").slice(0, 10)}</TableCell>
        <TableCell className="text-right">
          <div className="inline-flex gap-1">
            <Button size="sm" className="h-7 rounded-sm" onClick={onScan} disabled={scanning} data-testid={`doc-scan-${row.id}`}>
              {scanning
                ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Scanning…</>
                : <><ScanLine className="h-3 w-3 mr-1" /> {row.scan_status === "scanned" ? "Re-scan" : "AI Scan"}</>}
            </Button>
            <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={onDelete} data-testid={`doc-delete-${row.id}`}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
      {v?.items?.length > 0 && (
        <TableRow className="bg-secondary/30">
          <TableCell colSpan={6} className="py-2">
            <div className="flex flex-wrap gap-2">
              {v.items.map((it, i) => (
                <div key={i} className="text-[11px] bg-card border border-border rounded-sm px-2 py-1 flex items-center gap-1.5" title={JSON.stringify({ext: it.extracted_value, emp: it.employee_value})}>
                  <span className={ITEM_TONE[it.status]}>
                    {it.status === "match" && <CheckCircle2 className="h-3 w-3 inline" />}
                    {it.status === "mismatch" && <XCircle className="h-3 w-3 inline" />}
                    {it.status === "no_data" && <MinusCircle className="h-3 w-3 inline" />}
                  </span>
                  <span className="font-bold">{it.employee_key}</span>
                  <span className="text-muted-foreground truncate max-w-[140px]">{String(it.extracted_value || "—")}</span>
                </div>
              ))}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function Card({ children }) {
  return <div className="bg-card border border-border rounded-sm grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 p-5">{children}</div>;
}
function KV({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 last:border-0 pb-2 last:pb-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold text-right">{value || "—"}</span>
    </div>
  );
}
function Section({ title, icon: Icon, onAdd, addTestid, children }) {
  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="p-3 border-b border-border flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-primary" />}
        <div className="font-display font-bold text-sm">{title}</div>
        {onAdd && (
          <Button size="sm" variant="outline" className="ml-auto h-7 rounded-sm" onClick={onAdd} data-testid={addTestid}>
            <Plus className="h-3 w-3 mr-1" /> Add
          </Button>
        )}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}
function Empty({ text }) {
  return <div className="text-center py-6 text-sm text-muted-foreground">{text}</div>;
}
function StatBox({ label, value, tone = "blue" }) {
  const tones = {
    emerald: "bg-emerald-50 border-emerald-300 text-emerald-900",
    red: "bg-red-50 border-red-300 text-red-900",
    amber: "bg-amber-50 border-amber-300 text-amber-900",
    blue: "bg-blue-50 border-blue-300 text-blue-900",
  };
  return (
    <div className={`border rounded-sm p-3 ${tones[tone]}`}>
      <div className="text-[10px] font-bold uppercase tracking-wider opacity-80">{label}</div>
      <div className="text-2xl font-black tabular mt-1">{value}</div>
    </div>
  );
}
function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}

