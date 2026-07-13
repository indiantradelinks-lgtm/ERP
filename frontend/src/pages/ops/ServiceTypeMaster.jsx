/**
 * Service Type Master · Projects & Operations
 * Manages the company's offered services (scaffolding, painting, roof sheeting,
 * rope access, manpower deployment, material supply, site execution).
 *
 * Backend: /api/proj-masters/service-types
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, RefreshCcw, Wrench, BarChart3 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const BILLING_UOMS = ["sqm", "lm", "cum", "manday", "MT", "LS", "nos"];
const CATEGORIES = ["service", "material", "manpower", "safety"];
const EMPTY = {
  code: "", name: "", category: "service", billing_uom: "LS",
  default_rate: 0, description: "", sla_days: 0, is_active: true,
};

export default function ServiceTypeMaster() {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth() || {};
  const canWrite = ["super_admin", "director", "general_manager", "dept_head"].includes(user?.role);

  const load = async () => {
    try {
      const [a, b] = await Promise.all([
        api.get("/proj-masters/service-types"),
        api.get("/proj-masters/service-types/stats").catch(() => ({ data: [] })),
      ]);
      setRows(a.data);
      setStats(b.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load");
    }
  };
  useEffect(() => { load(); }, []);

  const open = (row) => {
    setEditing(row);
    setForm(row ? { ...EMPTY, ...row } : EMPTY);
  };
  const save = async () => {
    if (!form.code?.trim() || !form.name?.trim()) {
      toast.error("Code and Name are required");
      return;
    }
    setBusy(true);
    try {
      if (editing?.id) {
        await api.put(`/proj-masters/service-types/${editing.id}`, form);
        toast.success("Updated");
      } else {
        await api.post("/proj-masters/service-types", form);
        toast.success("Created");
      }
      setEditing(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id, name) => {
    if (!window.confirm(`Delete service type "${name}"?`)) return;
    try {
      await api.delete(`/proj-masters/service-types/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  const total = rows.length;
  const active = rows.filter((r) => r.is_active).length;
  const categories = [...new Set(rows.map((r) => r.category))];

  return (
    <div className="p-6 space-y-4" data-testid="page-service-types">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wrench className="h-6 w-6 text-primary" />
            Service Type Master
          </h1>
          <p className="text-sm text-muted-foreground">All services offered by Indian Trade Links — used by Sales, Quotations & Project Master.</p>
        </div>
        {canWrite && (
          <Button onClick={() => open(null)} data-testid="st-new">
            <Plus className="h-4 w-4 mr-1" /> New Service Type
          </Button>
        )}
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total Service Types" value={total} />
        <Stat label="Active" value={active} />
        <Stat label="Categories" value={categories.length} />
        <Stat label="Most Used" value={stats[0] ? stats[0].name : "—"} small />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">All Service Types <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={load} data-testid="st-refresh">
              <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Code</th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Billing UOM</th>
                  <th className="px-3 py-2 text-right">Default Rate (₹)</th>
                  <th className="px-3 py-2 text-center">SLA (days)</th>
                  <th className="px-3 py-2 text-center">Active</th>
                  <th className="px-3 py-2 text-center">Usage</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-8 text-slate-400">No service types defined</td></tr>
                )}
                {rows.map((r) => {
                  const s = stats.find((x) => x.code === r.code);
                  const usage = s ? s.project_count + s.enquiry_count : 0;
                  return (
                    <tr key={r.id} className="border-b hover:bg-slate-50/50" data-testid={`st-row-${r.code}`}>
                      <td className="px-3 py-2 font-mono font-bold text-primary">{r.code}</td>
                      <td className="px-3 py-2 font-medium">{r.name}</td>
                      <td className="px-3 py-2 text-xs uppercase">{r.category}</td>
                      <td className="px-3 py-2">{r.billing_uom}</td>
                      <td className="px-3 py-2 text-right font-mono">{Number(r.default_rate || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-center">{r.sla_days || "—"}</td>
                      <td className="px-3 py-2 text-center">{r.is_active ? "✓" : "—"}</td>
                      <td className="px-3 py-2 text-center">
                        {usage > 0 ? (
                          <span className="inline-flex items-center text-xs gap-1 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">
                            <BarChart3 className="h-3 w-3" /> {usage}
                          </span>
                        ) : <span className="text-muted-foreground text-xs">0</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {canWrite && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => open(r)} data-testid={`st-edit-${r.code}`}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" onClick={() => remove(r.id, r.name)} data-testid={`st-del-${r.code}`}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Edit / New Dialog */}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editing?.id ? "Edit" : "New"} Service Type</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Code *">
              <Input value={form.code} maxLength={20} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                     placeholder="SCF" data-testid="st-form-code" />
            </Field>
            <Field label="Name *">
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                     placeholder="Scaffolding Services" data-testid="st-form-name" />
            </Field>
            <Field label="Category">
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="st-form-category">
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Billing UOM">
              <select value={form.billing_uom} onChange={(e) => setForm({ ...form, billing_uom: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="st-form-uom">
                {BILLING_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </Field>
            <Field label="Default Rate (₹ per UOM)">
              <Input type="number" value={form.default_rate} onChange={(e) => setForm({ ...form, default_rate: Number(e.target.value) || 0 })}
                     data-testid="st-form-rate" />
            </Field>
            <Field label="SLA (days)">
              <Input type="number" value={form.sla_days} onChange={(e) => setForm({ ...form, sla_days: Number(e.target.value) || 0 })}
                     data-testid="st-form-sla" />
            </Field>
            <Field label="Description" full>
              <Textarea value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })}
                         rows={3} data-testid="st-form-desc" />
            </Field>
            <Field label="Active" full>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                        data-testid="st-form-active" />
                Active (available for selection in Sales/Quotations/Projects)
              </label>
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} disabled={busy} data-testid="st-form-save">{busy ? "Saving…" : "Save"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function Stat({ label, value, small }) {
  return (
    <div className="border rounded-sm p-3 bg-card">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={small ? "text-base font-semibold truncate" : "text-2xl font-bold"}>{value}</div>
    </div>
  );
}
