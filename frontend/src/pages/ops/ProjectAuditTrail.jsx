/**
 * Project Audit Trail · surfaces audit_logs entries for project-related resources.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { History, RefreshCcw, Search } from "lucide-react";

const ACTION_TONES = {
  create: "bg-emerald-50 text-emerald-700 border-emerald-200",
  update: "bg-blue-50 text-blue-700 border-blue-200",
  delete: "bg-rose-50 text-rose-700 border-rose-200",
  status: "bg-violet-50 text-violet-700 border-violet-200",
  allocate: "bg-amber-50 text-amber-700 border-amber-200",
};

export default function ProjectAuditTrail() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [resFilter, setResFilter] = useState("");
  const load = async () => {
    try {
      const r = await api.get("/project-audit?limit=300");
      setRows(r.data);
    } catch (e) {
      setRows([]);
    }
  };
  useEffect(() => { load(); }, []);

  const resources = useMemo(() => [...new Set(rows.map((r) => r.resource))].sort(), [rows]);
  const filtered = useMemo(() => {
    const qq = q.toLowerCase().trim();
    return rows.filter((r) =>
      (!resFilter || r.resource === resFilter) &&
      (!qq || [r.user_name, r.user_email, r.action, r.resource, r.record_id].filter(Boolean).join(" ").toLowerCase().includes(qq))
    );
  }, [rows, q, resFilter]);

  return (
    <div className="p-6 space-y-4" data-testid="page-project-audit">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><History className="h-6 w-6 text-primary" /> Project Audit Trail</h1>
          <p className="text-sm text-muted-foreground">Every change across Projects, Handovers, Work Orders, Orders, Enquiries & Quotations — tamper-evident audit log.</p>
        </div>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
      </div>

      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="h-4 w-4 absolute left-2.5 top-3 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search user / action / record id…" className="pl-8 h-9" data-testid="pa-search" />
          </div>
          <select value={resFilter} onChange={(e) => setResFilter(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="pa-filter-resource">
            <option value="">All resources</option>
            {resources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Entries ({filtered.length})</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2 text-center">Action</th>
                  <th className="px-3 py-2">Resource</th>
                  <th className="px-3 py-2">Record</th>
                  <th className="px-3 py-2">IP</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-slate-400">No audit entries</td></tr>}
                {filtered.map((r, i) => (
                  <tr key={r.id || i} className="border-b hover:bg-slate-50/50">
                    <td className="px-3 py-2 text-xs font-mono">{(r.at || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="px-3 py-2">{r.user_name || r.user_email || "—"}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${ACTION_TONES[r.action] || "bg-slate-50 text-slate-600 border-slate-200"}`}>{r.action || "—"}</span>
                    </td>
                    <td className="px-3 py-2 text-xs uppercase">{r.resource}</td>
                    <td className="px-3 py-2 font-mono text-[10px]">{(r.record_id || "—").slice(0, 12)}</td>
                    <td className="px-3 py-2 text-xs">{r.ip || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
