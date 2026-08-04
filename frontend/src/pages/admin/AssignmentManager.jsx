import { useEffect, useState } from "react";
import { UserCog, History, Save, RefreshCw, ArrowRightLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function AssignmentManager() {
  const [data, setData] = useState({ projects: [], users: [], pm_users: [], coord_users: [] });
  const [drafts, setDrafts] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [histFor, setHistFor] = useState(null);
  const [hist, setHist] = useState(null);
  const [q, setQ] = useState("");
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulk, setBulk] = useState({ from_user_id: "", to_user_id: "", remarks: "" });
  const [bulkSaving, setBulkSaving] = useState(false);

  const bulkTransfer = async () => {
    if (!bulk.from_user_id || !bulk.to_user_id) return toast.error("Pick both users");
    if (bulk.from_user_id === bulk.to_user_id) return toast.error("Source and target are the same person");
    setBulkSaving(true);
    try {
      const r = await api.post("/ops/project-assignments/bulk/transfer", bulk);
      toast.success(`${r.data.transferred} project(s) moved from ${r.data.from} to ${r.data.to}`);
      setBulkOpen(false); setBulk({ from_user_id: "", to_user_id: "", remarks: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Transfer failed"); }
    finally { setBulkSaving(false); }
  };

  const bulkCount = data.projects.filter((p) => p.project_manager_id === bulk.from_user_id || p.project_coordinator_id === bulk.from_user_id).length;

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

  const pms = data.pm_users || [];
  const coords = data.coord_users || [];
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
          <Button variant="outline" size="sm" className="text-orange-700 border-orange-300" onClick={() => setBulkOpen(true)} data-testid="bulk-transfer-btn"><ArrowRightLeft className="h-4 w-4 mr-1" /> Bulk Transfer</Button>
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
                      options={coords} onChange={(v) => setDraft(p.id, "project_coordinator_id", v)} testid={`assign-coord-${p.code}`} />
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

      <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><ArrowRightLeft className="h-4 w-4 text-orange-600" /> Bulk Transfer Projects</DialogTitle>
            <DialogDescription>Move every project handled by one person (as PM or Coordinator) to someone else — for exits, leave or workload balancing.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <div className="text-xs font-semibold mb-1">Transfer FROM</div>
              <UserSelect value={bulk.from_user_id} options={data.users} onChange={(v) => setBulk((b) => ({ ...b, from_user_id: v }))} testid="bulk-from" />
              {bulk.from_user_id && <div className="text-[11px] mt-1 text-orange-700" data-testid="bulk-count">{bulkCount} project(s) will be transferred</div>}
            </div>
            <div>
              <div className="text-xs font-semibold mb-1">Transfer TO</div>
              <UserSelect value={bulk.to_user_id} options={data.users.filter((u) => u.id !== bulk.from_user_id)} onChange={(v) => setBulk((b) => ({ ...b, to_user_id: v }))} testid="bulk-to" />
            </div>
            <div>
              <div className="text-xs font-semibold mb-1">Reason / note (shown in history)</div>
              <Input value={bulk.remarks} onChange={(e) => setBulk((b) => ({ ...b, remarks: e.target.value }))} placeholder="e.g., On leave till Sept 15" className="h-9" data-testid="bulk-remarks" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setBulkOpen(false)}>Cancel</Button>
              <Button className="bg-orange-600 hover:bg-orange-700" disabled={bulkSaving || !bulkCount} onClick={bulkTransfer} data-testid="bulk-submit">{bulkSaving ? "Transferring…" : `Transfer ${bulkCount || ""} Project(s)`}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!histFor} onOpenChange={(v) => !v && setHistFor(null)}>
        <DialogContent className="max-w-lg bg-white dark:bg-slate-900">
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
