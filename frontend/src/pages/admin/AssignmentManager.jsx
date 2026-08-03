import { useEffect, useState } from "react";
import { UserCog, History, Save, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function AssignmentManager() {
  const [data, setData] = useState({ projects: [], users: [] });
  const [drafts, setDrafts] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [histFor, setHistFor] = useState(null);
  const [hist, setHist] = useState(null);
  const [q, setQ] = useState("");

  const load = () => api.get("/ops/project-assignments").then((r) => { setData(r.data); setDrafts({}); }).catch((e) => toast.error(e?.response?.data?.detail || "Load failed"));
  useEffect(() => { load(); }, []);

  const setDraft = (pid, field, value) => setDrafts((d) => ({ ...d, [pid]: { ...(d[pid] || {}), [field]: value } }));

  const save = async (p) => {
    const d = drafts[p.id];
    if (!d) return;
    setSavingId(p.id);
    try {
      const remarks = window.prompt("Transfer note (optional)") || undefined;
      const res = await api.post(`/ops/project-assignments/${p.id}`, { ...d, remarks });
      toast.success(res.data.changed ? `Assignment updated (${res.data.changed} change(s)) — assignee notified` : "No changes");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSavingId(null); }
  };

  const openHistory = async (p) => {
    setHistFor(p); setHist(null);
    try { const r = await api.get(`/ops/project-assignments/${p.id}/history`); setHist(r.data); }
    catch { setHist({ history: [] }); }
  };

  const pms = data.users.filter((u) => u.role === "project_manager" || u.role === "dept_head");
  const coords = data.users.filter((u) => ["project_coordinator", "site_engineer", "site_supervisor"].includes(u.role));
  const filtered = data.projects.filter((p) => !q || `${p.code} ${p.name} ${p.client || ""}`.toLowerCase().includes(q.toLowerCase()));

  const UserSelect = ({ value, options, onChange, testid }) => (
    <select value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={testid}
      className="h-8 w-full rounded-sm border border-input bg-background px-2 text-xs">
      <option value="">— unassigned —</option>
      {options.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role.replace(/_/g, " ")})</option>)}
    </select>
  );

  return (
    <div className="space-y-4 p-1" data-testid="assignment-manager">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl flex items-center gap-2"><UserCog className="h-6 w-6 text-primary" /> Project Assignments</h1>
          <p className="text-xs text-muted-foreground">Assign or transfer the Project Manager & Coordinator per project. Assignees see only their projects — changes apply instantly and are notified.</p>
        </div>
        <div className="flex gap-2">
          <Input placeholder="Search project / client…" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 w-64" data-testid="assign-search" />
          <Button variant="outline" size="sm" onClick={load} data-testid="assign-refresh"><RefreshCw className="h-4 w-4" /></Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-auto">
        <Table data-testid="assign-table">
          <TableHeader>
            <TableRow>
              <TableHead>Project</TableHead><TableHead>Status</TableHead>
              <TableHead className="min-w-[220px]">Project Manager</TableHead>
              <TableHead className="min-w-[220px]">Project Coordinator</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((p) => {
              const d = drafts[p.id] || {};
              const dirty = d.project_manager_id !== undefined || d.project_coordinator_id !== undefined;
              return (
                <TableRow key={p.id} data-testid={`assign-row-${p.code}`}>
                  <TableCell className="text-xs"><b>{p.code}</b><div className="text-muted-foreground">{p.name}</div><div className="text-[10px] text-muted-foreground">{p.client}</div></TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{p.status || "—"}</Badge></TableCell>
                  <TableCell>
                    <UserSelect value={d.project_manager_id !== undefined ? d.project_manager_id : p.project_manager_id}
                      options={pms} onChange={(v) => setDraft(p.id, "project_manager_id", v)} testid={`assign-pm-${p.code}`} />
                    {p.project_manager_name && <div className="text-[10px] text-muted-foreground mt-0.5">current: {p.project_manager_name}</div>}
                  </TableCell>
                  <TableCell>
                    <UserSelect value={d.project_coordinator_id !== undefined ? d.project_coordinator_id : p.project_coordinator_id}
                      options={coords.length ? coords : data.users} onChange={(v) => setDraft(p.id, "project_coordinator_id", v)} testid={`assign-coord-${p.code}`} />
                    {p.project_coordinator_name && <div className="text-[10px] text-muted-foreground mt-0.5">current: {p.project_coordinator_name}</div>}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button size="sm" variant={dirty ? "default" : "outline"} disabled={!dirty || savingId === p.id}
                      className="h-7 text-xs mr-1" onClick={() => save(p)} data-testid={`assign-save-${p.code}`}>
                      <Save className="h-3 w-3 mr-1" /> {savingId === p.id ? "Saving…" : "Save"}
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => openHistory(p)} data-testid={`assign-history-${p.code}`}>
                      <History className="h-3 w-3 mr-1" /> {p.history_count || 0}
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {!filtered.length && <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">No projects found</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!histFor} onOpenChange={(v) => !v && setHistFor(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><History className="h-4 w-4" /> Assignment History</DialogTitle>
            <DialogDescription>{histFor?.code} · {histFor?.name}</DialogDescription>
          </DialogHeader>
          <div className="max-h-80 overflow-auto space-y-2" data-testid="assign-history-list">
            {!hist && <div className="text-sm text-muted-foreground">Loading…</div>}
            {hist && !hist.history?.length && <div className="text-sm text-muted-foreground py-4 text-center">No assignment changes recorded yet.</div>}
            {(hist?.history || []).map((h) => (
              <div key={h.id} className="border rounded-sm p-2.5 text-xs">
                <div className="font-semibold">{h.field}: <span className="text-muted-foreground">{h.from_name || "unassigned"}</span> → <span className="text-primary">{h.to_name || "unassigned"}</span></div>
                <div className="text-[10px] text-muted-foreground mt-0.5">{(h.at || "").replace("T", " ").slice(0, 16)} · by {h.by}{h.remarks ? ` · "${h.remarks}"` : ""}</div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
