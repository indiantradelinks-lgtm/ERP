import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Activity, Cpu, HardDrive, Database, RefreshCw, Brush, Timer, AlertTriangle, MemoryStick } from "lucide-react";
import { toast } from "sonner";
import { fmtDT } from "@/lib/datetime";

const tone = (pct, warn, crit) =>
  pct >= crit ? "text-rose-600" : pct >= warn ? "text-amber-600" : "text-emerald-600";

function Metric({ icon: Icon, label, value, sub, cls = "", testid }) {
  return (
    <Card data-testid={testid}>
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-500">
          <Icon className="h-4 w-4" /> {label}
        </div>
        <div className={`mt-2 text-2xl font-semibold ${cls}`}>{value}</div>
        {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function ThresholdForm({ settings, onSaved }) {
  const [f, setF] = useState(settings);
  const [saving, setSaving] = useState(false);
  useEffect(() => setF(settings), [settings]);
  const num = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  const ret = (k) => (e) => setF({ ...f, retention: { ...f.retention, [k]: Number(e.target.value) } });
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/admin/system-health/settings", {
        ...f, alert_emails: (f.alert_emails_text ?? (f.alert_emails || []).join(", ")).split(",").map((s) => s.trim()).filter(Boolean),
      });
      onSaved(data); toast.success("Thresholds saved");
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };
  if (!f) return null;
  const fields = [
    ["mem_warn_pct", "Memory warn %"], ["mem_crit_pct", "Memory critical %"],
    ["disk_warn_pct", "Disk warn %"], ["disk_crit_pct", "Disk critical %"],
    ["db_warn_mb", "DB size warn (MB)"], ["slow_ms", "Slow request (ms)"], ["alert_cooldown_hours", "Alert cooldown (h)"],
  ];
  const rfields = [
    ["temp_file_hours", "Temp files older than (h)"], ["login_activity_days", "Login activity (days)"],
    ["notifications_read_days", "Read notifications (days)"],
    ["email_outbox_body_days", "Email bodies (days, headers kept)"],
  ];
  return (
    <Card data-testid="health-settings-card">
      <CardHeader><CardTitle className="text-base">Alert thresholds & retention policy</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {fields.map(([k, l]) => (
            <div key={k}><Label className="text-xs">{l}</Label>
              <Input type="number" value={f[k] ?? ""} onChange={num(k)} data-testid={`health-setting-${k}`} /></div>
          ))}
          <div className="col-span-2"><Label className="text-xs">Extra alert emails (comma separated)</Label>
            <Input value={f.alert_emails_text ?? (f.alert_emails || []).join(", ")}
              onChange={(e) => setF({ ...f, alert_emails_text: e.target.value })} data-testid="health-setting-emails" /></div>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Switch checked={!!f.retention_enabled} onCheckedChange={(v) => setF({ ...f, retention_enabled: v })} data-testid="health-retention-toggle" />
          <span className="text-sm">Automatic retention of technical logs (business & transaction data are never touched)</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {rfields.map(([k, l]) => (
            <div key={k}><Label className="text-xs">{l}</Label>
              <Input type="number" value={f.retention?.[k] ?? ""} onChange={ret(k)} data-testid={`health-retention-${k}`} /></div>
          ))}
        </div>
        <Button onClick={save} disabled={saving} data-testid="health-settings-save">{saving ? "Saving…" : "Save"}</Button>
      </CardContent>
    </Card>
  );
}

export default function SystemHealth() {
  const [snap, setSnap] = useState(null);
  const [settings, setSettings] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState("");

  const load = async () => {
    try {
      const [s, h] = await Promise.all([api.get("/admin/system-health"), api.get("/admin/system-health/history?days=7")]);
      setSnap(s.data); setSettings((prev) => prev || s.data.settings); setHist(h.data.map((r) => ({ ...r, t: new Date(r.at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) })));
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed to load system health"); }
  };
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);

  const act = async (label, url) => {
    setBusy(label);
    try { const { data } = await api.post(url); toast.success(`${label}: ${JSON.stringify(data).slice(0, 160)}`); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || `${label} failed`); }
    finally { setBusy(""); }
  };

  if (!snap) return <div className="p-6 text-sm text-slate-500" data-testid="health-loading">Loading system health…</div>;
  const p = snap.process, st = snap.settings, d = snap.disk.app, dbm = snap.db.data_mb + snap.db.index_mb;

  return (
    <div className="p-4 md:p-6 space-y-6" data-testid="system-health-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2"><Activity className="h-6 w-6" /> System Health</h1>
          <p className="text-sm text-slate-500">Backend memory, CPU, disk, database and API response times — sampled every 5 minutes, 30-day history. Last snapshot {fmtDT(snap.at)}.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="health-refresh"><RefreshCw className="h-4 w-4 mr-1" />Refresh</Button>
          <Button variant="outline" size="sm" disabled={!!busy} onClick={() => act("Trim memory", "/admin/system-health/trim-memory")} data-testid="health-trim"><MemoryStick className="h-4 w-4 mr-1" />Trim memory</Button>
          <Button variant="outline" size="sm" disabled={!!busy} onClick={() => act("Housekeeping", "/admin/system-health/housekeeping/run")} data-testid="health-housekeeping"><Brush className="h-4 w-4 mr-1" />Run housekeeping</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Metric icon={MemoryStick} label="Memory" value={`${p.rss_mb} MB`} sub={`${p.mem_pct ?? "—"}% of ${p.mem_limit_mb} MB limit`} cls={tone(p.mem_pct || 0, st.mem_warn_pct, st.mem_crit_pct)} testid="health-metric-memory" />
        <Metric icon={Cpu} label="CPU" value={`${p.cpu_pct_of_quota}%`} sub={`of ${p.cpu_quota_cores} core quota · loop lag ${p.loop_lag_ewma_ms} ms`} cls={tone(p.cpu_pct_of_quota, 70, 90)} testid="health-metric-cpu" />
        <Metric icon={HardDrive} label="Disk" value={`${d.pct}%`} sub={`${d.used_gb} / ${d.total_gb} GB on /app`} cls={tone(d.pct, st.disk_warn_pct, st.disk_crit_pct)} testid="health-metric-disk" />
        <Metric icon={Database} label="Database" value={`${dbm.toFixed(0)} MB`} sub={`${snap.db.collections} collections · ${snap.db.indexes} indexes · ${snap.db.connections ?? "—"} conns`} cls={tone(dbm, st.db_warn_mb * 0.75, st.db_warn_mb)} testid="health-metric-db" />
        <Metric icon={Timer} label="API p95" value={`${snap.requests.p95_ms} ms`} sub={`avg ${snap.requests.avg_ms} ms · ${snap.requests.count} requests · ${snap.requests.errors_5xx} errors`} cls={tone(snap.requests.p95_ms, 800, st.slow_ms)} testid="health-metric-api" />
        <Metric icon={Activity} label="Process" value={`${p.uptime_min} min up`} sub={`${snap.scheduler.leader ? "scheduler leader" : "standby replica"} · AI lib in-process: ${p.litellm_loaded ? "YES" : "no"}`} cls={p.litellm_loaded ? "text-rose-600" : ""} testid="health-metric-process" />
      </div>

      <Card data-testid="health-history-card">
        <CardHeader><CardTitle className="text-base">Last 7 days — memory %, CPU %, API p95 (ms ÷ 10)</CardTitle></CardHeader>
        <CardContent className="h-64">
          {hist.length === 0 ? <div className="text-sm text-slate-500">No samples yet — the first sample is taken within 5 minutes of startup.</div> : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hist.map((r) => ({ ...r, p95_10: Math.round((r.p95_ms || 0) / 10) }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Line type="monotone" dataKey="mem_pct" name="Memory %" stroke="#0f766e" dot={false} />
                <Line type="monotone" dataKey="cpu_pct" name="CPU %" stroke="#b45309" dot={false} />
                <Line type="monotone" dataKey="p95_10" name="p95 ms/10" stroke="#1d4ed8" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card data-testid="health-slow-card">
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Timer className="h-4 w-4" /> Slow requests (≥ {st.slow_ms} ms, this process)</CardTitle></CardHeader>
          <CardContent>
            {snap.slow_requests.length === 0 ? <div className="text-sm text-slate-500" data-testid="health-slow-empty">None recorded since start.</div> : (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-slate-500"><th>When</th><th>Request</th><th className="text-right">ms</th><th className="text-right">Status</th></tr></thead>
                <tbody>{snap.slow_requests.map((r, i) => (
                  <tr key={i} className="border-t"><td className="py-1">{fmtDT(r.at)}</td><td className="font-mono break-all">{r.method} {r.route || r.path}</td><td className="text-right font-semibold">{r.ms}</td><td className="text-right">{r.status}</td></tr>
                ))}</tbody>
              </table>
            )}
          </CardContent>
        </Card>
        <Card data-testid="health-alerts-card">
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Alerts & housekeeping</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {snap.recent_alerts.length === 0 ? <div className="text-slate-500">No threshold alerts raised.</div> :
              snap.recent_alerts.map((a) => (
                <div key={a.key} className="flex items-start gap-2">
                  <Badge className={a.level === "critical" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}>{a.level}</Badge>
                  <div><div className="font-medium">{a.title}</div><div className="text-xs text-slate-500">{a.message} · {fmtDT(a.last_sent)} · ×{a.count}</div></div>
                </div>
              ))}
            <div className="border-t pt-3 text-xs text-slate-600" data-testid="health-last-housekeeping">
              <span className="font-medium">Last housekeeping:</span>{" "}
              {snap.last_housekeeping ? `${fmtDT(snap.last_housekeeping.at)} — temp files removed ${snap.last_housekeeping.temp?.removed ?? 0} (${snap.last_housekeeping.temp?.freed_mb ?? 0} MB), login activity ${snap.last_housekeeping.login_activity_deleted ?? 0}, notifications ${snap.last_housekeeping.notifications_deleted ?? 0}, email bodies pruned ${snap.last_housekeeping.email_bodies_pruned ?? 0}` : "never run (scheduled daily 20:30 UTC)"}
            </div>
          </CardContent>
        </Card>
      </div>

      <ThresholdForm settings={settings} onSaved={(s) => { setSettings(s); setSnap({ ...snap, settings: s }); }} />
    </div>
  );
}
