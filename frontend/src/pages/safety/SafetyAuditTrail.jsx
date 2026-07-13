/**
 * Safety Audit Trail (Phase 5) — read-only immutable audit log viewer
 * with filters (record kind, action, user, date range).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { History, RefreshCcw } from "lucide-react";

export default function SafetyAuditTrail() {
  const [kinds, setKinds] = useState([]);
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [filters, setFilters] = useState({ record_kind: "", action: "", from: "", to: "", limit: 500 });

  const load = async () => {
    try {
      const q = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
      const [a, b] = await Promise.all([
        api.get(`/safety/audit-trail?${q.toString()}`),
        api.get("/safety/audit-trail/kinds"),
      ]);
      setRows(a.data.rows || []); setCount(a.data.count || 0); setKinds(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="audit-trail-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 5</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <History className="h-6 w-6 text-red-600" /> Safety Audit Trail
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Immutable log of every safety-record state change. No hard delete for approved safety transactions.
          </p>
        </div>
        <Button variant="outline" onClick={load} data-testid="trail-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <div>
          <Label className="text-[10px] uppercase">Record Kind</Label>
          <select className="w-full border rounded h-8 px-1 text-xs" value={filters.record_kind} onChange={(e) => setFilters({ ...filters, record_kind: e.target.value })} data-testid="trail-kind">
            <option value="">All</option>
            {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase">Action contains</Label>
          <Input className="h-8 text-xs" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} placeholder="e.g. close, submit" />
        </div>
        <div>
          <Label className="text-[10px] uppercase">From</Label>
          <Input type="date" className="h-8 text-xs" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} />
        </div>
        <div>
          <Label className="text-[10px] uppercase">To</Label>
          <Input type="date" className="h-8 text-xs" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} />
        </div>
        <div className="flex items-end">
          <Button className="w-full h-8" onClick={load} data-testid="trail-apply">Apply</Button>
        </div>
      </div>

      <div className="text-xs text-slate-500">{count} entries</div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <div className="max-h-[70vh] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">At</th>
                <th className="text-left px-3 py-2">Record</th>
                <th className="text-left px-3 py-2">Action</th>
                <th className="text-left px-3 py-2">By</th>
                <th className="text-left px-3 py-2">Role</th>
                <th className="text-left px-3 py-2">Meta</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-400">No audit entries.</td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={i} className="border-t hover:bg-slate-50/40" data-testid={`trail-row-${i}`}>
                  <td className="px-3 py-1.5 font-mono">{(r.at || "").slice(0, 19).replace("T", " ")}</td>
                  <td className="px-3 py-1.5">
                    <div className="font-semibold">{r.record_kind}</div>
                    <div className="text-slate-500 text-[10px] font-mono">{r.record_no || r.record_id?.slice(0, 8) || "—"}</div>
                  </td>
                  <td className="px-3 py-1.5"><span className="inline-block px-1.5 py-0.5 bg-slate-100 rounded font-mono text-[10px]">{r.action}</span></td>
                  <td className="px-3 py-1.5">{r.by_name || r.by_id?.slice(0, 8) || "—"}</td>
                  <td className="px-3 py-1.5 text-slate-500">{r.by_role || "—"}</td>
                  <td className="px-3 py-1.5 text-[10px] text-slate-500 max-w-xs truncate" title={JSON.stringify(r.meta || {})}>
                    {r.meta && Object.keys(r.meta).length ? JSON.stringify(r.meta) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
