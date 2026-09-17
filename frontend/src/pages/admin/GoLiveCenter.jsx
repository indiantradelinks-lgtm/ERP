/**
 * Go-Live Center · Phase 10
 * Migration coverage, reconciliation, negative tests, and final readiness score.
 * Backend: /api/finance/phase10/go-live/checklist
 *          /api/finance/phase10/reconciliation/summary
 *          /api/finance/phase10/reconciliation/ledger-tie-out
 *          /api/finance/phase10/negative-tests/run
 *          /api/finance/phase10/migration/coverage
 *          /api/finance/phase10/go-live/pending-approvals
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCcw, ListTodo } from "lucide-react";
import { fmtD } from "@/lib/datetime";

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function GoLiveCenter() {
  const [checklist, setChecklist] = useState(null);
  const [recon, setRecon] = useState(null);
  const [tie, setTie] = useState(null);
  const [neg, setNeg] = useState(null);
  const [pending, setPending] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [c, r, t, n, p] = await Promise.all([
        api.get("/finance/phase10/go-live/checklist"),
        api.get("/finance/phase10/reconciliation/summary"),
        api.get("/finance/phase10/reconciliation/ledger-tie-out"),
        api.get("/finance/phase10/negative-tests/run"),
        api.get("/finance/phase10/go-live/pending-approvals"),
      ]);
      setChecklist(c.data); setRecon(r.data); setTie(t.data);
      setNeg(n.data); setPending(p.data);
    } catch (e) { toast.error("Failed to load go-live data"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (!checklist) return <div className="p-6 text-slate-400">Loading go-live center…</div>;

  return (
    <div className="p-6 space-y-4" data-testid="page-golive-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Go-Live Center</h1>
          <p className="text-sm text-slate-400">Migration, reconciliation, negative tests &amp; readiness</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading} data-testid="btn-reload-golive">
          <RefreshCcw className="h-4 w-4 mr-1" /> Re-run
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-400">Readiness Score</span>
            <Badge variant={checklist.ready_for_go_live ? "default" : "destructive"} data-testid="badge-readiness">
              {checklist.ready_for_go_live ? "READY" : "NOT READY"}
            </Badge>
          </div>
          <div className="flex items-center gap-3">
            <Progress value={checklist.score} className="flex-1" />
            <span className="text-2xl font-semibold" data-testid="text-score">{checklist.score}%</span>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="checklist">
        <TabsList>
          <TabsTrigger value="checklist" data-testid="tab-checklist">Checklist</TabsTrigger>
          <TabsTrigger value="recon" data-testid="tab-recon">Reconciliation</TabsTrigger>
          <TabsTrigger value="negative" data-testid="tab-negative">Negative Tests</TabsTrigger>
          <TabsTrigger value="migration" data-testid="tab-migration">Migration Coverage</TabsTrigger>
          <TabsTrigger value="pending" data-testid="tab-pending">Pending Approvals</TabsTrigger>
        </TabsList>

        <TabsContent value="checklist" className="mt-4">
          <Card><CardContent className="p-4 space-y-2">
            {checklist.items.map((it) => (
              <div key={it.key} className="flex items-center justify-between p-3 border border-slate-700 rounded" data-testid={`checklist-item-${it.key}`}>
                <div className="flex items-center gap-3">
                  {it.ok
                    ? <CheckCircle2 className="h-5 w-5 text-green-500" />
                    : <AlertTriangle className="h-5 w-5 text-amber-500" />}
                  <div>
                    <div className="font-medium">{it.label}</div>
                    <div className="text-xs text-slate-500">{it.detail}</div>
                  </div>
                </div>
                <Badge variant={it.ok ? "default" : "destructive"}>{it.ok ? "OK" : "ACTION"}</Badge>
              </div>
            ))}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="recon" className="mt-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { l: "AR Outstanding", v: recon?.ar?.outstanding },
              { l: "AP Outstanding", v: recon?.ap?.outstanding },
              { l: "Cash / Bank", v: recon?.cash_bank_balance },
              { l: "Payroll Payable", v: recon?.payroll_payable },
              { l: "GST Net", v: recon?.gst?.net },
              { l: "TDS Deducted", v: recon?.tds?.deducted },
              { l: "TDS Payable", v: recon?.tds?.payable },
              { l: "Advances Out", v: recon?.advances?.outstanding },
            ].map((k, i) => (
              <Card key={i} data-testid={`recon-${k.l.toLowerCase().replace(/[^a-z]/g, "-")}`}>
                <CardContent className="p-4">
                  <div className="text-xs uppercase text-slate-400">{k.l}</div>
                  <div className="text-xl font-semibold mt-1">{fmt(k.v)}</div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card><CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-slate-400">Trial Balance Tie-out</div>
                <div className="text-xs text-slate-500 mt-1">DR ₹{tie?.total_debit} · CR ₹{tie?.total_credit}</div>
              </div>
              <Badge variant={tie?.balanced ? "default" : "destructive"} data-testid="badge-tie">
                {tie?.balanced ? "BALANCED" : `OFF BY ₹${tie?.difference}`}
              </Badge>
            </div>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="negative" className="mt-4">
          <Card><CardContent className="p-4 space-y-2">
            <div className="text-sm mb-3">
              <span className="text-green-500 font-semibold">{neg?.passed}</span> passed ·{" "}
              <span className="text-red-500 font-semibold">{neg?.failed}</span> failed of {neg?.total}
            </div>
            {neg?.tests?.map((t) => (
              <div key={t.key} className="flex items-center justify-between p-3 border border-slate-700 rounded" data-testid={`neg-${t.key}`}>
                <div className="flex items-center gap-3">
                  {t.passed
                    ? <CheckCircle2 className="h-5 w-5 text-green-500" />
                    : <XCircle className="h-5 w-5 text-red-500" />}
                  <div>
                    <div className="font-medium">{t.label}</div>
                    {!t.passed && t.count > 0 && <div className="text-xs text-red-400">{t.count} offending rows</div>}
                  </div>
                </div>
                <Badge variant={t.passed ? "default" : "destructive"}>{t.passed ? "PASS" : "FAIL"}</Badge>
              </div>
            ))}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="migration" className="mt-4">
          <Card><CardContent className="p-4">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Entity</th><th className="text-right">Count</th></tr></thead>
              <tbody>
                {Object.entries(checklist.coverage).map(([k, v]) => (
                  <tr key={k} className="border-b border-slate-800">
                    <td className="py-2">{k}</td>
                    <td className="text-right">{typeof v === "object" ? `${v.total} (${v.active} active)` : v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="pending" className="mt-4">
          <Card><CardContent className="p-4">
            {!pending || pending.rows.length === 0
              ? <div className="text-slate-400 text-sm flex items-center gap-2"><ListTodo className="h-4 w-4" /> Approval queue is clear.</div>
              : <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Type</th><th>Subject</th><th className="text-right">Amount</th><th>Status</th><th>Created</th></tr></thead>
                  <tbody>
                    {pending.rows.map((r, i) => (
                      <tr key={r.id} className="border-b border-slate-800" data-testid={`pending-row-${i}`}>
                        <td className="py-2">{r.type}</td><td>{r.subject || "-"}</td>
                        <td className="text-right">{r.amount ? fmt(r.amount) : "-"}</td>
                        <td><Badge variant="secondary">{r.status}</Badge></td>
                        <td className="text-xs text-slate-400">{fmtD(r.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>}
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
