import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ShieldCheck, RefreshCw, CloudUpload } from "lucide-react";
import { toast } from "sonner";

const mb = (b) => `${((b || 0) / 1024 / 1024).toFixed(2)} MB`;

export default function DocumentStorageAudit({ onMigrateAll }) {
  const [audit, setAudit] = useState(null);
  const [busy, setBusy] = useState("");

  const load = async () => {
    try { setAudit((await api.get("/admin/onedrive/storage-audit")).data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load storage audit"); }
  };
  useEffect(() => { load(); }, []);

  const verifyNow = async () => {
    setBusy("verify");
    try {
      const { data } = await api.post("/admin/onedrive/verify-now?limit=50");
      toast.success(`Verified ${data.verified} · failed ${data.failed} · candidates ${data.candidates ?? 0}${data.skipped ? ` (${data.skipped})` : ""}`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Verification failed"); }
    finally { setBusy(""); }
  };

  if (!audit) return <div className="text-sm text-muted-foreground p-4" data-testid="storage-audit-loading">Loading storage audit…</div>;
  const t = audit.totals;
  const pct = t.files ? Math.round((100 * t.verified) / t.files) : 0;

  return (
    <Card data-testid="storage-audit-card">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5" /> Document Storage — OneDrive primary migration</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load} data-testid="storage-audit-refresh"><RefreshCw className="h-4 w-4 mr-1" />Refresh</Button>
          <Button size="sm" variant="outline" disabled={!!busy} onClick={verifyNow} data-testid="storage-audit-verify"><ShieldCheck className="h-4 w-4 mr-1" />Verify pushed files</Button>
          <Button size="sm" onClick={onMigrateAll} data-testid="storage-audit-migrate"><CloudUpload className="h-4 w-4 mr-1" />Queue all historical files</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
          <div><div className="text-xs text-muted-foreground">Active documents</div><div className="text-xl font-semibold" data-testid="storage-total-files">{t.files}</div><div className="text-xs">{mb(t.bytes)}</div></div>
          <div><div className="text-xs text-muted-foreground">Pushed to OneDrive</div><div className="text-xl font-semibold">{t.pushed}</div></div>
          <div><div className="text-xs text-muted-foreground">Verified (OneDrive primary)</div><div className="text-xl font-semibold text-emerald-700" data-testid="storage-verified">{t.verified}</div><div className="text-xs">{mb(t.verified_bytes)}</div></div>
          <div><div className="text-xs text-muted-foreground">Verification failed</div><div className={`text-xl font-semibold ${t.verify_failed ? "text-rose-600" : ""}`}>{t.verify_failed}</div></div>
          <div><div className="text-xs text-muted-foreground">Queue</div><div className="text-sm pt-1">{audit.queue.pending || 0} pending · {audit.queue.failed || 0} failed · {audit.not_queued > 0 ? audit.not_queued : 0} not queued</div></div>
        </div>
        <div>
          <div className="flex justify-between text-xs mb-1"><span>Migration progress (verified ÷ active)</span><span>{pct}%</span></div>
          <Progress value={pct} />
        </div>
        <p className="text-xs text-muted-foreground">
          A document is served from OneDrive only after its bytes were downloaded back and the SHA-256 matched the hash recorded at upload.
          The object-store copy is never deleted — it remains the automatic fallback and rollback.
        </p>
        <div className="border rounded overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase">
              <tr><th className="px-3 py-2 text-left">Module</th><th className="px-3 py-2 text-right">Files</th><th className="px-3 py-2 text-right">Size</th><th className="px-3 py-2 text-right">Pushed</th><th className="px-3 py-2 text-right">Verified</th><th className="px-3 py-2 text-right">Failed</th><th className="px-3 py-2 text-left">Status</th></tr>
            </thead>
            <tbody>
              {audit.modules.map((m) => (
                <tr key={m.module} className="border-t" data-testid={`storage-row-${m.module}`}>
                  <td className="px-3 py-2 font-medium">{m.module}</td>
                  <td className="px-3 py-2 text-right">{m.files}</td>
                  <td className="px-3 py-2 text-right">{mb(m.bytes)}</td>
                  <td className="px-3 py-2 text-right">{m.pushed}</td>
                  <td className="px-3 py-2 text-right">{m.verified}</td>
                  <td className="px-3 py-2 text-right">{m.verify_failed}</td>
                  <td className="px-3 py-2">
                    {m.verified === m.files ? <Badge className="bg-emerald-100 text-emerald-700">migrated</Badge>
                      : m.pushed ? <Badge className="bg-amber-100 text-amber-700">verifying</Badge>
                        : <Badge variant="outline">object store</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
