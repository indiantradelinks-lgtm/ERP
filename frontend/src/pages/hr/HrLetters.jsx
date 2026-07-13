import { useEffect, useMemo, useState } from "react";
import {
  FileText, Upload, Trash2, Download, Plus, Search,
  ScrollText, Info, History, FileCode2, Mail,
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
import { api, API, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import SendEmailDialog from "@/components/SendEmailDialog";

const KINDS = [
  { value: "offer", label: "Offer Letter" },
  { value: "appointment", label: "Appointment Letter" },
  { value: "confirmation", label: "Confirmation Letter" },
  { value: "experience", label: "Experience Certificate" },
  { value: "relieving", label: "Relieving Letter" },
  { value: "warning", label: "Warning Letter" },
  { value: "transfer", label: "Transfer Letter" },
  { value: "promotion", label: "Promotion Letter" },
  { value: "increment", label: "Increment Letter" },
  { value: "salary_slip", label: "Salary Slip" },
  { value: "custom", label: "Custom" },
];

export default function HrLetters() {
  const [tab, setTab] = useState("templates");
  const [templates, setTemplates] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [letters, setLetters] = useState([]);
  const [placeholders, setPlaceholders] = useState(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ name: "", kind: "offer", description: "", file: null });

  const [renderOpen, setRenderOpen] = useState(false);
  const [renderTpl, setRenderTpl] = useState(null);
  const [renderEmp, setRenderEmp] = useState("");
  const [customVars, setCustomVars] = useState([]); // [{k,v}]
  const [showPlaceholders, setShowPlaceholders] = useState(false);
  const [emailFor, setEmailFor] = useState(null);

  const [q, setQ] = useState("");

  const load = async () => {
    try {
      const [t, e, l, p] = await Promise.all([
        api.get("/hr/letter-templates"),
        api.get("/employees"),
        api.get("/hr/letters"),
        api.get("/hr/letters/placeholders"),
      ]);
      setTemplates(t.data || []);
      setEmployees(e.data || []);
      setLetters(l.data || []);
      setPlaceholders(p.data);
    } catch (err) { toast.error(apiErrorMessage(err, "Load failed")); }
  };
  useEffect(() => { load(); }, []);

  const filteredTpl = useMemo(() => {
    if (!q.trim()) return templates;
    const s = q.toLowerCase();
    return templates.filter((t) => [t.name, t.kind, t.description].some((v) => (v || "").toLowerCase().includes(s)));
  }, [templates, q]);

  const uploadTpl = async () => {
    if (!uploadForm.name.trim() || !uploadForm.file) {
      toast.error("Name and .docx file are required"); return;
    }
    if (!uploadForm.file.name.toLowerCase().endsWith(".docx")) {
      toast.error("Only .docx files are supported"); return;
    }
    const fd = new FormData();
    fd.append("file", uploadForm.file);
    fd.append("name", uploadForm.name);
    fd.append("kind", uploadForm.kind);
    fd.append("description", uploadForm.description);
    try {
      await api.post("/hr/letter-templates", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Template uploaded");
      setUploadOpen(false);
      setUploadForm({ name: "", kind: "offer", description: "", file: null });
      load();
    } catch (e) { toast.error(apiErrorMessage(e, "Upload failed")); }
  };

  const deleteTpl = async (tid) => {
    if (!window.confirm("Delete this template? Existing rendered letters are kept.")) return;
    try {
      await api.delete(`/hr/letter-templates/${tid}`);
      toast.success("Deleted"); load();
    } catch (e) { toast.error(apiErrorMessage(e, "Delete failed")); }
  };

  const downloadTpl = (tid) => {
    window.open(`${API}/hr/letter-templates/${tid}/download`, "_blank");
  };

  const openRender = (tpl) => {
    setRenderTpl(tpl);
    setRenderEmp(employees[0]?.id || "");
    setCustomVars([]);
    setRenderOpen(true);
  };

  const renderLetter = async () => {
    if (!renderEmp) { toast.error("Pick employee"); return; }
    const variables = {};
    customVars.forEach(({ k, v }) => { if (k.trim()) variables[k.trim()] = v; });
    try {
      const res = await fetch(`${API}/hr/letter-templates/${renderTpl.id}/render`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: renderEmp, variables }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(apiErrorMessage({ response: { data: body } }, "Render failed"));
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const empCode = employees.find((e) => e.id === renderEmp)?.emp_code || "letter";
      a.href = url;
      a.download = `${renderTpl.kind}_${empCode}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Letter generated & downloaded");
      setRenderOpen(false);
      load();
    } catch (e) { toast.error(e.message || "Render failed"); }
  };

  const downloadLetter = (lid) => {
    window.open(`${API}/hr/letters/${lid}/download`, "_blank");
  };

  return (
    <div className="space-y-6" data-testid="hr-letters-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ScrollText className="h-3 w-3" /> Human Resources
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Letters & Templates</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Upload DOCX templates with Jinja-style placeholders. The merge engine fills employee, company, user
          and any custom variables you pass at render time, then returns a ready-to-print Word doc.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="templates" data-testid="letters-tab-templates"><FileText className="h-3.5 w-3.5 mr-1" />Templates ({templates.length})</TabsTrigger>
          <TabsTrigger value="history" data-testid="letters-tab-history"><History className="h-3.5 w-3.5 mr-1" />Render History ({letters.length})</TabsTrigger>
        </TabsList>

        {/* TEMPLATES */}
        <TabsContent value="templates" className="mt-4 space-y-3">
          <div className="bg-card border border-border rounded-sm p-3 flex flex-wrap items-center gap-2">
            <div className="relative w-72">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="tpl-search" />
            </div>
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => setShowPlaceholders(true)} data-testid="tpl-help">
              <Info className="h-4 w-4 mr-1.5" /> Placeholders Help
            </Button>
            <Button className="ml-auto h-9 rounded-sm" onClick={() => setUploadOpen(true)} data-testid="tpl-upload">
              <Upload className="h-4 w-4 mr-1.5" /> Upload Template
            </Button>
          </div>

          <div className="bg-card border border-border rounded-sm overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Name</TableHead><TableHead>Kind</TableHead><TableHead>Description</TableHead>
                <TableHead>Uploaded</TableHead><TableHead>Size</TableHead><TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {filteredTpl.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No templates yet — upload one to get started.</TableCell></TableRow>}
                {filteredTpl.map((t) => (
                  <TableRow key={t.id} data-testid={`tpl-row-${t.id}`}>
                    <TableCell className="font-semibold">{t.name}</TableCell>
                    <TableCell><Badge variant="outline" className="rounded-sm font-mono">{t.kind}</Badge></TableCell>
                    <TableCell className="text-[12px] max-w-xs truncate">{t.description || "—"}</TableCell>
                    <TableCell className="text-[11px]">{(t.created_at || "").slice(0, 10)}</TableCell>
                    <TableCell className="text-[11px] tabular">{Math.round((t.size_bytes || 0) / 1024)} KB</TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button size="sm" className="h-7 rounded-sm" onClick={() => openRender(t)} data-testid={`tpl-render-${t.id}`}>
                          <FileCode2 className="h-3 w-3 mr-1" /> Render
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => downloadTpl(t.id)} data-testid={`tpl-download-${t.id}`}>
                          <Download className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => deleteTpl(t.id)} data-testid={`tpl-delete-${t.id}`}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* HISTORY */}
        <TabsContent value="history" className="mt-4">
          <div className="bg-card border border-border rounded-sm overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Template</TableHead><TableHead>Kind</TableHead><TableHead>Employee</TableHead>
                <TableHead>Rendered At</TableHead><TableHead>By</TableHead><TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {letters.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No letters generated yet.</TableCell></TableRow>}
                {letters.map((l) => (
                  <TableRow key={l.id} data-testid={`letter-row-${l.id}`}>
                    <TableCell className="font-semibold">{l.template_name}</TableCell>
                    <TableCell><Badge variant="outline" className="rounded-sm font-mono">{l.template_kind}</Badge></TableCell>
                    <TableCell>{l.employee_name}</TableCell>
                    <TableCell className="text-[11px]">{(l.rendered_at || "").slice(0, 19).replace("T", " ")}</TableCell>
                    <TableCell className="text-[11px]">{l.rendered_by}</TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1 justify-end">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => downloadLetter(l.id)} data-testid={`letter-download-${l.id}`}>
                          <Download className="h-3 w-3 mr-1" /> Download
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setEmailFor(l)} data-testid={`letter-email-${l.id}`}>
                          <Mail className="h-3 w-3 mr-1" /> Email
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      {/* Upload dialog */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Upload className="h-4 w-4 text-primary" /> Upload DOCX Template</DialogTitle>
            <DialogDescription>Use Jinja-style placeholders like <code className="bg-secondary px-1 rounded">{`{{ name }}`}</code>, <code className="bg-secondary px-1 rounded">{`{{ designation }}`}</code>, <code className="bg-secondary px-1 rounded">{`{{ today_long }}`}</code> in your .docx file.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Template Name *</Label>
              <Input value={uploadForm.name} onChange={(e) => setUploadForm({ ...uploadForm, name: e.target.value })} className="rounded-sm mt-1 h-9" data-testid="tpl-form-name" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Kind</Label>
              <Select value={uploadForm.kind} onValueChange={(v) => setUploadForm({ ...uploadForm, kind: v })}>
                <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="tpl-form-kind"><SelectValue /></SelectTrigger>
                <SelectContent>{KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Description</Label>
              <Textarea value={uploadForm.description} onChange={(e) => setUploadForm({ ...uploadForm, description: e.target.value })} className="rounded-sm mt-1 min-h-[60px]" data-testid="tpl-form-desc" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">DOCX File *</Label>
              <Input type="file" accept=".docx" onChange={(e) => setUploadForm({ ...uploadForm, file: e.target.files?.[0] || null })} className="rounded-sm mt-1 h-9" data-testid="tpl-form-file" />
              {uploadForm.file && <div className="text-[11px] text-muted-foreground mt-1">{uploadForm.file.name} ({Math.round(uploadForm.file.size / 1024)} KB)</div>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setUploadOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={uploadTpl} data-testid="tpl-form-save">Upload</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Render dialog */}
      <Dialog open={renderOpen} onOpenChange={setRenderOpen}>
        <DialogContent className="max-w-xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><FileCode2 className="h-4 w-4 text-primary" /> Render: {renderTpl?.name}</DialogTitle>
            <DialogDescription>Pick the employee, add any custom variables, then generate the merged DOCX.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Employee *</Label>
              <Select value={renderEmp} onValueChange={setRenderEmp}>
                <SelectTrigger className="h-9 rounded-sm mt-1" data-testid="render-employee"><SelectValue placeholder="Pick…" /></SelectTrigger>
                <SelectContent>
                  {employees.map((e) => <SelectItem key={e.id} value={e.id}>{e.name} ({e.emp_code})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider flex items-center gap-2">
                Custom Variables
                <Button size="sm" variant="ghost" className="h-6 rounded-sm" onClick={() => setCustomVars([...customVars, { k: "", v: "" }])} data-testid="render-add-var">
                  <Plus className="h-3 w-3 mr-1" /> Add
                </Button>
              </Label>
              <div className="space-y-1.5 mt-1">
                {customVars.length === 0 && <div className="text-[11px] text-muted-foreground">e.g. add <code>increment_amount</code> = <code>50000</code> if your template uses <code>{`{{ increment_amount }}`}</code>.</div>}
                {customVars.map((v, i) => (
                  <div key={i} className="flex gap-1.5">
                    <Input className="h-8 rounded-sm" placeholder="variable_key" value={v.k} onChange={(e) => { const c = [...customVars]; c[i].k = e.target.value; setCustomVars(c); }} data-testid={`render-var-key-${i}`} />
                    <Input className="h-8 rounded-sm" placeholder="value" value={v.v} onChange={(e) => { const c = [...customVars]; c[i].v = e.target.value; setCustomVars(c); }} data-testid={`render-var-val-${i}`} />
                    <Button size="sm" variant="outline" className="h-8 w-8 p-0 rounded-sm" onClick={() => setCustomVars(customVars.filter((_, j) => j !== i))}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRenderOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={renderLetter} data-testid="render-confirm">
              <Download className="h-4 w-4 mr-1.5" /> Generate & Download
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Placeholders reference */}
      <Dialog open={showPlaceholders} onOpenChange={setShowPlaceholders}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Info className="h-4 w-4 text-primary" /> Placeholders Reference</DialogTitle>
            <DialogDescription>Use these tokens in your .docx template using Jinja syntax: <code className="bg-secondary px-1 rounded">{`{{ token }}`}</code>.</DialogDescription>
          </DialogHeader>
          {placeholders && (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto text-sm">
              {Object.entries(placeholders).map(([group, items]) => (
                <div key={group} className="bg-card border border-border rounded-sm p-3">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-primary mb-1.5">{group}</div>
                  {Array.isArray(items) ? (
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((p) => <code key={p} className="bg-secondary px-2 py-0.5 rounded-sm text-[12px]">{`{{ ${p} }}`}</code>)}
                    </div>
                  ) : (
                    <div className="text-[12px] text-muted-foreground">{items}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="hr_letter"
        recordId={emailFor?.id}
      />
    </div>
  );
}
