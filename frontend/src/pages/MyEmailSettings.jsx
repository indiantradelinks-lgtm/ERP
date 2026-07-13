import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Mail, Send, Trash2, ShieldCheck, KeyRound, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

export default function MyEmailSettings() {
  const [state, setState] = useState({ configured: false });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [lastResult, setLastResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/email/me/smtp");
      setState(data);
      if (data.configured) {
        setUsername(data.smtp_username || "");
        setDisplayName(data.display_name || "");
        setTestTo(data.smtp_username || "");
      }
    } catch (e) {
      toast.error("Could not load your email settings");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!username || !password) {
      toast.error("Mailbox and app password are required");
      return;
    }
    setSaving(true);
    try {
      await api.put("/email/me/smtp", {
        smtp_username: username.trim(),
        app_password: password,
        display_name: displayName || null,
      });
      toast.success("App password saved (encrypted)");
      setPassword("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const clearCreds = async () => {
    if (!window.confirm("Remove your saved SMTP credentials? You'll need to paste your app password again to send.")) return;
    try {
      await api.delete("/email/me/smtp");
      toast.success("Credentials removed");
      setState({ configured: false });
      setUsername("");
      setPassword("");
      setDisplayName("");
    } catch (e) {
      toast.error("Failed to remove");
    }
  };

  const sendTest = async () => {
    if (!testTo.trim()) {
      toast.error("Recipient is required");
      return;
    }
    setTesting(true);
    setLastResult(null);
    try {
      const { data } = await api.post("/email/me/test", {
        to: testTo.trim(),
        subject: "ERP — SMTP test from my M365 mailbox",
        body: "Hi, this is a test from my ERP user account confirming Microsoft 365 SMTP works end-to-end.",
      });
      setLastResult(data);
      if (data.result?.ok) toast.success("Test sent");
      else toast.error(data.record?.last_error || "Test failed");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="space-y-6" data-testid="my-email-settings-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Mail className="h-3 w-3" /> My Email Settings
        </div>
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Microsoft 365 mailbox</h1>
        <p className="text-sm text-muted-foreground mt-1">When you click "Send" anywhere in the ERP and choose "From my mailbox", we'll use these credentials. Your app password is stored encrypted at rest (Fernet).</p>
      </div>

      <Card className={state.configured ? "border-success/40" : "border-warning/40"}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-display flex items-center gap-2">
            {state.configured ? <ShieldCheck className="h-4 w-4 text-success" /> : <AlertTriangle className="h-4 w-4 text-warning" />}
            {state.configured ? `Configured · ${state.smtp_username}` : "Not configured"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">M365 mailbox email</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="you@yourcompany.com" autoComplete="username" data-testid="my-smtp-username" />
            </div>
            <div>
              <Label className="text-xs">App password</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={state.configured ? "•••••••• (leave blank to keep)" : "16-character app password"} autoComplete="new-password" data-testid="my-smtp-password" />
            </div>
            <div>
              <Label className="text-xs">From display name</Label>
              <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. Aman · Sales · INDIAN TRADE LINKS" data-testid="my-smtp-display-name" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} disabled={saving} data-testid="my-smtp-save-btn">
              <KeyRound className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Saving…" : (state.configured ? "Update credentials" : "Save credentials")}
            </Button>
            {state.configured && (
              <Button variant="outline" onClick={clearCreds} data-testid="my-smtp-clear-btn">
                <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Remove
              </Button>
            )}
          </div>
          {state.last_test_status && (
            <div className="text-xs text-muted-foreground pt-1">
              Last test: <Badge variant={state.last_test_status === "sent" ? "default" : "destructive"}>{state.last_test_status}</Badge> at {state.last_test_at}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-display flex items-center gap-2"><Send className="h-4 w-4" /> Send a test email from your mailbox</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="recipient@example.com" data-testid="my-smtp-test-to" />
          <Button onClick={sendTest} disabled={!state.configured || testing} data-testid="my-smtp-test-btn">
            {testing ? "Sending…" : "Send test"}
          </Button>
          {lastResult && (
            <div className={`rounded-sm border p-3 text-xs ${lastResult.result?.ok ? "border-success/40 bg-success/5" : "border-destructive/40 bg-destructive/5"}`} data-testid="my-smtp-test-result">
              <div className="font-bold">{lastResult.result?.ok ? "✓ Sent" : "✗ Failed"} · {lastResult.result?.attempts} attempt(s)</div>
              <div className="mt-1 text-muted-foreground break-words">{lastResult.result?.ok ? (lastResult.result?.smtp_response || "Delivered to M365") : (lastResult.record?.last_error || lastResult.result?.last_error)}</div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-muted bg-muted/30">
        <CardContent className="pt-4 text-xs text-muted-foreground leading-relaxed space-y-2">
          <div className="font-bold text-foreground flex items-center gap-2"><KeyRound className="h-3.5 w-3.5" /> How to generate your Microsoft 365 App Password</div>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Enable Multi-Factor Authentication on your account if you haven't: <a className="underline text-primary" href="https://aka.ms/MFASetup" target="_blank" rel="noreferrer">aka.ms/MFASetup</a></li>
            <li>Sign in at <a className="underline text-primary" href="https://mysignins.microsoft.com/security-info" target="_blank" rel="noreferrer">mysignins.microsoft.com/security-info</a></li>
            <li>Click <strong>+ Add sign-in method</strong> → <strong>App password</strong>.</li>
            <li>Name it "ERP-SMTP" → copy the 16-character password shown (only displayed once).</li>
            <li>Paste it into the field above and click "Save credentials".</li>
            <li>Make sure your tenant admin has enabled SMTP AUTH for your mailbox — otherwise sending will fail with "Authentication unsuccessful". Ask them to run <code className="text-foreground">Set-CASMailbox -Identity you@yourcompany.com -SmtpClientAuthenticationDisabled $false</code>.</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
