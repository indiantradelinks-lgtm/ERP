/**
 * HR Masters — Designation Master (db.hr_designations via /api/hr1/designations)
 * and Skill / Trade Master (db.hr_skills via /api/hr1/skills).
 * These collections feed manpower dropdowns in Resource Planning, Resource Requests & Employees.
 */
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Plus, Pencil, Trash2, Search, BadgeCheck, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { api } from "@/lib/api";

const EMPTY_DESIG = { code: "", name: "", level: "", active: true };
const EMPTY_SKILL = { code: "", name: "", category: "", certification_required: false, safety_training_required: false, medical_fitness_required: false, active: true };

export default function HrMasters() {
  const location = useLocation();
  const [tab, setTab] = useState(new URLSearchParams(location.search).get("tab") === "skills" ? "skills" : "designations");
  const [desigs, setDesigs] = useState([]);
  const [skills, setSkills] = useState([]);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_DESIG);
  const isDesig = tab === "designations";

  const load = async () => {
    try {
      const [d, s] = await Promise.all([api.get("/hr1/designations"), api.get("/hr1/skills")]);
      setDesigs(d.data || []);
      setSkills(s.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load HR masters"); }
  };
  useEffect(() => { load(); }, []);

  const rows = useMemo(() => {
    const src = isDesig ? desigs : skills;
    const s = q.toLowerCase();
    return src.filter((r) => !s || (r.name || "").toLowerCase().includes(s) || (r.code || "").toLowerCase().includes(s));
  }, [isDesig, desigs, skills, q]);

  const openNew = () => { setEditing({}); setForm(isDesig ? EMPTY_DESIG : EMPTY_SKILL); };
  const openEdit = (r) => { setEditing(r); setForm({ ...(isDesig ? EMPTY_DESIG : EMPTY_SKILL), ...r }); };

  const save = async () => {
    if (!form.code?.trim() || !form.name?.trim()) { toast.error("Code and Name are required"); return; }
    const base = isDesig ? "/hr1/designations" : "/hr1/skills";
    try {
      if (editing?.id) await api.put(`${base}/${editing.id}`, form);
      else await api.post(base, form);
      toast.success(editing?.id ? "Updated" : "Created");
      setEditing(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.code} · ${r.name}?`)) return;
    const base = isDesig ? "/hr1/designations" : "/hr1/skills";
    try { await api.delete(`${base}/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const toggleActive = async (r) => {
    const base = isDesig ? "/hr1/designations" : "/hr1/skills";
    try {
      await api.put(`${base}/${r.id}`, { ...r, active: r.active === false });
      toast.success(r.active === false ? "Activated" : "Deactivated");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Update failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="hr-masters-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · HR · Masters</div>
          <h1 className="font-display font-black text-3xl tracking-tight">Designation & Skill Master</h1>
          <p className="text-sm text-slate-600 mt-1">Designations feed manpower dropdowns in Resource Planning, Resource Requests and Employee records.</p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input placeholder="Code / name…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8 w-56" data-testid="hrm-search" />
          </div>
          <Button onClick={openNew} data-testid="hrm-new">
            <Plus className="h-4 w-4 mr-1" /> New {isDesig ? "Designation" : "Skill"}
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="designations" data-testid="hrm-tab-designations"><BadgeCheck className="h-3.5 w-3.5 mr-1" />Designations ({desigs.length})</TabsTrigger>
          <TabsTrigger value="skills" data-testid="hrm-tab-skills"><Wrench className="h-3.5 w-3.5 mr-1" />Skills / Trades ({skills.length})</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Code</th>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">{isDesig ? "Level" : "Category"}</th>
              {!isDesig && <th className="text-left px-3 py-2">Requirements</th>}
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2 w-32">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400 text-sm">
                No {isDesig ? "designations" : "skills"} yet — click "New {isDesig ? "Designation" : "Skill"}" to add the first one.
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`hrm-row-${r.id}`}>
                <td className="px-3 py-2 font-mono-data text-xs">{r.code}</td>
                <td className="px-3 py-2 font-medium">{r.name}</td>
                <td className="px-3 py-2 text-xs">{(isDesig ? r.level : r.category) || "—"}</td>
                {!isDesig && (
                  <td className="px-3 py-2 text-[10px] text-slate-500">
                    {[r.certification_required && "Certification", r.safety_training_required && "Safety training", r.medical_fitness_required && "Medical fitness"].filter(Boolean).join(" · ") || "—"}
                  </td>
                )}
                <td className="px-3 py-2">
                  <button onClick={() => toggleActive(r)} title="Click to toggle"
                          className={`px-2 py-0.5 text-xs rounded border ${r.active === false ? "bg-zinc-100 text-zinc-600 border-zinc-300" : "bg-green-100 text-green-800 border-green-300"}`}
                          data-testid={`hrm-toggle-${r.id}`}>
                    {r.active === false ? "inactive" : "active"}
                  </button>
                </td>
                <td className="px-3 py-2 text-right">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEdit(r)} data-testid={`hrm-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-red-600" onClick={() => remove(r)} data-testid={`hrm-del-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing?.id ? "Edit" : "New"} {isDesig ? "Designation" : "Skill / Trade"}</DialogTitle>
            <DialogDescription className="sr-only">HR master record</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-[10px] uppercase tracking-wider">Code *</Label>
              <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} className="h-9 mt-1" placeholder={isDesig ? "WLD" : "TIG"} data-testid="hrm-form-code" />
            </div>
            <div><Label className="text-[10px] uppercase tracking-wider">Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="h-9 mt-1" placeholder={isDesig ? "Welder" : "TIG Welding"} data-testid="hrm-form-name" />
            </div>
            {isDesig ? (
              <div><Label className="text-[10px] uppercase tracking-wider">Level</Label>
                <Input value={form.level || ""} onChange={(e) => setForm({ ...form, level: e.target.value })} className="h-9 mt-1" placeholder="e.g. L2 / Senior" data-testid="hrm-form-level" />
              </div>
            ) : (
              <>
                <div><Label className="text-[10px] uppercase tracking-wider">Category</Label>
                  <Input value={form.category || ""} onChange={(e) => setForm({ ...form, category: e.target.value })} className="h-9 mt-1" placeholder="e.g. Welding" data-testid="hrm-form-category" />
                </div>
                <div className="col-span-2 flex flex-wrap gap-4 text-sm">
                  {[["certification_required", "Certification required"], ["safety_training_required", "Safety training required"], ["medical_fitness_required", "Medical fitness required"]].map(([k, label]) => (
                    <label key={k} className="flex items-center gap-1.5 cursor-pointer">
                      <input type="checkbox" checked={!!form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} className="h-4 w-4" /> {label}
                    </label>
                  ))}
                </div>
              </>
            )}
            <div className="flex items-end gap-2">
              <input id="hrm-active" type="checkbox" checked={form.active !== false} onChange={(e) => setForm({ ...form, active: e.target.checked })} className="h-4 w-4" data-testid="hrm-form-active" />
              <Label htmlFor="hrm-active" className="text-xs uppercase tracking-wider">Active</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="hrm-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
