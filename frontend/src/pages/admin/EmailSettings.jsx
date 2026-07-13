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

      <div className="text-xs text-muted-foreground">
        <a href="/app/admin/email-outbox" className="text-primary inline-flex items-center gap-1 underline">
          Open Email Outbox <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
