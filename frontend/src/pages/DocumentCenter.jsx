/**
 * Document Center · central DMS for Projects + all modules.
 * Fast uploads (object storage) with background OneDrive sync.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { FolderArchive, Upload, RefreshCw, Download, History, Archive, Search, Cloud, CloudOff, Clock, FileText, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect } from "@/components/MasterSelect";

const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } };
const errMsg = (err, fallback) => {
  const d = err?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
};

const MODULES = [
  ["", "All"], ["projects", "Projects"], ["hr", "HR"], ["safety", "Safety"],
  ["procurement", "Procurement"], ["accounts", "Accounts"], ["logistics", "Logistics"], ["company", "Company"],
];
const MODULE_LABEL = Object.fromEntries(MODULES);

const STATUS_BADGE = {
  active: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Active</Badge>,
  pending_approval: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Approval</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
  archived: <Badge variant="outline" className="rounded-sm text-muted-foreground">Archived</Badge>,
};

const fmtSize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const API_BASE = process.env.REACT_APP_BACKEND_URL;

function ExpiryBadge({ date }) {
  if (!date) return <span className="text-muted-foreground">—</span>;
  const days = Math.ceil((new Date(date) - new Date()) / 86400000);
  if (days < 0) return <Badge variant="destructive" className="rounded-sm">Expired {Math.abs(days)}d</Badge>;
  if (days <= 30) return <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">{days}d left</Badge>;
  return <span className="text-xs">{date}</span>;
}

function SyncBadge({ status, url }) {
  if (status === "pushed") {
    return url
      ? <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[10px] text-emerald-700 font-bold" title="Synced to OneDrive — open"><Cloud className="h-3 w-3" /> OneDrive</a>
      : <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 font-bold"><Cloud className="h-3 w-3" /> Synced</span>;
  }
  if (status === "failed") return <span className="inline-flex items-center gap-1 text-[10px] text-red-600 font-bold" title="OneDrive sync failed — will retry"><CloudOff className="h-3 w-3" /> Retry</span>;
  return <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground" title="Queued for OneDrive sync"><Clock className="h-3 w-3" /> Queued</span>;
}

export default function DocumentCenter() {
  const { user, can } = useAuth();
  const canWrite = !!can && can("documents", "write");
  const [stats, setStats] = useState(null);
  const [cats, setCats] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ module: "", project_code: "", category_id: "", q: "", status: "", expiring: "" });
  const [uploading, setUploading] = useState(false);
  const [history, setHistory] = useState(null);
  const verInputRef = useRef(null);
  const [verTarget, setVerTarget] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
      const [d, s] = await Promise.all([api.get("/dms/documents", { params }), api.get("/dms/stats")]);
      setRows(d.data || []);
      setStats(s.data);
    } catch { toast.error("Failed to load documents"); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [JSON.stringify(filters)]); // eslint-disable-line
  useEffect(() => { api.get("/dms/categories").then((r) => setCats(r.data || [])).catch(() => {}); }, []);

  const download = (doc, ver) => {
    const v = ver || (doc.versions || []).slice(-1)[0];
    if (!v?.file_id) return;
    window.open(`${API_BASE}/api/files/${v.file_id}/download`, "_blank");
  };

  const onNewVersion = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !verTarget) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      await api.post(`/dms/documents/${verTarget.id}/versions`, fd, MULTIPART);
      toast.success(`Version ${(verTarget.current_version || 1) + 1} uploaded`);
      setVerTarget(null);
      load();
    } catch (err) { toast.error(errMsg(err, "Version upload failed")); }
  };

  const archive = async (doc) => {
    if (!window.confirm(`Archive ${doc.doc_no} — ${doc.title}?`)) return;
    try {
      await api.delete(`/dms/documents/${doc.id}`);
      toast.success("Document archived");
      load();
    } catch (err) { toast.error(errMsg(err, "Archive failed")); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="document-center">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-1.5">
            <FolderArchive className="h-3.5 w-3.5" /> Document Management
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Document Center</h1>
          <p className="text-sm text-muted-foreground">Central vault for Projects & all modules — fast uploads, background OneDrive sync, versioning & expiry tracking.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="dms-refresh">
            <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh
          </Button>
          {canWrite && (
            <Button className="h-9 rounded-sm" onClick={() => setUploading(true)} data-testid="dms-upload-btn">
              <Upload className="h-4 w-4 mr-1.5" /> Upload Document
            </Button>
          )}
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[["Total Documents", stats.total, "", ""],
            ["Expiring ≤ 30d", stats.expiring_30d, "soon", "text-amber-600"],
            ["Expired", stats.expired, "expired", "text-red-600"],
            ["Pending Approval", stats.pending_approval, "", "text-blue-600"]].map(([k, v, exp, tone]) => (
            <button key={k} type="button"
              onClick={() => setFilters((f) => ({ ...f, expiring: exp, status: k === "Pending Approval" ? "pending_approval" : "" }))}
              className="border border-border rounded-sm p-3 text-left bg-card hover:bg-secondary transition-colors"
              data-testid={`dms-stat-${k.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{k}</div>
              <div className={`text-2xl font-black tabular ${tone}`}>{v}</div>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 bg-card border border-border rounded-sm p-3">
        <div className="flex flex-wrap gap-1">
          {MODULES.map(([k, lbl]) => (
            <button key={k} type="button"
              onClick={() => setFilters((f) => ({ ...f, module: k, project_code: k === "projects" ? f.project_code : "" }))}
              className={`px-2.5 py-1.5 text-xs font-bold rounded-sm border transition-colors ${filters.module === k ? "bg-primary text-primary-foreground border-primary" : "bg-background border-border hover:bg-secondary"}`}
              data-testid={`dms-module-${k || "all"}`}>
              {lbl}{stats?.by_module?.[k] ? ` (${stats.by_module[k]})` : ""}
            </button>
          ))}
        </div>
        <div className="w-56">
          <ProjectSelect label="Project" value={filters.project_code} placeholder="— all projects —"
            onChange={(v) => setFilters((f) => ({ ...f, project_code: v }))} testid="dms-filter-project" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Category</Label>
          <select value={filters.category_id} onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))}
            className="h-9 mt-1 rounded-sm border border-input bg-background px-2 text-sm block" data-testid="dms-filter-category">
            <option value="">All categories</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}{c.requires_approval ? " (approval)" : ""}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Status</Label>
          <select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            className="h-9 mt-1 rounded-sm border border-input bg-background px-2 text-sm block" data-testid="dms-filter-status">
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="rejected">Rejected</option>
            <option value="archived">Archived</option>
          </select>
        </div>
        <div className="relative flex-1 min-w-[180px]">
          <Label className="text-[10px] uppercase tracking-wider">Search</Label>
          <Search className="h-3.5 w-3.5 absolute left-2 bottom-2.5 text-muted-foreground" />
          <Input value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
            placeholder="Title, doc no, tag, file name…" className="h-9 mt-1 pl-7 rounded-sm" data-testid="dms-search" />
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Doc #</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Module / Project</TableHead>
              <TableHead>Ver</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead>Expiry</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Sync</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">
                {loading ? "Loading…" : "No documents found — upload the first one."}
              </TableCell></TableRow>
            )}
            {rows.map((r) => {
              const latest = (r.versions || []).slice(-1)[0] || {};
              return (
                <TableRow key={r.id} data-testid={`dms-row-${r.doc_no}`}>
                  <TableCell className="font-mono-data text-xs">{r.doc_no}</TableCell>
                  <TableCell>
                    <div className="font-semibold text-sm">{r.title}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {latest.file_name} · {fmtSize(latest.size || 0)}
                      {(r.tags || []).length > 0 && <span> · {r.tags.map((t) => `#${t}`).join(" ")}</span>}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{r.category_name}</TableCell>
                  <TableCell className="text-xs">{MODULE_LABEL[r.module] || r.module}{r.project_code ? ` · ${r.project_code}` : ""}</TableCell>
                  <TableCell className="text-xs font-bold">v{r.current_version}</TableCell>
                  <TableCell className="text-xs">{latest.uploaded_by}<div className="text-[10px] text-muted-foreground">{(latest.uploaded_at || "").slice(0, 10)}</div></TableCell>
                  <TableCell><ExpiryBadge date={r.expiry_date} /></TableCell>
                  <TableCell>{STATUS_BADGE[r.status] || r.status}</TableCell>
                  <TableCell><SyncBadge status={r.onedrive_status} url={r.onedrive_url} /></TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Download latest" onClick={() => download(r)} data-testid={`dms-download-${r.doc_no}`}>
                      <Download className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Version history" onClick={() => setHistory(r)} data-testid={`dms-history-${r.doc_no}`}>
                      <History className="h-4 w-4" />
                    </Button>
                    {canWrite && r.status !== "archived" && (
                      <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Upload new version"
                        onClick={() => { setVerTarget(r); verInputRef.current?.click(); }} data-testid={`dms-newver-${r.doc_no}`}>
                        <Plus className="h-4 w-4" />
                      </Button>
                    )}
                    {canWrite && r.status !== "archived" && (user?.role === "super_admin" || user?.role === "director" || user?.id === r.created_by_id) && (
                      <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-red-600" title="Archive" onClick={() => archive(r)} data-testid={`dms-archive-${r.doc_no}`}>
                        <Archive className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <input ref={verInputRef} type="file" className="hidden" onChange={onNewVersion} data-testid="dms-version-file-input" />

      <UploadDialog open={uploading} onOpenChange={setUploading} cats={cats} onDone={load} />

      <Dialog open={!!history} onOpenChange={(o) => !o && setHistory(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><History className="h-4 w-4" /> {history?.doc_no} — Version History</DialogTitle>
            <DialogDescription>{history?.title}</DialogDescription>
          </DialogHeader>
          <ul className="space-y-1.5 max-h-80 overflow-y-auto">
            {(history?.versions || []).slice().reverse().map((v) => (
              <li key={v.version} className="flex items-center justify-between border border-border rounded-sm p-2.5" data-testid={`dms-ver-${v.version}`}>
                <div>
                  <div className="text-sm font-bold">v{v.version} <span className="font-normal text-xs text-muted-foreground">· {v.file_name} · {fmtSize(v.size || 0)}</span></div>
                  <div className="text-[10px] text-muted-foreground">{v.uploaded_by} · {(v.uploaded_at || "").slice(0, 16).replace("T", " ")}</div>
                </div>
                <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={() => download(history, v)} data-testid={`dms-ver-download-${v.version}`}>
                  <Download className="h-3.5 w-3.5 mr-1" /> Download
                </Button>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function UploadDialog({ open, onOpenChange, cats, onDone }) {
  const blank = { title: "", module: "projects", project_code: "", category_id: "", tags: "", expiry_date: "", remarks: "" };
  const [form, setForm] = useState(blank);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const cat = cats.find((c) => c.id === form.category_id);

  const submit = async () => {
    if (!file) return toast.error("Choose a file");
    if (!form.category_id) return toast.error("Pick a category");
    if (form.module === "projects" && !form.project_code) return toast.error("Pick a project");
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(form).forEach(([k, v]) => fd.append(k, v || ""));
    setBusy(true);
    try {
      const r = await api.post("/dms/documents", fd, MULTIPART);
      toast.success(`${r.data.doc_no} uploaded${r.data.status === "pending_approval" ? " — sent for approval" : ""}`);
      setForm(blank); setFile(null);
      onOpenChange(false);
      onDone();
    } catch (err) { toast.error(errMsg(err, "Upload failed")); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Upload className="h-4 w-4" /> Upload Document</DialogTitle>
          <DialogDescription>Stored instantly, auto-synced to OneDrive in the background.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">File *</Label>
            <Input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} className="mt-1 rounded-sm" data-testid="dms-form-file" />
          </div>
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">Title</Label>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder={file?.name || "Document title"} className="h-9 mt-1 rounded-sm" data-testid="dms-form-title" />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Module *</Label>
            <select value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value })}
              className="w-full h-9 mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="dms-form-module">
              {MODULES.filter(([k]) => k).map(([k, lbl]) => <option key={k} value={k}>{lbl}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Category *</Label>
            <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              className="w-full h-9 mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="dms-form-category">
              <option value="">— select —</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.name}{c.requires_approval ? " · needs approval" : ""}</option>)}
            </select>
            {cat?.requires_approval && <div className="text-[10px] text-amber-700 mt-1">This category goes for approval before becoming official.</div>}
          </div>
          {form.module === "projects" && (
            <ProjectSelect label="Project *" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="dms-form-project" />
          )}
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Expiry Date</Label>
            <Input type="date" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} className="h-9 mt-1 rounded-sm" data-testid="dms-form-expiry" />
          </div>
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">Tags (comma separated)</Label>
            <Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="insurance, 2026, tower-a" className="h-9 mt-1 rounded-sm" data-testid="dms-form-tags" />
          </div>
          <div className="col-span-2">
            <Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
            <Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} rows={2} className="mt-1 rounded-sm" data-testid="dms-form-remarks" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button className="rounded-sm" onClick={submit} disabled={busy} data-testid="dms-form-submit">
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
