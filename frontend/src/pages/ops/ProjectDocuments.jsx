/**
 * Project Documents · upload + browse documents per project using the existing
 * /api/uploads + /api/files infrastructure.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FileText, Upload, RefreshCcw, Download, Search } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { fmtDT } from "@/lib/datetime";
import { lookupGet } from "@/lib/lookups";

export default function ProjectDocuments() {
  const [projects, setProjects] = useState([]);
  const [selected, setSelected] = useState("");
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const { user } = useAuth() || {};
  const canWrite = !["sales_executive", "store_incharge", "purchase_officer"].includes(user?.role);

  useEffect(() => {
    lookupGet("/projects").then((r) => setProjects(r.data)).catch(() => {});
  }, []);
  const loadDocs = async (pid) => {
    if (!pid) { setDocs([]); return; }
    try {
      const r = await api.get(`/files?resource=projects&record_id=${pid}`);
      setDocs(r.data || []);
    } catch (e) {
      // Fallback if /files endpoint not available
      setDocs([]);
    }
  };
  useEffect(() => { loadDocs(selected); }, [selected]);

  const onUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f || !selected) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("resource", "projects");
      fd.append("record_id", selected);
      await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Uploaded ${f.name}`);
      loadDocs(selected);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const filtered = useMemo(() => {
    const qq = q.toLowerCase().trim();
    if (!qq) return docs;
    return docs.filter((d) => (d.original_name || d.filename || "").toLowerCase().includes(qq));
  }, [docs, q]);

  const selectedProject = projects.find((p) => p.id === selected);

  return (
    <div className="p-6 space-y-4" data-testid="page-project-documents">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><FileText className="h-6 w-6 text-primary" /> Project Documents</h1>
          <p className="text-sm text-muted-foreground">Upload & view scope docs, drawings, MoMs, MPRs, billing certificates per Project.</p>
        </div>
      </div>

      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <select value={selected} onChange={(e) => setSelected(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm min-w-[320px]" data-testid="pd-project">
            <option value="">— Select a project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
          <div className="relative flex-1 min-w-[220px]">
            <Search className="h-4 w-4 absolute left-2.5 top-3 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter documents…" className="pl-8 h-9" />
          </div>
          {canWrite && selected && (
            <label className="inline-flex items-center gap-1 h-9 px-3 rounded-sm border bg-card hover:bg-accent cursor-pointer text-sm" data-testid="pd-upload-label">
              <Upload className="h-3.5 w-3.5" /> {busy ? "Uploading…" : "Upload"}
              <input type="file" hidden onChange={onUpload} disabled={busy} data-testid="pd-upload-input" />
            </label>
          )}
          <Button size="sm" variant="outline" onClick={() => loadDocs(selected)}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            {selectedProject ? <span><span className="font-mono text-xs text-primary">{selectedProject.code}</span> · {selectedProject.name}</span> : "Documents"} <span className="text-xs text-slate-400">({filtered.length})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!selected ? (
            <div className="text-center py-12 text-muted-foreground">Select a project to view its documents.</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">No documents yet. {canWrite && "Click Upload to add the first one."}</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Filename</th>
                  <th className="px-3 py-2">Size</th>
                  <th className="px-3 py-2">Uploaded By</th>
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => (
                  <tr key={d.id || d.filename} className="border-b hover:bg-slate-50/50">
                    <td className="px-3 py-2 font-medium">{d.original_name || d.filename}</td>
                    <td className="px-3 py-2 text-xs">{d.size ? (d.size / 1024).toFixed(1) + " KB" : "—"}</td>
                    <td className="px-3 py-2 text-xs">{d.uploaded_by || d.created_by || "—"}</td>
                    <td className="px-3 py-2 text-xs">{fmtDT(d.uploaded_at || d.created_at)}</td>
                    <td className="px-3 py-2 text-right">
                      {d.url && (
                        <a href={d.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 text-xs">
                          <Download className="h-3.5 w-3.5" /> Open
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
