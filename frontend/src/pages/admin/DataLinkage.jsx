import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Sheet, Database, Plug, RefreshCw, Trash2, ExternalLink,
  CheckCircle2, AlertTriangle, Search,
} from "lucide-react";
import { toast } from "sonner";

export default function DataLinkage() {
  const [tab, setTab] = useState("sheets");

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" data-testid="data-linkage-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Plug className="h-6 w-6 text-blue-600" /> Data Linkage
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Live Google Sheets feeds and Tally master sync. Cross-module record linking is exposed on every detail page via the Linked Records panel.
        </p>
      </div>

      <div className="flex gap-2 border-b">
        {[
          { key: "sheets", label: "Google Sheets", icon: Sheet },
          { key: "tally", label: "Tally Sync", icon: Database },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm flex items-center gap-2 border-b-2 transition ${tab === t.key ? "border-blue-600 text-blue-600" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            data-testid={`linkage-tab-${t.key}`}
          >
            <t.icon className="h-4 w-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "sheets" && <GoogleSheetsTab />}
      {tab === "tally" && <TallyTab />}
    </div>
  );
}

function GoogleSheetsTab() {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", csv_url: "", description: "" });
  const [adding, setAdding] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get("/linkage/sheets"); setChannels(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!form.name || !form.csv_url) { toast.error("Name and Published CSV URL required"); return; }
    setAdding(true);
    try {
      await api.post("/linkage/sheets", form);
      setForm({ name: "", csv_url: "", description: "" });
      toast.success("Sheet channel added");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setAdding(false); }
  };

  const removeChannel = async (id) => {
    if (!confirm("Remove this sheet channel?")) return;
    try { await api.delete(`/linkage/sheets/${id}`); toast.success("Removed"); await load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const previewChannel = async (id) => {
    setPreviewing(true); setPreview(null);
    try {
      const { data } = await api.get(`/linkage/sheets/${id}/data`);
      setPreview(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setPreviewing(false); }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Add Sheet Channel</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid md:grid-cols-3 gap-3">
            <div>
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Client Master Pricelist" data-testid="sheet-name" />
            </div>
            <div className="md:col-span-2">
              <Label>Published CSV URL <span className="text-xs text-muted-foreground">(File → Share → Publish to web → CSV)</span></Label>
              <Input value={form.csv_url} onChange={(e) => setForm({ ...form, csv_url: e.target.value })} placeholder="https://docs.google.com/spreadsheets/d/.../pub?output=csv" data-testid="sheet-url" />
            </div>
          </div>
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional description" data-testid="sheet-desc" />
          <Button onClick={add} disabled={adding} data-testid="sheet-add-btn">{adding ? "Adding…" : "Add Channel"}</Button>
          <div className="text-xs p-3 rounded bg-blue-50 border border-blue-200">
            <strong>How to publish a Google Sheet:</strong> Open your sheet → <em>File → Share → Publish to web</em> → Pick the tab → choose <em>Comma-separated values (.csv)</em> → Publish → copy the URL.
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Active Channels</CardTitle></CardHeader>
        <CardContent>
          {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : (
            <div className="border rounded">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">URL</th>
                    <th className="px-3 py-2 text-left">Last Synced</th>
                    <th className="px-3 py-2 text-left">Rows</th>
                    <th className="px-3 py-2 text-left">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.length === 0 && <tr><td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">No channels yet</td></tr>}
                  {channels.map((c) => (
                    <tr key={c.id} className="border-t" data-testid={`sheet-row-${c.id}`}>
                      <td className="px-3 py-2 font-medium">{c.name}</td>
                      <td className="px-3 py-2 text-xs"><a href={c.csv_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline inline-flex items-center gap-1 truncate max-w-[300px]">{c.csv_url.slice(0, 60)}…<ExternalLink className="h-3 w-3" /></a></td>
                      <td className="px-3 py-2 text-xs">{c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : "—"}</td>
                      <td className="px-3 py-2 text-xs">{c.last_row_count ?? "—"}</td>
                      <td className="px-3 py-2">
                        <Button size="sm" variant="outline" onClick={() => previewChannel(c.id)} disabled={previewing} data-testid={`sheet-preview-${c.id}`}><RefreshCw className="h-3 w-3 mr-1" />Preview</Button>
                        <Button size="sm" variant="ghost" className="text-rose-600 ml-1" onClick={() => removeChannel(c.id)} data-testid={`sheet-delete-${c.id}`}><Trash2 className="h-3 w-3" /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {preview && (
        <Card>
          <CardHeader>
            <CardTitle>Preview: {preview.name} <Badge variant="outline" className="ml-2">{preview.row_count} rows</Badge></CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto border rounded max-h-[400px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr>{preview.headers.map((h) => <th key={h} className="px-2 py-1.5 text-left font-semibold">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.data.slice(0, 50).map((row, i) => (
                    <tr key={`r-${i}`} className="border-t">
                      {preview.headers.map((h) => <td key={h} className="px-2 py-1">{row[h]}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.row_count > 50 && <div className="text-xs text-muted-foreground mt-2">Showing first 50 of {preview.row_count} rows</div>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TallyTab() {
  const [cfg, setCfg] = useState({ host: "localhost", port: 9000, company: "", enabled: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [ledgers, setLedgers] = useState([]);
  const [q, setQ] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [c, l] = await Promise.all([
        api.get("/linkage/tally/config"),
        api.get("/linkage/tally/ledgers"),
      ]);
      setCfg(c.data);
      setLedgers(l.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/linkage/tally/config", { host: cfg.host, port: Number(cfg.port), company: cfg.company, enabled: cfg.enabled });
      toast.success("Saved");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true); setTestResult(null);
    try {
      const { data } = await api.post("/linkage/tally/test");
      setTestResult(data);
      data.ok ? toast.success("Connected!") : toast.error("Failed — see details below");
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setTesting(false); }
  };

  const syncMasters = async () => {
    setSyncing(true);
    try {
      const { data } = await api.post("/linkage/tally/sync-masters");
      toast.success(`Synced ${data.ledger_count} ledgers`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setSyncing(false); }
  };

  const search = async () => {
    try {
      const { data } = await api.get(`/linkage/tally/ledgers?q=${encodeURIComponent(q)}`);
      setLedgers(data);
    } catch (e) { toast.error("Failed"); }
  };

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading Tally settings…</div>;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Tally HTTP-XML Gateway Settings
            {cfg.last_test_ok && <Badge className="bg-emerald-100 text-emerald-700 ml-2">Connected</Badge>}
            {cfg.last_test_ok === false && <Badge className="bg-rose-100 text-rose-700 ml-2">Not connected</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-3">
            <div>
              <Label>Tally Host</Label>
              <Input value={cfg.host} onChange={(e) => setCfg({ ...cfg, host: e.target.value })} placeholder="localhost or LAN IP" data-testid="tally-host" />
            </div>
            <div>
              <Label>Port</Label>
              <Input type="number" value={cfg.port} onChange={(e) => setCfg({ ...cfg, port: e.target.value })} placeholder="9000" data-testid="tally-port" />
            </div>
            <div>
              <Label>Company (optional)</Label>
              <Input value={cfg.company} onChange={(e) => setCfg({ ...cfg, company: e.target.value })} placeholder="ITL Books" data-testid="tally-company" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="tally-enabled" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} data-testid="tally-enabled" />
            <Label htmlFor="tally-enabled" className="font-normal">Enable Tally sync</Label>
          </div>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="tally-save">{saving ? "Saving…" : "Save"}</Button>
            <Button variant="outline" onClick={test} disabled={testing} data-testid="tally-test">{testing ? "Testing…" : "Test Connection"}</Button>
            <Button variant="outline" onClick={syncMasters} disabled={syncing || !cfg.enabled} data-testid="tally-sync"><RefreshCw className="h-4 w-4 mr-1" />{syncing ? "Syncing…" : "Sync Masters"}</Button>
          </div>
          {testResult && (
            <div className={`p-3 rounded border text-sm ${testResult.ok ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`}>
              {testResult.ok ? (
                <div className="flex items-center gap-2 text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Connected — Companies: {(testResult.companies || []).join(", ") || "(none)"}</div>
              ) : (
                <div className="flex items-start gap-2 text-rose-700"><AlertTriangle className="h-4 w-4 mt-0.5" /><span className="font-mono text-xs whitespace-pre-wrap break-all">{testResult.error}</span></div>
              )}
            </div>
          )}
          <div className="text-xs p-3 rounded bg-blue-50 border border-blue-200">
            <strong>Tally setup:</strong> In Tally Prime open <em>Gateway → F12 → ODBC/Advanced → Enable HTTP server</em>. The default port is <code>9000</code>. The ERP backend must be able to reach the Tally machine over the network — for a local-network Tally, set Host to the LAN IP of the Tally PC.
          </div>
          {cfg.last_sync_at && (
            <div className="text-xs text-muted-foreground">Last masters sync: {new Date(cfg.last_sync_at).toLocaleString()} · {cfg.ledger_count} ledgers</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Tally Ledgers <Badge variant="outline" className="ml-2">{ledgers.length}</Badge></CardTitle>
          <div className="flex gap-2">
            <Input className="w-64" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name / GSTIN…" data-testid="tally-search" />
            <Button variant="outline" size="sm" onClick={search}><Search className="h-3 w-3 mr-1" />Search</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="border rounded max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase sticky top-0">
                <tr><th className="px-3 py-2 text-left">Name</th><th className="px-3 py-2 text-left">Parent</th><th className="px-3 py-2 text-left">GSTIN</th><th className="px-3 py-2 text-left">Phone</th><th className="px-3 py-2 text-left">Email</th></tr>
              </thead>
              <tbody>
                {ledgers.length === 0 && <tr><td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">No ledgers — run "Sync Masters" first.</td></tr>}
                {ledgers.map((l) => (
                  <tr key={l.id} className="border-t">
                    <td className="px-3 py-2">{l.name}</td>
                    <td className="px-3 py-2 text-xs">{l.parent}</td>
                    <td className="px-3 py-2 text-xs font-mono">{l.gstin}</td>
                    <td className="px-3 py-2 text-xs">{l.phone}</td>
                    <td className="px-3 py-2 text-xs">{l.email}</td>
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
