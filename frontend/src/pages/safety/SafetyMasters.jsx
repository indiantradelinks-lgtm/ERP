/**
 * Safety Masters — one page cycling through all 13 masters via a tab strip.
 * Each master shares the same simple shape (code / name / description /
 * severity / active), so we render a single generic table+form for all of
 * them and switch on the master slug.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, RefreshCcw, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const MASTER_TABS = [
  { slug: "hazard-categories",             label: "Hazard Category" },
  { slug: "risk-categories",               label: "Risk Category" },
  { slug: "control-measures",              label: "Control Measure" },
  { slug: "ppe-categories",                label: "PPE Category" },
  { slug: "work-permit-types",             label: "Work Permit Type" },
  { slug: "safety-training-types",         label: "Safety Training Type" },
  { slug: "incident-categories",           label: "Incident Category" },
  { slug: "observation-categories",        label: "Observation Category" },
  { slug: "corrective-action-categories",  label: "Corrective Action" },
  { slug: "inspection-checklists",         label: "Inspection Checklist" },
  { slug: "legal-compliance-requirements", label: "Legal Compliance" },
  { slug: "emergency-responses",           label: "Emergency Response" },
  { slug: "toolbox-talk-topics",           label: "Toolbox Talk Topic" },
];

const SEVERITY_OPTS = ["", "low", "medium", "high", "critical"];

const EMPTY = { code: "", name: "", description: "", severity: "", color: "", active: true };

export default function SafetyMasters() {
  const [active, setActive] = useState(MASTER_TABS[0].slug);
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [showInactive, setShowInactive] = useState(false);

  const loadCounts = () =>
    api.get("/safety/masters").then((r) => {
      const map = {};
      (r.data || []).forEach((x) => { map[x.slug] = x.active_count; });
      setCounts(map);
    }).catch(() => {});

  const loadRows = () =>
    api.get(`/safety/masters/${active}?include_inactive=${showInactive}`)
      .then((r) => setRows(r.data || []))
      .catch((e) => toast.error(e.response?.data?.detail || "Load failed"));

  useEffect(() => { loadCounts(); }, []);
  useEffect(() => { loadRows(); }, [active, showInactive]);

  const currentLabel = useMemo(() => MASTER_TABS.find((m) => m.slug === active)?.label || active, [active]);

  const save = async () => {
    if (!form.name?.trim()) { toast.error("Name is required"); return; }
    try {
      if (editing?.id) {
        await api.put(`/safety/masters/${active}/${editing.id}`, form);
        toast.success("Updated");
      } else {
        await api.post(`/safety/masters/${active}`, form);
        toast.success("Created");
      }
      setEditing(null); loadRows(); loadCounts();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Deactivate "${r.name}"? Master rows are never hard-deleted so history stays intact.`)) return;
    try {
      await api.delete(`/safety/masters/${active}/${r.id}`);
      toast.success("Deactivated"); loadRows(); loadCounts();
    } catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="safety-masters-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Database className="h-6 w-6 text-primary" /> Safety Master Data
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Reference lists that power HIRA, JSA, permits, PPE issue, incidents & inspections.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs flex items-center gap-1.5 text-muted-foreground">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              data-testid="masters-show-inactive"
            />
            Show inactive
          </label>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="masters-new">
            <Plus className="h-4 w-4 mr-1" /> New {currentLabel}
          </Button>
          <Button variant="outline" onClick={() => { loadRows(); loadCounts(); }}>
            <RefreshCcw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Tab strip */}
      <div className="border-b border-border overflow-x-auto">
        <div className="flex gap-1 min-w-max">
          {MASTER_TABS.map((t) => (
            <button
              key={t.slug}
              onClick={() => setActive(t.slug)}
              className={`px-3 py-2 text-xs whitespace-nowrap border-b-2 transition-colors ${
                active === t.slug
                  ? "border-primary text-primary font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
              data-testid={`masters-tab-${t.slug}`}
            >
              {t.label}
              <span className="ml-1.5 text-[10px] text-muted-foreground tabular">{counts[t.slug] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2 w-32">Code</th>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2 w-32">Severity</th>
              <th className="text-left px-3 py-2">Description</th>
              <th className="text-center px-3 py-2 w-24">Active</th>
              <th className="text-right px-3 py-2 w-24"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="text-center py-8 text-slate-400">No rows in this master yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/50" data-testid={`masters-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.code || "—"}</td>
                <td className="px-3 py-2 font-medium">{r.name}</td>
                <td className="px-3 py-2 text-xs uppercase tracking-wider">{r.severity || "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{r.description || ""}</td>
                <td className="px-3 py-2 text-center text-xs">
                  {r.active ? <span className="text-emerald-700">✓</span> : <span className="text-slate-400">✗</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditing(r); setForm({ ...EMPTY, ...r }); }} data-testid={`masters-edit-${r.id}`}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r)} data-testid={`masters-del-${r.id}`}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing?.id ? "Edit" : "New"} — {currentLabel}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Code</Label>
              <Input value={form.code || ""} onChange={(e) => setForm({ ...form, code: e.target.value })} data-testid="masters-form-code" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Severity</Label>
              <select
                value={form.severity || ""}
                onChange={(e) => setForm({ ...form, severity: e.target.value })}
                className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm"
                data-testid="masters-form-severity"
              >
                {SEVERITY_OPTS.map((s) => <option key={s} value={s}>{s || "— none —"}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Name *</Label>
              <Input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="masters-form-name" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px] uppercase tracking-wider">Description</Label>
              <Textarea rows={3} value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="col-span-2 flex items-center gap-2">
              <input
                type="checkbox"
                id="masters-form-active"
                checked={!!form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })}
                data-testid="masters-form-active"
              />
              <label htmlFor="masters-form-active" className="text-sm">Active</label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="masters-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
