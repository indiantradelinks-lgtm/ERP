/**
 * Minimum Wage Master — state / skill / designation wise wage rates with
 * seed defaults, Excel export and full CRUD (HR write, super_admin delete).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeIndianRupee, Download, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const SKILLS = [
  { value: "unskilled", label: "Unskilled" },
  { value: "semi_skilled", label: "Semi-Skilled" },
  { value: "skilled", label: "Skilled" },
  { value: "highly_skilled", label: "Highly Skilled" },
  { value: "clerical", label: "Clerical / Non-Technical" },
];
const skillLabel = (v) => SKILLS.find((s) => s.value === v)?.label || v;
const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;
const WRITE_ROLES = ["super_admin", "director", "general_manager", "hr_executive"];

const blank = { state: "", zone: "", skill_category: "unskilled", designation: "", wage_per_day: "", wage_per_month: "", vda_per_month: "", effective_from: "", notes: "", active: true };

export default function MinimumWages() {
  const { user } = useAuth();
  const canWrite = WRITE_ROLES.includes(user?.role);
  const [rows, setRows] = useState([]);
  const [state, setState] = useState("");
  const [skill, setSkill] = useState("");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/hr/minimum-wages", { params: { state: state || undefined, skill_category: skill || undefined, q: q || undefined } });
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  }, [state, skill, q]);
  useEffect(() => { load(); }, [load]);

  const states = useMemo(() => [...new Set(rows.map((r) => r.state))].sort(), [rows]);

  const seed = async () => {
    try {
      const r = await api.post("/hr/minimum-wages/seed-defaults");
      toast.success(`${r.data.created} standard rate(s) added — review & adjust as per latest notifications`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Seed failed"); }
  };

  const exportXlsx = async () => {
    try {
      const r = await api.get("/hr/minimum-wages/export", { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = "minimum_wage_master.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const del = async (r) => {
    if (!window.confirm(`Delete ${r.state} / ${skillLabel(r.skill_category)}${r.designation ? ` / ${r.designation}` : ""}?`)) return;
    try { await api.delete(`/hr/minimum-wages/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="minimum-wages-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · HR · Masters</div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2"><BadgeIndianRupee className="h-7 w-7 text-primary" /> Minimum Wage Master</h1>
          <p className="text-sm text-slate-600 mt-1">State-wise, skill-wise & designation-wise statutory wage rates. Designation rows override the skill-category rate.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" onClick={exportXlsx} data-testid="mw-export-btn"><Download className="h-4 w-4 mr-1.5" /> Excel</Button>
          {canWrite && (
            <>
              <Button variant="outline" onClick={seed} data-testid="mw-seed-btn"><Sparkles className="h-4 w-4 mr-1.5" /> Seed Standard Rates</Button>
              <Button onClick={() => setEdit({ ...blank })} data-testid="mw-add-btn"><Plus className="h-4 w-4 mr-1.5" /> Add Rate</Button>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-2 items-end flex-wrap bg-card border border-border rounded-sm p-3">
        <div><Label className="text-[10px] uppercase tracking-wider">State</Label>
          <select value={state} onChange={(e) => setState(e.target.value)} className="h-9 mt-1 w-44 rounded-sm border border-input bg-background px-2 text-sm" data-testid="mw-filter-state">
            <option value="">All states</option>
            {states.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Skill Category</Label>
          <select value={skill} onChange={(e) => setSkill(e.target.value)} className="h-9 mt-1 w-48 rounded-sm border border-input bg-background px-2 text-sm" data-testid="mw-filter-skill">
            <option value="">All skills</option>
            {SKILLS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select></div>
        <div><Label className="text-[10px] uppercase tracking-wider">Search</Label>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="State / designation / notes" className="h-9 mt-1 w-56" data-testid="mw-search" /></div>
        {(state || skill || q) && (
          <Button variant="ghost" size="sm" className="h-9" onClick={() => { setState(""); setSkill(""); setQ(""); }} data-testid="mw-clear"><X className="h-4 w-4 mr-1" /> Clear</Button>
        )}
      </div>

      <div className="border border-border rounded-sm overflow-x-auto bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">State</th>
              <th className="text-left px-3 py-2">Zone</th>
              <th className="text-left px-3 py-2">Skill Category</th>
              <th className="text-left px-3 py-2">Designation</th>
              <th className="text-right px-3 py-2">Wage / Day</th>
              <th className="text-right px-3 py-2">Wage / Month</th>
              <th className="text-right px-3 py-2">VDA / Month</th>
              <th className="text-left px-3 py-2">Effective From</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2">Notes</th>
              {canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={11} className="text-center py-10 text-slate-400">
                No wage rates yet{canWrite ? " — use “Seed Standard Rates” or “Add Rate”." : "."}
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`mw-row-${r.id}`}>
                <td className="px-3 py-1.5 font-medium">{r.state}</td>
                <td className="px-3 py-1.5 text-xs">{r.zone || "—"}</td>
                <td className="px-3 py-1.5">{skillLabel(r.skill_category)}</td>
                <td className="px-3 py-1.5 text-xs">{r.designation || "—"}</td>
                <td className="px-3 py-1.5 text-right tabular font-semibold">{inr(r.wage_per_day)}</td>
                <td className="px-3 py-1.5 text-right tabular">{inr(r.wage_per_month)}</td>
                <td className="px-3 py-1.5 text-right tabular">{r.vda_per_month ? inr(r.vda_per_month) : "—"}</td>
                <td className="px-3 py-1.5 text-xs">{r.effective_from || "—"}</td>
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase ${r.active !== false ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "bg-slate-100 border-slate-300 text-slate-500"}`}>{r.active !== false ? "Active" : "Inactive"}</span>
                </td>
                <td className="px-3 py-1.5 text-xs max-w-[220px] truncate" title={r.notes}>{r.notes || "—"}</td>
                {canWrite && (
                  <td className="px-3 py-1.5 text-right whitespace-nowrap">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm mr-1" onClick={() => setEdit({ ...r })} data-testid={`mw-edit-${r.id}`}><Pencil className="h-3 w-3" /></Button>
                    {user?.role === "super_admin" || user?.role === "hr_executive" ? (
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-red-600 border-red-300" onClick={() => del(r)} data-testid={`mw-delete-${r.id}`}><Trash2 className="h-3 w-3" /></Button>
                    ) : null}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {edit && <WageDialog row={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function WageDialog({ row, onClose, onSaved }) {
  const [form, setForm] = useState(row);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.state?.trim()) { toast.error("State is required"); return; }
    if (!Number(form.wage_per_day) && !Number(form.wage_per_month)) { toast.error("Enter wage per day or per month"); return; }
    setSaving(true);
    const body = { ...form, wage_per_day: Number(form.wage_per_day) || 0, wage_per_month: Number(form.wage_per_month) || 0, vda_per_month: Number(form.vda_per_month) || 0 };
    try {
      if (form.id) await api.put(`/hr/minimum-wages/${form.id}`, body);
      else await api.post("/hr/minimum-wages", body);
      toast.success("Saved");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg bg-white dark:bg-slate-900" data-testid="mw-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">{form.id ? "Edit Wage Rate" : "Add Wage Rate"}</DialogTitle>
          <DialogDescription>Leave Designation blank for the general skill-category rate. Day/Month auto-derive from each other (26-day convention).</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="text-xs">State *</Label>
            <Input value={form.state} onChange={(e) => set("state", e.target.value)} placeholder="e.g. Delhi" className="h-9 mt-1" data-testid="mw-form-state" /></div>
          <div><Label className="text-xs">Zone (optional)</Label>
            <Input value={form.zone} onChange={(e) => set("zone", e.target.value)} placeholder="e.g. Zone I" className="h-9 mt-1" data-testid="mw-form-zone" /></div>
          <div><Label className="text-xs">Skill Category *</Label>
            <select value={form.skill_category} onChange={(e) => set("skill_category", e.target.value)} className="h-9 mt-1 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="mw-form-skill">
              {SKILLS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select></div>
          <div><Label className="text-xs">Designation (optional override)</Label>
            <Input value={form.designation} onChange={(e) => set("designation", e.target.value)} placeholder="e.g. Scaffolder, Welder" className="h-9 mt-1" data-testid="mw-form-designation" /></div>
          <div><Label className="text-xs">Wage / Day (₹)</Label>
            <Input type="number" min="0" value={form.wage_per_day} onChange={(e) => set("wage_per_day", e.target.value)} className="h-9 mt-1 text-right" data-testid="mw-form-day" /></div>
          <div><Label className="text-xs">Wage / Month (₹)</Label>
            <Input type="number" min="0" value={form.wage_per_month} onChange={(e) => set("wage_per_month", e.target.value)} className="h-9 mt-1 text-right" data-testid="mw-form-month" /></div>
          <div><Label className="text-xs">VDA / Month (₹)</Label>
            <Input type="number" min="0" value={form.vda_per_month} onChange={(e) => set("vda_per_month", e.target.value)} className="h-9 mt-1 text-right" data-testid="mw-form-vda" /></div>
          <div><Label className="text-xs">Effective From</Label>
            <Input type="date" value={form.effective_from} onChange={(e) => set("effective_from", e.target.value)} className="h-9 mt-1" data-testid="mw-form-effective" /></div>
          <div className="col-span-2"><Label className="text-xs">Notes</Label>
            <Input value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Notification reference, remarks…" className="h-9 mt-1" data-testid="mw-form-notes" /></div>
          <label className="flex items-center gap-2 text-sm col-span-2">
            <input type="checkbox" checked={form.active !== false} onChange={(e) => set("active", e.target.checked)} data-testid="mw-form-active" /> Active
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="mw-form-cancel">Cancel</Button>
          <Button onClick={save} disabled={saving} data-testid="mw-form-save">{saving ? "Saving…" : "Save Rate"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
