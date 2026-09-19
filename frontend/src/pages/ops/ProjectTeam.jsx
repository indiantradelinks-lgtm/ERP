/**
 * Project Team · view + edit the team assigned to each project.
 * Aggregates: project_manager / project_coordinator / reporting_manager /
 *             site_supervisor / safety_officer / material_coordinator.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Users, Pencil, RefreshCcw, Search } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

export default function ProjectTeam() {
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [q, setQ] = useState("");
  const { user } = useAuth() || {};
  const canWrite = ["super_admin", "director", "general_manager", "dept_head"].includes(user?.role);

  const load = async () => {
    try {
      const r = await lookupGet("/projects");
      setProjects(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const qq = q.toLowerCase().trim();
    if (!qq) return projects;
    return projects.filter((p) =>
      [p.code, p.name, p.client, p.site, p.manager, p.site_supervisor, p.safety_officer]
        .filter(Boolean).join(" ").toLowerCase().includes(qq));
  }, [projects, q]);

  const save = async () => {
    try {
      await api.put(`/projects/${editing.id}`, { ...editing, ...form });
      toast.success("Team updated");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const teamCount = (p) => ["manager", "project_coordinator_id", "reporting_manager_id",
    "site_supervisor", "safety_officer", "material_coordinator"].filter((k) => p[k]).length;

  return (
    <div className="p-6 space-y-4" data-testid="page-project-team">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Users className="h-6 w-6 text-primary" /> Project Team</h1>
          <p className="text-sm text-muted-foreground">Manage PM, Coordinator, Reporting Manager, Site Supervisor, Safety Officer & Material Coordinator on every project.</p>
        </div>
        <Button size="sm" variant="outline" onClick={load}>
          <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-3">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-2.5 top-3 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by code, name, client, manager…" className="pl-8 h-9" data-testid="pt-search" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Projects ({filtered.length})</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2">Client / Site</th>
                  <th className="px-3 py-2">PM</th>
                  <th className="px-3 py-2">Site Supervisor</th>
                  <th className="px-3 py-2">Safety Officer</th>
                  <th className="px-3 py-2">Material Coord.</th>
                  <th className="px-3 py-2 text-center">Team Size</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={8} className="text-center py-8 text-slate-400">No projects match</td></tr>
                )}
                {filtered.map((p) => (
                  <tr key={p.id} className="border-b hover:bg-slate-50/50" data-testid={`pt-row-${p.id}`}>
                    <td className="px-3 py-2">
                      <div className="font-mono text-xs text-primary">{p.code}</div>
                      <div className="font-medium">{p.name}</div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <div>{p.client || "—"}</div>
                      <div className="text-muted-foreground">{p.site || "—"}</div>
                    </td>
                    <td className="px-3 py-2">{p.manager || <i className="text-muted-foreground">—</i>}</td>
                    <td className="px-3 py-2">{p.site_supervisor || <i className="text-muted-foreground">—</i>}</td>
                    <td className="px-3 py-2">{p.safety_officer || <i className="text-muted-foreground">—</i>}</td>
                    <td className="px-3 py-2">{p.material_coordinator || <i className="text-muted-foreground">—</i>}</td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center text-xs gap-1 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">{teamCount(p)} / 6</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canWrite && (
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(p); setForm(p); }} data-testid={`pt-edit-${p.id}`}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Project Team · {editing?.code}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Project Manager"><Input value={form.manager || ""} onChange={(e) => setForm({ ...form, manager: e.target.value })} data-testid="pt-form-pm" /></F>
            <F label="Site Supervisor"><Input value={form.site_supervisor || ""} onChange={(e) => setForm({ ...form, site_supervisor: e.target.value })} data-testid="pt-form-ss" /></F>
            <F label="Safety Officer"><Input value={form.safety_officer || ""} onChange={(e) => setForm({ ...form, safety_officer: e.target.value })} data-testid="pt-form-so" /></F>
            <F label="Material Coordinator"><Input value={form.material_coordinator || ""} onChange={(e) => setForm({ ...form, material_coordinator: e.target.value })} data-testid="pt-form-mc" /></F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="pt-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
function F({ label, children }) {
  return <div><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>;
}
