/**
 * Project WBS · P&O Phase 2 (Round 2)
 *
 * Hierarchical Work Breakdown Structure per project. Tree view with
 * indented codes (1, 1.1, 1.1.2). Inline add/edit/delete; deleting a
 * node cascades to its descendants and unlinks dependent activities /
 * resources.
 *
 * Backend: /api/proj-phase2/wbs/{project_id} ...
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
import { Network, Plus, Pencil, Trash2, RefreshCcw, ChevronRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

const WBS_STATUS = ["not_started", "in_progress", "completed", "on_hold", "cancelled"];
const EMPTY = {
  code: "", name: "", description: "", parent_id: "",
  scope_type: "", weight_pct: 0, estimated_hours: 0, status: "not_started",
  boq_id: "", remarks: "",
};

export default function ProjectWBS() {
  const [projects, setProjects]   = useState([]);
  const [projectId, setProjectId] = useState("");
  const [nodes, setNodes]         = useState([]);
  const [editing, setEditing]     = useState(null);     // {} new, row edit
  const [form, setForm]           = useState(EMPTY);
  const { user } = useAuth() || {};
  const canEdit = !["sales_executive", "store_incharge"].includes(user?.role);

  useEffect(() => { lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { if (projectId) load(); else setNodes([]); }, [projectId]);

  const load = async () => {
    try {
      const { data } = await api.get(`/proj-phase2/wbs/${projectId}`);
      setNodes(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };

  const tree = useMemo(() => buildTree(nodes), [nodes]);
  const flatList = useMemo(() => flatten(tree), [tree]);

  const save = async () => {
    if (!projectId) { toast.error("Pick a project first"); return; }
    if (!form.code?.trim()) { toast.error("Code is required"); return; }
    if (!form.name?.trim()) { toast.error("Name is required"); return; }
    try {
      const payload = {
        ...form,
        parent_id: form.parent_id || null,
        weight_pct: Number(form.weight_pct) || 0,
        estimated_hours: Number(form.estimated_hours) || 0,
      };
      if (editing?.id) {
        await api.put(`/proj-phase2/wbs/nodes/${editing.id}`, payload);
        toast.success("Node updated");
      } else {
        await api.post(`/proj-phase2/wbs/${projectId}`, payload);
        toast.success("Node created");
      }
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (n) => {
    if (!window.confirm(`Delete WBS ${n.code} and all its descendants?`)) return;
    try {
      await api.delete(`/proj-phase2/wbs/nodes/${n.id}`);
      toast.success("Node deleted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-project-wbs">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Network className="h-6 w-6 text-primary" /> Work Breakdown Structure
          </h1>
          <p className="text-sm text-muted-foreground">Hierarchical tree of project scope. Codes use dot-notation (1 → 1.1 → 1.1.2). Deleting a parent cascades all descendants.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm min-w-[260px]" data-testid="wbs-project-select">
            <option value="">— select project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={!projectId}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          {canEdit && projectId && (
            <Button onClick={() => { setEditing({}); setForm({ ...EMPTY }); }} data-testid="wbs-new">
              <Plus className="h-4 w-4 mr-1" /> Add Node
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">WBS Tree <span className="text-xs text-slate-400">({nodes.length} nodes)</span></CardTitle></CardHeader>
        <CardContent>
          {!projectId ? (
            <div className="text-center py-10 text-slate-400">Select a project to load its WBS</div>
          ) : nodes.length === 0 ? (
            <div className="text-center py-10 text-slate-400">No WBS nodes yet — click &quot;Add Node&quot; to start.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2 w-72">Code · Name</th>
                    <th className="px-2 py-2">Scope</th>
                    <th className="px-2 py-2 text-right">Weight %</th>
                    <th className="px-2 py-2 text-right">Est. Hrs</th>
                    <th className="px-2 py-2 text-center">Status</th>
                    <th className="px-2 py-2">Remarks</th>
                    <th className="px-2 py-2 text-right w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {flatList.map((n) => (
                    <tr key={n.id} className="border-b hover:bg-slate-50/50" data-testid={`wbs-row-${n.id}`}>
                      <td className="px-2 py-1">
                        <div className="flex items-center" style={{ paddingLeft: `${(n.level - 1) * 18}px` }}>
                          {n.level > 1 && <ChevronRight className="h-3 w-3 text-slate-400 mr-1" />}
                          <span className="font-mono text-xs text-primary font-bold mr-2">{n.code}</span>
                          <span className="truncate">{n.name}</span>
                        </div>
                      </td>
                      <td className="px-2 py-1 text-xs">{n.scope_type || "—"}</td>
                      <td className="px-2 py-1 text-right font-mono text-xs">{n.weight_pct || 0}%</td>
                      <td className="px-2 py-1 text-right font-mono text-xs">{n.estimated_hours || 0}</td>
                      <td className="px-2 py-1 text-center"><span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone(n.status)}`}>{n.status}</span></td>
                      <td className="px-2 py-1 text-xs truncate max-w-[200px]">{n.remarks || ""}</td>
                      <td className="px-2 py-1 text-right">
                        {canEdit && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(n); setForm({ ...EMPTY, ...n, parent_id: n.parent_id || "" }); }} data-testid={`wbs-edit-${n.id}`}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(n)} data-testid={`wbs-del-${n.id}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "Add"} WBS Node</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Code *"><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="1.1.2" data-testid="wbs-form-code" /></F>
            <F label="Parent">
              <select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="wbs-form-parent">
                <option value="">— Root —</option>
                {nodes.filter((n) => n.id !== editing?.id).map((n) => <option key={n.id} value={n.id}>{n.code} · {n.name}</option>)}
              </select>
            </F>
            <F label="Name *" full><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="wbs-form-name" /></F>
            <F label="Description" full><Textarea rows={2} value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} /></F>
            <F label="Scope Type"><Input value={form.scope_type} onChange={(e) => setForm({ ...form, scope_type: e.target.value })} placeholder="Civil / MEP / Painting" /></F>
            <F label="Weight (%)"><Input type="number" value={form.weight_pct} onChange={(e) => setForm({ ...form, weight_pct: e.target.value })} /></F>
            <F label="Est. Hours"><Input type="number" value={form.estimated_hours} onChange={(e) => setForm({ ...form, estimated_hours: e.target.value })} /></F>
            <F label="Status">
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm">
                {WBS_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </F>
            <F label="Remarks" full><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="wbs-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const TONES = {
  not_started: "bg-slate-50 text-slate-600 border-slate-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  completed:   "bg-emerald-50 text-emerald-700 border-emerald-200",
  on_hold:     "bg-amber-50 text-amber-700 border-amber-200",
  cancelled:   "bg-rose-50 text-rose-700 border-rose-200",
};
function tone(s) { return TONES[s] || TONES.not_started; }

function buildTree(nodes) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, { ...n, children: [] }]));
  const roots = [];
  nodes.forEach((n) => {
    const node = byId[n.id];
    if (n.parent_id && byId[n.parent_id]) byId[n.parent_id].children.push(node);
    else roots.push(node);
  });
  return roots;
}
function flatten(tree) {
  const out = [];
  const walk = (arr) => arr.forEach((n) => { out.push(n); if (n.children?.length) walk(n.children); });
  walk(tree);
  return out;
}

function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
