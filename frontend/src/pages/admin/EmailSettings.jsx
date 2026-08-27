import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Mail, ShieldCheck, ShieldAlert, Send, ExternalLink, KeyRound, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

export default function EmailSettings() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testSubject, setTestSubject] = useState("ERP — SMTP test from shared mailbox");
  const [testBody, setTestBody] = useState("This is a connectivity test from your ERP system mailbox via Microsoft 365 SMTP.");
  const [lastResult, setLastResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/email/config");
      setConfig(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load email config");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const sendTest = async () => {
    if (!testTo.trim()) {
      toast.error("Recipient email is required");
      return;
    }
    setTesting(true);
    setLastResult(null);
    try {
      const { data } = await api.post("/email/config/test", { to: testTo.trim(), subject: testSubject, body: testBody });
      setLastResult(data);
      if (data.result?.ok) {
        toast.success(`Test email sent in ${data.result.attempts} attempt(s)`);
      } else {
        toast.error(data.record?.last_error || "Test send failed");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to send test");
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;

  const sharedOk = config?.shared_mailbox_configured;
  const fernetOk = config?.fernet_ready;

  return (
    <div className="space-y-6" data-testid="email-settings-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Mail className="h-3 w-3" /> Microsoft 365 SMTP
        </div>
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Email Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Send quotations, POs, invoices and HR letters from your company Microsoft 365 mailbox via authenticated SMTP.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className={sharedOk ? "border-success/40" : "border-warning/40"}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-display flex items-center gap-2">
              {sharedOk ? <ShieldCheck className="h-4 w-4 text-success" /> : <ShieldAlert className="h-4 w-4 text-warning" />}
              System / Shared Mailbox
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5 text-muted-foreground">
            <div>Host: <span className="text-foreground font-medium">{config?.smtp_host}:{config?.smtp_port}</span></div>
            <div>Mailbox: <span className="text-foreground font-mono" data-testid="shared-mailbox-redacted">{config?.shared_mailbox || "— not configured —"}</span></div>
            <div>Display name: <span className="text-foreground">{config?.shared_display_name}</span></div>
            <div className="pt-1">
              <Badge variant={sharedOk ? "default" : "outline"} data-testid="shared-status-badge">
                {sharedOk ? "Configured" : "Pending .env credentials"}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className={fernetOk ? "border-success/40" : "border-destructive/40"}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-display flex items-center gap-2">
              <KeyRound className="h-4 w-4" /> Per-user Credentials Encryption
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5 text-muted-foreground">
            <div>Algorithm: <span className="text-foreground">Fernet (AES-128-CBC + HMAC-SHA256)</span></div>
            <div>Key source: <span className="text-foreground">backend/.env → M365_FERNET_KEY</span></div>
            <div className="pt-1">
              <Badge variant={fernetOk ? "default" : "destructive"} data-testid="fernet-status-badge">
                {fernetOk ? "Ready" : "Missing key"}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {!sharedOk && (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="pt-4 text-xs leading-relaxed space-y-2">
            <div className="font-bold text-warning flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5" /> Shared mailbox setup steps</div>
            <ol className="list-decimal pl-5 space-y-1 text-muted-foreground">
              <li>Create a dedicated regular (not shared) M365 mailbox e.g. <code className="text-foreground">erp@yourcompany.com</code>.</li>
              <li>Enable MFA on that mailbox at <a className="underline text-primary" href="https://mysignins.microsoft.com/security-info" target="_blank" rel="noreferrer">mysignins.microsoft.com</a>.</li>
              <li>Tenant admin runs: <code className="text-foreground">Set-TransportConfig -SmtpClientAuthenticationDisabled $false</code></li>
              <li>Per-mailbox: <code className="text-foreground">Set-CASMailbox -Identity erp@yourcompany.com -SmtpClientAuthenticationDisabled $false</code></li>
              <li>Generate an App Password on the same security portal and paste it into <code className="text-foreground">backend/.env</code> → <code className="text-foreground">M365_SMTP_SHARED_USERNAME</code> and <code className="text-foreground">M365_SMTP_SHARED_PASSWORD</code>.</li>
              <li>Restart the backend (<code className="text-foreground">sudo supervisorctl restart backend</code>) and refresh this page.</li>
            </ol>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-display flex items-center gap-2">
            <Send className="h-4 w-4" /> Send a test email from the shared mailbox
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label className="text-xs">Recipient (To)</Label>
            <Input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="someone@yourcompany.com" data-testid="shared-test-to" />
          </div>
          <div>
            <Label className="text-xs">Subject</Label>
            <Input value={testSubject} onChange={(e) => setTestSubject(e.target.value)} data-testid="shared-test-subject" />
          </div>
          <div>
            <Label className="text-xs">Body</Label>
            <Textarea rows={3} value={testBody} onChange={(e) => setTestBody(e.target.value)} data-testid="shared-test-body" />
          </div>
          <div className="pt-1">
            <Button onClick={sendTest} disabled={!sharedOk || testing} data-testid="shared-test-send-btn">
              {testing ? "Sending…" : "Send test"}
            </Button>
          </div>
          {lastResult && (
            <div className={`mt-2 rounded-sm border p-3 text-xs ${lastResult.result?.ok ? "border-success/40 bg-success/5" : "border-destructive/40 bg-destructive/5"}`} data-testid="shared-test-result">
              <div className="font-bold">
                {lastResult.result?.ok ? "✓ Sent" : "✗ Failed"} · {lastResult.result?.attempts} attempt(s)
              </div>
              <div className="mt-1 text-muted-foreground break-words">
                {lastResult.result?.ok
                  ? lastResult.result?.smtp_response || "Delivered to M365"
                  : lastResult.record?.last_error || lastResult.result?.last_error}
              </div>
              <div className="mt-1 text-muted-foreground">Outbox ID: <span className="font-mono">{lastResult.outbox_id}</span></div>
            </div>
          )}
        </CardContent>
      </Card>

      <SystemMailboxes />

      <div className="text-xs text-muted-foreground">
        <a href="/app/admin/email-outbox" className="text-primary inline-flex items-center gap-1 underline">
          Open Email Outbox <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}

function SystemMailboxes() {
  const blank = { purpose: "", email: "", display_name: "INDIAN TRADE LINKS", app_password: "", active: true };
  const [rows, setRows] = useState([]);
  const [editing, setEditing] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const load = async () => {
    try { setRows((await api.get("/email/system-mailboxes")).data); } catch { /* non-admin */ }
  };
  useEffect(() => { load(); }, []);
  const save = async () => {
    if (!editing.purpose || !editing.email || (!editing.id && !editing.app_password)) {
      toast.error("Purpose, email and app password are required"); return;
    }
    try {
      if (editing.id) await api.put(`/email/system-mailboxes/${editing.id}`, editing);
      else await api.post("/email/system-mailboxes", editing);
      toast.success("Mailbox saved");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete '${r.purpose}' mailbox? Sends for this purpose will fall back to the default shared mailbox.`)) return;
    try { await api.delete(`/email/system-mailboxes/${r.id}`); load(); } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const test = async (r) => {
    const to = window.prompt("Send test email to:", r.email);
    if (!to) return;
    setTestingId(r.id);
    try {
      const { data } = await api.post(`/email/system-mailboxes/${r.id}/test`, { to });
      data.ok ? toast.success(`Test sent from ${r.email}`) : toast.error(data.error || "Send failed");
    } catch (e) { toast.error(e.response?.data?.detail || "Send failed"); }
    finally { setTestingId(null); }
  };
  return (
    <Card data-testid="system-mailboxes-card">
      <CardHeader className="flex flex-row items-center pb-3">
        <CardTitle className="text-sm font-display flex-1">Purpose-based System Mailboxes
          <span className="block text-[11px] font-normal text-muted-foreground mt-1">Different sender for each purpose — e.g. sales@ for quotations, purchase@ for POs/RFQs, noreply@ for reminders. Add more anytime.</span>
        </CardTitle>
        <Button size="sm" onClick={() => setEditing({ ...blank })} data-testid="add-system-mailbox">+ Add Mailbox</Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.length === 0 && <div className="text-xs text-muted-foreground">No purpose mailboxes yet — all system emails use the default shared mailbox from .env.</div>}
        {rows.map((r) => (
          <div key={r.id} className="flex items-center gap-3 border border-border rounded-sm px-3 py-2" data-testid={`mailbox-row-${r.purpose}`}>
            <Badge variant="outline" className="rounded-sm text-[10px] uppercase">{r.purpose}</Badge>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold truncate">{r.email}</div>
              <div className="text-[10px] text-muted-foreground">{r.display_name}</div>
            </div>
            <Badge variant="outline" className={`rounded-sm text-[10px] ${r.active ? "border-emerald-300 text-emerald-800 bg-emerald-50" : "border-slate-300 text-slate-500"}`}>{r.active ? "Active" : "Disabled"}</Badge>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={testingId === r.id} onClick={() => test(r)} data-testid={`test-mailbox-${r.purpose}`}>{testingId === r.id ? "Sending…" : "Test"}</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing({ ...r, app_password: "" })}>Edit</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => remove(r)}>Delete</Button>
          </div>
        ))}
        {editing && (
          <div className="border border-primary/40 rounded-sm p-3 grid grid-cols-1 md:grid-cols-2 gap-3 mt-2" data-testid="mailbox-form">
            <div><Label className="text-[10px] uppercase tracking-wider">Purpose (key) *</Label>
              <Input value={editing.purpose} disabled={!!editing.id} placeholder="sales / procurement / noreply / hr…" onChange={(e) => setEditing({ ...editing, purpose: e.target.value })} className="h-9 mt-1" data-testid="mailbox-purpose" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Email Address *</Label>
              <Input value={editing.email} placeholder="sales@indiantradelinks.in" onChange={(e) => setEditing({ ...editing, email: e.target.value })} className="h-9 mt-1" data-testid="mailbox-email" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">Display Name</Label>
              <Input value={editing.display_name || ""} onChange={(e) => setEditing({ ...editing, display_name: e.target.value })} className="h-9 mt-1" /></div>
            <div><Label className="text-[10px] uppercase tracking-wider">M365 App Password {editing.id ? "(leave blank to keep current)" : "*"}</Label>
              <Input type="password" value={editing.app_password} placeholder="16-character app password" onChange={(e) => setEditing({ ...editing, app_password: e.target.value })} className="h-9 mt-1" data-testid="mailbox-password" /></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editing.active} onChange={(e) => setEditing({ ...editing, active: e.target.checked })} /> Active</label>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
              <Button size="sm" onClick={save} data-testid="mailbox-save">Save</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
