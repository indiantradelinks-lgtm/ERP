import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Cloud, ShieldCheck, ShieldAlert, RefreshCw, Database, History,
  AlertTriangle, CheckCircle2, ExternalLink, Play,
} from "lucide-react";
import { toast } from "sonner";

const StatusPill = ({ ok, label }) =>
  ok ? (
    <Badge className="bg-emerald-100 text-emerald-700 border border-emerald-200" data-testid="onedrive-status-ok">
      <ShieldCheck className="h-3 w-3 mr-1" /> {label}
    </Badge>
  ) : (
    <Badge className="bg-rose-100 text-rose-700 border border-rose-200" data-testid="onedrive-status-bad">
      <ShieldAlert className="h-3 w-3 mr-1" /> {label}
    </Badge>
  );

export default function OneDriveSettings() {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({ tenant_id: "", client_id: "", client_secret: "", backup_user_upn: "", base_folder: "ITL-ERP-Backups", enabled: true });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [stats, setStats] = useState({ pending: 0, pushed: 0, failed: 0, total: 0 });
  const [queue, setQueue] = useState([]);
  const [backups, setBackups] = useState([]);
  const [tab, setTab] = useState("settings");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const pollRef = useRef(null);
  const prevPushedRef = useRef(0);
  const lastTickRef = useRef(Date.now());
  const [throughput, setThroughput] = useState(0); // files / minute

  const loadLight = async () => {
    try {
      const [st, q] = await Promise.all([
        api.get("/admin/onedrive/stats"),
        api.get("/admin/onedrive/queue?limit=50"),
      ]);
      const now = Date.now();
      const deltaPushed = (st.data.pushed || 0) - prevPushedRef.current;
      const deltaMin = (now - lastTickRef.current) / 60000;
      if (deltaMin > 0.1 && deltaPushed >= 0) setThroughput(Math.round(deltaPushed / deltaMin));
      prevPushedRef.current = st.data.pushed || 0;
      lastTickRef.current = now;
      setStats(st.data);
      setQueue(q.data);
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    if (autoRefresh) {
      pollRef.current = setInterval(loadLight, 5000);
      return () => clearInterval(pollRef.current);
    }
  }, [autoRefresh]);

  const load = async () => {
    setLoading(true);
    try {
      const [s, st, q, b] = await Promise.all([
        api.get("/admin/onedrive/settings"),
        api.get("/admin/onedrive/stats"),
        api.get("/admin/onedrive/queue?limit=50"),
        api.get("/admin/onedrive/backups"),
      ]);
      setSettings(s.data);
      setForm({
        tenant_id: s.data.tenant_id || "",
        client_id: s.data.client_id || "",
        client_secret: s.data.client_secret === "********" ? "" : (s.data.client_secret || ""),
        backup_user_upn: s.data.backup_user_upn || "",
        base_folder: s.data.base_folder || "ITL-ERP-Backups",
        enabled: s.data.enabled !== false,
      });
      setStats(st.data);
      setQueue(q.data);
      setBackups(b.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load OneDrive settings");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.tenant_id || !form.client_id || !form.backup_user_upn) {
      toast.error("Tenant ID, Client ID and Backup User UPN are required");
      return;
    }
    setSaving(true);
    try {
      await api.put("/admin/onedrive/settings", form);
      toast.success("Settings saved");
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const testConn = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post("/admin/onedrive/test-connection");
      setTestResult(data);
      if (data.ok) toast.success(`Connected: ${data.drive_name || "OneDrive"}`);
      else toast.error("Connection failed — see details below");
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test failed");
    } finally {
      setTesting(false);
    }
  };

  const processNow = async () => {
    try {
      await api.post("/admin/onedrive/process-now");
      toast.success("Push queue triggered — refresh in a moment");
      setTimeout(load, 3000);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const backupNow = async () => {
    try {
      await api.post("/admin/onedrive/backup-now");
      toast.success("DB backup scheduled — refresh in a moment");
      setTimeout(load, 5000);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const migrateAll = async () => {
    if (!confirm("Queue every existing file for OneDrive upload? This may take a while.")) return;
    try {
      const { data } = await api.post("/admin/onedrive/migrate-historical");
      toast.success(`Queued ${data.queued} files for migration`);
      setAutoRefresh(true);  // turn on live polling
      setTab("queue");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const retryItem = async (id) => {
    try {
      await api.post(`/admin/onedrive/retry/${id}`);
      toast.success("Retry queued");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading OneDrive settings…</div>;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" data-testid="onedrive-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Cloud className="h-6 w-6 text-blue-600" /> OneDrive Cloud Storage
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            One-way push of all ERP files + nightly database backups to a shared OneDrive.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill ok={settings?.configured} label={settings?.configured ? "Configured" : "Not configured"} />
          <StatusPill ok={settings?.last_test_ok} label={settings?.last_test_ok ? "Connection OK" : "Not tested"} />
        </div>
      </div>

      {/* Tab nav */}
      <div className="flex gap-2 border-b">
        {[
          { key: "settings", label: "Settings", icon: ShieldCheck },
          { key: "queue", label: `Push Queue (${stats.pending} pending · ${stats.failed} failed)`, icon: RefreshCw },
          { key: "backups", label: "DB Backups", icon: Database },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm flex items-center gap-2 border-b-2 transition ${tab === t.key ? "border-blue-600 text-blue-600" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            data-testid={`onedrive-tab-${t.key}`}
          >
            <t.icon className="h-4 w-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "settings" && (
        <Card>
          <CardHeader>
            <CardTitle>Azure App Registration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label>Directory (Tenant) ID</Label>
                <Input value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} placeholder="00000000-0000-0000-0000-000000000000" data-testid="onedrive-tenant-id" />
              </div>
              <div>
                <Label>Application (Client) ID</Label>
                <Input value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} data-testid="onedrive-client-id" />
              </div>
              <div className="md:col-span-2">
                <Label>Client Secret <span className="text-xs text-muted-foreground">(leave blank to keep existing)</span></Label>
                <Input type="password" value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} placeholder={settings?.configured ? "•••••••• (stored encrypted)" : "Paste secret value"} data-testid="onedrive-client-secret" />
              </div>
              <div>
                <Label>Backup User UPN <span className="text-xs text-muted-foreground">(licensed M365 account)</span></Label>
                <Input value={form.backup_user_upn} onChange={(e) => setForm({ ...form, backup_user_upn: e.target.value })} placeholder="backup@indiantradelinks.in" data-testid="onedrive-upn" />
              </div>
              <div>
                <Label>Base Folder</Label>
                <Input value={form.base_folder} onChange={(e) => setForm({ ...form, base_folder: e.target.value })} placeholder="ITL-ERP-Backups" data-testid="onedrive-base-folder" />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input type="checkbox" id="enabled" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              <Label htmlFor="enabled" className="font-normal">Enable one-way push to OneDrive</Label>
            </div>

            <div className="flex items-center gap-2">
              <Button onClick={save} disabled={saving} data-testid="onedrive-save-btn">{saving ? "Saving…" : "Save Settings"}</Button>
              <Button variant="outline" onClick={testConn} disabled={testing || !settings?.configured} data-testid="onedrive-test-btn">
                {testing ? "Testing…" : "Test Connection"}
              </Button>
            </div>

            {testResult && (
              <div className={`mt-4 p-4 rounded-md border text-sm ${testResult.ok ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`}>
                {testResult.ok ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 font-medium text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Connection successful</div>
                    <div className="text-xs text-muted-foreground">Drive: {testResult.drive_name} · Owner: {testResult.owner} · Type: {testResult.drive_type}</div>
                    {testResult.quota?.total && (
                      <div className="text-xs text-muted-foreground">Quota: {Math.round((testResult.quota.used || 0) / 1e9)} GB used of {Math.round(testResult.quota.total / 1e9)} GB</div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 font-medium text-rose-700"><AlertTriangle className="h-4 w-4" /> Connection failed</div>
                    <div className="text-xs font-mono whitespace-pre-wrap break-all">{testResult.error}</div>
                  </div>
                )}
              </div>
            )}

            <div className="mt-6 p-4 rounded-md bg-blue-50 border border-blue-200 text-xs space-y-2">
              <div className="font-medium text-blue-700">Setup checklist (Azure side)</div>
              <ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
                <li>Register an application in Microsoft Entra Admin Center (App Registrations).</li>
                <li>Under <strong>API Permissions</strong> → <em>Microsoft Graph</em> → add <code>Files.ReadWrite.All</code> (Application). Grant admin consent.</li>
                <li>Under <strong>Certificates &amp; Secrets</strong>, create a Client Secret and copy the <em>value</em>.</li>
                <li>Make sure the backup user account is licensed and has signed in once so OneDrive is provisioned.</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      )}

      {tab === "queue" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Push Queue</CardTitle>
            <div className="flex gap-2 items-center">
              <label className="text-xs flex items-center gap-1 cursor-pointer">
                <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} data-testid="onedrive-autorefresh" />
                Live (5s)
              </label>
              <Button size="sm" variant="outline" onClick={migrateAll} data-testid="onedrive-migrate-btn"><History className="h-4 w-4 mr-1" /> Migrate Historical Files</Button>
              <Button size="sm" onClick={processNow} data-testid="onedrive-process-btn"><Play className="h-4 w-4 mr-1" /> Process Now</Button>
            </div>
          </CardHeader>
          <CardContent>
            {(() => {
              const done = stats.pushed + stats.failed;
              const pct = stats.total ? Math.round((done / stats.total) * 100) : 0;
              const etaMin = throughput > 0 && stats.pending > 0 ? Math.ceil(stats.pending / throughput) : null;
              return stats.total > 0 ? (
                <div className="mb-4 p-3 border rounded-md bg-slate-50">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="font-medium">Overall progress · {done} / {stats.total} ({pct}%)</span>
                    <span className="text-muted-foreground">
                      {throughput > 0 ? `${throughput} files/min` : "—"}
                      {etaMin !== null && <> · ETA {etaMin < 60 ? `${etaMin}m` : `${Math.floor(etaMin / 60)}h ${etaMin % 60}m`}</>}
                    </span>
                  </div>
                  <Progress value={pct} className="h-2" data-testid="onedrive-progress" />
                </div>
              ) : null;
            })()}
            <div className="grid grid-cols-4 gap-3 mb-4">
              <div className="p-3 border rounded bg-amber-50 border-amber-200"><div className="text-xs text-muted-foreground">Pending</div><div className="text-2xl font-bold text-amber-700" data-testid="stat-pending">{stats.pending}</div></div>
              <div className="p-3 border rounded bg-emerald-50 border-emerald-200"><div className="text-xs text-muted-foreground">Pushed</div><div className="text-2xl font-bold text-emerald-700" data-testid="stat-pushed">{stats.pushed}</div></div>
              <div className="p-3 border rounded bg-rose-50 border-rose-200"><div className="text-xs text-muted-foreground">Failed</div><div className="text-2xl font-bold text-rose-700" data-testid="stat-failed">{stats.failed}</div></div>
              <div className="p-3 border rounded bg-slate-50 border-slate-200"><div className="text-xs text-muted-foreground">Total</div><div className="text-2xl font-bold" data-testid="stat-total">{stats.total}</div></div>
            </div>
            <div className="border rounded overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase">
                  <tr><th className="px-3 py-2 text-left">File ID</th><th className="px-3 py-2 text-left">Status</th><th className="px-3 py-2 text-left">Attempts</th><th className="px-3 py-2 text-left">Remote Path</th><th className="px-3 py-2 text-left">Error</th><th className="px-3 py-2 text-left">Action</th></tr>
                </thead>
                <tbody>
                  {queue.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">Queue is empty</td></tr>}
                  {queue.map((q) => (
                    <tr key={q.id} className="border-t" data-testid={`queue-row-${q.id}`}>
                      <td className="px-3 py-2 font-mono text-xs truncate max-w-[160px]">{q.file_id}</td>
                      <td className="px-3 py-2"><Badge className={q.status === "pushed" ? "bg-emerald-100 text-emerald-700" : q.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}>{q.status}</Badge></td>
                      <td className="px-3 py-2">{q.attempts || 0}</td>
                      <td className="px-3 py-2 text-xs truncate max-w-[260px]">
                        {q.web_url ? <a href={q.web_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline inline-flex items-center gap-1">{q.remote_path}<ExternalLink className="h-3 w-3" /></a> : (q.remote_path || "—")}
                      </td>
                      <td className="px-3 py-2 text-xs text-rose-600 truncate max-w-[200px]" title={q.error || ""}>{q.error || ""}</td>
                      <td className="px-3 py-2">{q.status === "failed" && <Button size="sm" variant="ghost" onClick={() => retryItem(q.id)} data-testid={`retry-${q.id}`}>Retry</Button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {tab === "backups" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Database Backups (nightly @ midnight IST)</CardTitle>
            <Button size="sm" onClick={backupNow} data-testid="onedrive-backup-now-btn"><Database className="h-4 w-4 mr-1" /> Backup Now</Button>
          </CardHeader>
          <CardContent>
            <div className="border rounded overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase">
                  <tr><th className="px-3 py-2 text-left">Date</th><th className="px-3 py-2 text-left">Filename</th><th className="px-3 py-2 text-left">Size</th><th className="px-3 py-2 text-left">Remote Path</th></tr>
                </thead>
                <tbody>
                  {backups.length === 0 && <tr><td colSpan={4} className="px-3 py-8 text-center text-muted-foreground">No backups yet</td></tr>}
                  {backups.map((b) => (
                    <tr key={b.id} className="border-t">
                      <td className="px-3 py-2">{new Date(b.at).toLocaleString()}</td>
                      <td className="px-3 py-2 font-mono text-xs">{b.filename}</td>
                      <td className="px-3 py-2">{(b.size / 1024 / 1024).toFixed(1)} MB</td>
                      <td className="px-3 py-2 text-xs">
                        {b.web_url ? <a href={b.web_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline inline-flex items-center gap-1">{b.remote_path}<ExternalLink className="h-3 w-3" /></a> : b.remote_path}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
