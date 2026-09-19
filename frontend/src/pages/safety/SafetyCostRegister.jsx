/**
 * Safety Cost Register (Phase 4) — unified P&L of safety-related spend.
 * Includes penalties (source=penalty) and recoveries (is_recovery=true).
 * Costs ≥ threshold auto-route to Finance Head for approval.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Wallet, Plus, RefreshCcw, AlertTriangle } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const COST_SOURCES = [
  "ppe_purchase", "training", "medical", "incident", "audit", "equipment",
  "compliance", "corrective_action", "vendor_safety", "penalty", "recovery",
];

const EMPTY = {
  cost_source: "ppe_purchase", project_id: "", project_code: "",
  vendor_id: "", vendor_bill_ref: "", incident_id: "", audit_id: "",
  amount: "", is_recovery: false,
  cost_date: new Date().toISOString().slice(0, 10), description: "",
};

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function SafetyCostRegister() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [filterSource, setFilterSource] = useState("");

  const load = async () => {
    try {
      const q = filterSource ? `?cost_source=${encodeURIComponent(filterSource)}` : "";
      const [a, b] = await Promise.all([api.get(`/safety/costs${q}`), lookupGet("/projects")]);
      setRows(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [filterSource]);

  const totals = useMemo(() => {
    let cost = 0, penalty = 0, recovery = 0, approvalPending = 0;
    for (const r of rows) {
      const amt = Number(r.amount || 0);
      if (r.is_recovery) recovery += amt;
      else {
        cost += amt;
        if (r.cost_source === "penalty") penalty += amt;
      }
      if (r.approval_id) approvalPending += 1;
    }
    return { cost, penalty, recovery, approvalPending, net: cost - recovery };
  }, [rows]);

  const save = async () => {
    try {
      const payload = { ...form, amount: Number(form.amount) };
      Object.keys(payload).forEach((k) => { if (payload[k] === "") delete payload[k]; });
      const r = await api.post(`/safety/costs`, payload);
      if (r.data.approval_id) toast.success("Recorded · sent to Finance Head for approval");
      else toast.success("Recorded");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="safety-cost-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Wallet className="h-6 w-6 text-red-600" /> Safety Cost Register
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            PPE · Training · Medical · Incidents · Audits · Compliance · Vendor · Penalties · Recoveries. High-value entries auto-route to Finance Head.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="cost-new">
            <Plus className="h-4 w-4 mr-1" /> New Cost / Recovery
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="border rounded-sm p-3 bg-card"><div className="text-[10px] uppercase text-slate-500">Total Cost</div><div className="text-xl font-bold text-red-700">{inr(totals.cost)}</div></div>
        <div className="border rounded-sm p-3 bg-card"><div className="text-[10px] uppercase text-slate-500">Penalties</div><div className="text-xl font-bold text-amber-700">{inr(totals.penalty)}</div></div>
        <div className="border rounded-sm p-3 bg-card"><div className="text-[10px] uppercase text-slate-500">Recovery</div><div className="text-xl font-bold text-emerald-700">{inr(totals.recovery)}</div></div>
        <div className="border rounded-sm p-3 bg-card"><div className="text-[10px] uppercase text-slate-500">Net (Cost − Recovery)</div><div className="text-xl font-bold text-slate-900">{inr(totals.net)}</div></div>
      </div>

      <div className="flex items-center gap-2">
        <Label className="text-xs">Filter by source:</Label>
        <select className="border rounded h-9 px-2 text-sm" value={filterSource} onChange={(e) => setFilterSource(e.target.value)} data-testid="cost-filter">
          <option value="">— All —</option>
          {COST_SOURCES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
        </select>
        {totals.approvalPending > 0 && (
          <span className="ml-auto inline-flex items-center gap-1 text-xs text-amber-800 bg-amber-100 px-2 py-1 rounded">
            <AlertTriangle className="h-3 w-3" /> {totals.approvalPending} awaiting finance approval
          </span>
        )}
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Date</th>
              <th className="text-left px-3 py-2">Source</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Description</th>
              <th className="text-right px-3 py-2">Amount</th>
              <th className="text-center px-3 py-2">Type</th>
              <th className="text-center px-3 py-2">Approval</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-slate-400">No safety cost entries.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`cost-row-${r.id}`}>
                <td className="px-3 py-2">{r.cost_date}</td>
                <td className="px-3 py-2 capitalize">{(r.cost_source || "").replace(/_/g, " ")}</td>
                <td className="px-3 py-2">{r.project_code || "—"}</td>
                <td className="px-3 py-2 max-w-sm text-slate-600">{r.description || "—"}</td>
                <td className="px-3 py-2 text-right font-mono">{inr(r.amount)}</td>
                <td className="px-3 py-2 text-center">
                  {r.is_recovery ? (
                    <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">Recovery</span>
                  ) : (
                    <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded bg-red-100 text-red-800">Cost</span>
                  )}
                </td>
                <td className="px-3 py-2 text-center text-xs">
                  {r.approval_id ? <span className="text-amber-700">Pending</span> : <span className="text-slate-400">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Safety Cost / Recovery Entry</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Cost Source</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.cost_source} onChange={(e) => setForm({ ...form, cost_source: e.target.value })} data-testid="cost-source">
                {COST_SOURCES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <Label>Amount (₹)</Label>
              <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="cost-amount" />
            </div>
            <div>
              <Label>Cost Date</Label>
              <Input type="date" value={form.cost_date} onChange={(e) => setForm({ ...form, cost_date: e.target.value })} />
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }}>
                <option value="">— Corporate —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Vendor Bill Ref (optional)</Label>
              <Input value={form.vendor_bill_ref} onChange={(e) => setForm({ ...form, vendor_bill_ref: e.target.value })} />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_recovery} onChange={(e) => setForm({ ...form, is_recovery: e.target.checked })} data-testid="cost-is-recovery" />
                <span>This is a recovery (credited, not spent)</span>
              </label>
            </div>
            <div className="col-span-2">
              <Label>Description</Label>
              <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="cost-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
