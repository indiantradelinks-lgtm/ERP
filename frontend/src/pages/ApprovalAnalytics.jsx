import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { TrendingUp, Clock, AlertCircle, RotateCcw } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

export default function ApprovalAnalytics() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const { data } = await api.get(`/approvals/analytics?days=${days}`);
      setData(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [days]);

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  const t = data.totals;
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="approval-analytics">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-primary" /> Approval Analytics
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Cycle-time and bottleneck analysis across all approvals · last {days} days.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="border rounded-sm p-1 text-sm" data-testid="analytics-window">
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>1 year</option>
          </select>
          <Button variant="outline" onClick={load} disabled={busy}>Refresh</Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Kpi label="Total Approvals" value={t.approvals} icon={Clock} tone="bg-blue-50 border-blue-200 text-blue-900" />
        <Kpi label="Avg Cycle Days" value={t.avg_cycle_days} icon={Clock} tone="bg-emerald-50 border-emerald-200 text-emerald-900" />
        <Kpi label="p95 Cycle Days" value={t.p95_cycle_days} icon={Clock} tone="bg-amber-50 border-amber-200 text-amber-900" />
        <Kpi label="Resubmits" value={t.resubmits} icon={RotateCcw} tone="bg-purple-50 border-purple-200 text-purple-900" />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Rejections" value={t.rejections} icon={AlertCircle} tone="bg-rose-50 border-rose-200 text-rose-900" />
        <Kpi label="Info Requests" value={t.info_requests} icon={AlertCircle} tone="bg-amber-50 border-amber-200 text-amber-900" />
        <Kpi label="p50 Cycle Days" value={t.p50_cycle_days} icon={Clock} tone="bg-slate-50 border-slate-200 text-slate-900" />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Cycle Time by Approval Type</CardTitle></CardHeader>
        <CardContent style={{ height: 320 }} className="min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={(data.by_type || []).slice(0, 12)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="type" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="avg_days" name="Avg days" fill="#3b82f6" />
              <Bar dataKey="approved" name="Approved" fill="#10b981" />
              <Bar dataKey="rejected" name="Rejected" fill="#ef4444" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Bottleneck Roles (avg days spent at step)</CardTitle></CardHeader>
        <CardContent>
          <div className="border rounded-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left p-2">Role</th>
                  <th className="text-right p-2">Actions</th>
                  <th className="text-right p-2">Avg days at step</th>
                </tr>
              </thead>
              <tbody>
                {(data.bottleneck_roles || []).length === 0 && (
                  <tr><td colSpan={3} className="p-4 text-center text-muted-foreground">No data in this window.</td></tr>
                )}
                {(data.bottleneck_roles || []).map((b) => (
                  <tr key={b.role} className="border-t" data-testid={`bottleneck-row-${b.role}`}>
                    <td className="p-2 capitalize">{(b.role || "").replaceAll("_", " ")}</td>
                    <td className="p-2 text-right">{b.actions}</td>
                    <td className="p-2 text-right">
                      <Badge className={b.avg_days_at_step > 3 ? "bg-rose-100 text-rose-700" : b.avg_days_at_step > 1 ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}>
                        {b.avg_days_at_step}d
                      </Badge>
                    </td>
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

function Kpi({ label, value, icon: Icon, tone }) {
  return (
    <div className={`p-4 border rounded-sm ${tone}`}>
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 opacity-70" />
        <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
      </div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}
