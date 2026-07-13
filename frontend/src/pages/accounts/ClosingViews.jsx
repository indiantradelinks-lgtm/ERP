/**
 * Closing / Profitability / Controls · Phase 5 Views
 * ===================================================
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RefreshCcw, Lock, Unlock, FileDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { fmt } from "./AccountsViews";

const STATUS_COLORS = {
  profitable: "bg-emerald-100 text-emerald-800",
  at_risk:    "bg-amber-100 text-amber-800",
  loss:       "bg-rose-100 text-rose-800",
  idle:       "bg-slate-100 text-slate-600",
  neutral:    "bg-blue-100 text-blue-800",
};

const downloadCSV = async (key) => {
  try {
    const res = await api.get(`/closing/export/${key}`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${key}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast.success(`${key}.csv downloaded`);
  } catch (e) {
    toast.error(e.response?.data?.detail || "Export failed");
  }
};

/* ═══════════════════ Project Profitability ═══════════════════ */
export function ProjectProfitabilityView() {
  const [data, setData] = useState({ projects: [], summary: {} });
  const load = () => api.get("/closing/project-profitability").then(r => setData(r.data));
  useEffect(() => { load(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Project Profitability</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => downloadCSV("project-profitability")}><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2 mb-4">
          <div className="p-3 rounded-md border bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Projects</div><div className="text-lg font-bold">{data.summary?.projects_count || 0}</div></div>
          <div className="p-3 rounded-md border bg-emerald-50"><div className="text-[10px] uppercase text-slate-500">Profitable</div><div className="text-lg font-bold text-emerald-700">{data.summary?.profitable_count || 0}</div></div>
          <div className="p-3 rounded-md border bg-amber-50"><div className="text-[10px] uppercase text-slate-500">At Risk</div><div className="text-lg font-bold text-amber-700">{data.summary?.at_risk_count || 0}</div></div>
          <div className="p-3 rounded-md border bg-rose-50"><div className="text-[10px] uppercase text-slate-500">Loss</div><div className="text-lg font-bold text-rose-700">{data.summary?.loss_count || 0}</div></div>
          <div className="p-3 rounded-md border-2 border-slate-400 bg-white">
            <div className="text-[10px] uppercase text-slate-500">Net Profit</div>
            <div className={`text-lg font-bold tabular-nums ${data.summary?.total_profit >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmt(data.summary?.total_profit)}</div>
          </div>
        </div>
        <div className="border rounded-md overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Project</th><th className="text-right px-3 py-2">WO Value</th>
                <th className="text-right px-3 py-2">Revenue</th><th className="text-right px-3 py-2">Collected</th>
                <th className="text-right px-3 py-2">Material</th><th className="text-right px-3 py-2">Labour</th>
                <th className="text-right px-3 py-2">Vendor</th><th className="text-right px-3 py-2">Site/Logist/Safety</th>
                <th className="text-right px-3 py-2">Total Cost</th><th className="text-right px-3 py-2">Net Profit</th>
                <th className="text-right px-3 py-2">%</th><th className="text-center px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data.projects || []).map(p => (
                <tr key={p.project_id} className="border-t hover:bg-slate-50" data-testid={`close-prof-row-${p.project_code}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{p.project_code}{p.project_name && <span className="text-slate-500 ml-2">{p.project_name}</span>}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.wo_value)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-blue-700">{fmt(p.revenue_invoiced)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.revenue_collected)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.cost_material)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.cost_labour)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.cost_vendor)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.cost_site + p.cost_logistics + p.cost_safety)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(p.total_cost)}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums font-bold ${p.net_profit >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmt(p.net_profit)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{p.profit_pct}%</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[p.status] || ""}`}>{p.status}</span></td>
                </tr>
              ))}
              {(data.projects || []).length === 0 && <tr><td colSpan={12} className="text-center py-6 text-xs text-slate-400">No projects.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Balance Sheet ═══════════════════ */
export function BalanceSheetView() {
  const [data, setData] = useState({ assets: { rows: [], total: 0 }, liabilities: { rows: [], total: 0 }, equity: { rows: [], total: 0 } });
  const load = () => api.get("/closing/reports/balance-sheet").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Balance Sheet <span className="ml-2 text-xs text-slate-500 font-normal">as of {data.as_of}</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" onClick={() => downloadCSV("balance-sheet")}><FileDown className="h-3.5 w-3.5 mr-1" />CSV</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-4">
          {["assets", "liabilities", "equity"].map(side => (
            <div key={side}>
              <div className={`text-xs uppercase tracking-wider font-semibold mb-2 ${side === "assets" ? "text-blue-700" : side === "liabilities" ? "text-rose-700" : "text-violet-700"}`}>{side}</div>
              <table className="w-full text-sm border rounded-md overflow-hidden">
                <tbody>
                  {(data[side]?.rows || []).map(r => (
                    <tr key={r.code} className="border-b hover:bg-slate-50">
                      <td className="px-3 py-1 font-mono text-xs">{r.code}</td>
                      <td className="px-3 py-1 text-xs">{r.name}</td>
                      <td className="px-3 py-1 text-right tabular-nums">{fmt(r.amount)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-100 font-bold">
                  <tr><td colSpan={2} className="px-3 py-1.5">Total</td><td className="px-3 py-1.5 text-right tabular-nums">{fmt(data[side]?.total)}</td></tr>
                </tfoot>
              </table>
            </div>
          ))}
        </div>
        <div className={`mt-4 p-3 rounded-md ${data.balanced ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
          {data.balanced ? "✓ Balance Sheet is balanced" : `Diff: ${fmt(data.balance_diff)} (legacy single-sided JEs may explain this)`}
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Cash Flow Statement ═══════════════════ */
export function CashFlowView() {
  const [data, setData] = useState({ inflows: {}, outflows: {} });
  const [f, setF] = useState({ start: "", end: "" });
  const run = () => {
    const params = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    api.get(`/closing/reports/cash-flow?${params}`).then(r => setData(r.data));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Cash Flow Statement</CardTitle>
        <div className="flex gap-2">
          <Input type="date" className="h-8 w-36" value={f.start} onChange={e => setF({ ...f, start: e.target.value })} />
          <Input type="date" className="h-8 w-36" value={f.end} onChange={e => setF({ ...f, end: e.target.value })} />
          <Button size="sm" onClick={run}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 mb-4">
          {["operating", "investing", "financing"].map(cat => (
            <div key={cat} className="p-3 border rounded-md">
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{cat}</div>
              <div className="grid grid-cols-2 gap-1 text-sm mt-1">
                <div><span className="text-[10px] text-emerald-700">Inflow</span><div className="font-semibold tabular-nums text-emerald-700">{fmt(data.inflows?.[cat])}</div></div>
                <div><span className="text-[10px] text-rose-700">Outflow</span><div className="font-semibold tabular-nums text-rose-700">{fmt(data.outflows?.[cat])}</div></div>
              </div>
            </div>
          ))}
        </div>
        <div className="p-4 rounded-md border-2 bg-slate-50 grid grid-cols-4 gap-3 text-sm">
          <div><div className="text-[10px] uppercase text-slate-500">Net Operating</div><div className="font-bold tabular-nums">{fmt(data.net_operating)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-500">Net Investing</div><div className="font-bold tabular-nums">{fmt(data.net_investing)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-500">Net Financing</div><div className="font-bold tabular-nums">{fmt(data.net_financing)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-500">Net Cash Change</div><div className={`text-lg font-bold tabular-nums ${data.net_change >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmt(data.net_change)}</div></div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Month-End Closing ═══════════════════ */
export function MonthEndClosingView() {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState({ items: [], progress: 0, all_clear: false });
  const [locks, setLocks] = useState([]);
  const load = () => {
    api.get(`/closing/period/checklist?period=${period}`).then(r => setData(r.data));
    api.get("/closing/period/status").then(r => setLocks(r.data || []));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [period]);

  const lock = async () => {
    if (!window.confirm(`Lock ${period}? Normal users will be unable to backdate entries into this month.`)) return;
    try { await api.post("/closing/period/lock", { period, period_type: "month" }); toast.success("Period locked"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const unlock = async (p) => {
    const reason = window.prompt(`Unlock ${p.period}? Provide reason (min 5 chars):`);
    if (!reason || reason.length < 5) { toast.error("Reason required (min 5 chars)"); return; }
    try { await api.post("/closing/period/unlock", { period: p.period, period_type: p.period_type, reason }); toast.success("Unlocked"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Month-End Closing</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="2026-06" value={period} onChange={e => setPeriod(e.target.value)} className="h-8 w-32" data-testid="close-period" />
          <Button size="sm" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" disabled={!data.all_clear} onClick={lock} data-testid="close-lock"><Lock className="h-3.5 w-3.5 mr-1" />Lock Period</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex justify-between mb-1 text-sm"><span>Closing Progress · {period}</span><span className="font-bold">{data.progress}%</span></div>
          <div className="h-2 bg-slate-200 rounded overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${data.progress}%` }} /></div>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {(data.items || []).map(i => (
                <tr key={i.key} className="border-b hover:bg-slate-50">
                  <td className="px-3 py-1.5 text-center w-10">{i.done ? <CheckCircle2 className="h-4 w-4 text-emerald-600 inline" /> : <AlertTriangle className="h-4 w-4 text-amber-600 inline" />}</td>
                  <td className="px-3 py-1.5 font-semibold">{i.label}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-500">{i.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-600 font-semibold mb-2">Locked Periods</div>
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-3 py-1">Period</th><th className="text-left px-3 py-1">Type</th><th className="text-left px-3 py-1">Status</th><th className="text-left px-3 py-1">By</th><th className="text-left px-3 py-1">At</th><th></th></tr></thead>
              <tbody>
                {locks.map(l => (
                  <tr key={l.id} className="border-t">
                    <td className="px-3 py-1 font-mono">{l.period}</td>
                    <td className="px-3 py-1 text-xs">{l.period_type}</td>
                    <td className="px-3 py-1"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${l.status === "locked" ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800"}`}>{l.status}</span></td>
                    <td className="px-3 py-1 text-xs">{l.locked_by || l.unlocked_by}</td>
                    <td className="px-3 py-1 font-mono text-xs">{(l.locked_at || l.unlocked_at)?.slice(0, 19)?.replace("T", " ")}</td>
                    <td className="px-3 py-1 text-right">
                      {l.status === "locked" && <Button size="sm" variant="outline" onClick={() => unlock(l)}><Unlock className="h-3 w-3 mr-1" />Unlock</Button>}
                    </td>
                  </tr>
                ))}
                {locks.length === 0 && <tr><td colSpan={6} className="text-center py-4 text-xs text-slate-400">No locked periods.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ Alerts Centre ═══════════════════ */
export function AlertsCentreView() {
  const [data, setData] = useState({ alerts: [], count: 0 });
  const load = () => api.get("/closing/alerts").then(r => setData(r.data));
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Accounts Alerts Centre <span className="ml-2 text-sm text-slate-500 font-normal">{data.count} active</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        {(data.alerts || []).length === 0 && <div className="text-center py-8 text-xs text-emerald-600">✓ All clear — no alerts.</div>}
        <div className="space-y-2">
          {(data.alerts || []).map(a => (
            <div key={a.key} className={`p-3 rounded-md border flex items-center gap-2 ${a.severity === "high" ? "bg-rose-50 border-rose-300" : a.severity === "medium" ? "bg-amber-50 border-amber-300" : "bg-slate-50 border-slate-300"}`}>
              <AlertTriangle className={`h-4 w-4 ${a.severity === "high" ? "text-rose-700" : a.severity === "medium" ? "text-amber-700" : "text-slate-500"}`} />
              <span className="flex-1 text-sm">{a.label}</span>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">{a.severity}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
