/**
 * Budget & Commitment Center · Finance Phase 3
 *
 * 4-tab workbench for the Store/Inventory/Procurement integration with Finance:
 *   • Budget Check         — project budget vs committed vs spent vs available
 *   • PO Commitment        — open POs (approved-not-fully-received)
 *   • GRN-not-billed       — GRNI provision risk (vendor hasn't billed yet)
 *   • Bill-without-GRN     — services (info) + audit-risk material bills
 *
 * Backend: /api/finance/budget/check + /api/finance/reports/*
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Wallet, Calculator, RefreshCcw, AlertTriangle, CheckCircle2, FileWarning } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const SEV_TONE = {
  critical: "bg-rose-100 text-rose-700",
  warning: "bg-amber-100 text-amber-700",
  info: "bg-blue-100 text-blue-700",
};

const fmt = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function BudgetCommitmentCenter() {
  const [projects, setProjects] = useState([]);
  const [tab, setTab] = useState("budget");
  const [projectId, setProjectId] = useState("");
  const [amount, setAmount] = useState(0);
  const [budget, setBudget] = useState(null);
  const poList = usePagedList("/finance/reports/po-commitment", {}, { viewKey: "fin_po_commitment", errorLabel: "PO commitment", pageSize: 25, defaultSort: { by: "po_date", dir: "desc" }, searchKeys: "po_number,vendor_name,project_code,status" });
  const grnList = usePagedList("/finance/reports/grn-not-billed", { days_old: 0 }, { viewKey: "fin_grn_not_billed", errorLabel: "GRN not billed", pageSize: 25, defaultSort: { by: "grn_date", dir: "desc" }, searchKeys: "grn_number,po_number,vendor_name,project_code,status" });
  const billList = usePagedList("/finance/reports/bill-without-grn", {}, { viewKey: "fin_bill_without_grn", errorLabel: "bills without GRN", pageSize: 25, defaultSort: { by: "invoice_date", dir: "desc" }, searchKeys: "bill_no,invoice_no,vendor_name,po_number,project_code,status,expense_category" });
  const poRows = { rows: poList.rows, count: poList.meta.count ?? 0, total_open_commitment: poList.meta.total_open_commitment ?? 0 };
  const grnRows = { rows: grnList.rows, count: grnList.meta.count ?? 0, total_open_grni: grnList.meta.total_open_grni ?? 0 };
  const billRows = { rows: billList.rows, count: billList.meta.count ?? 0, audit_risk_count: billList.meta.audit_risk_count ?? 0 };
  const [rollup, setRollup] = useState({ count: 0, rows: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await lookupGet("/projects");
        const rows = Array.isArray(data) ? data : (data?.data || []);
        setProjects(rows);
      } catch { /* ignore */ }
    })();
    loadReports();
  }, []);

  const loadBudget = async () => {
    if (!projectId) { toast.error("Pick a project first"); return; }
    setLoading(true);
    try {
      const { data } = await api.get("/finance/budget/check", { params: { project_id: projectId, amount: Number(amount) || 0 } });
      setBudget(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Budget check failed"); }
    finally { setLoading(false); }
  };

  const loadReports = async () => {
    setLoading(true);
    try {
      poList.reload(); grnList.reload(); billList.reload();
      const ru = await api.get("/finance/reports/project-procurement-cost");
      setRollup(ru.data);
    } catch (e) { toast.error("Failed to load reports"); }
    finally { setLoading(false); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-budget-commitment">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Wallet className="h-6 w-6 text-primary" /> Budget & Commitment Center</h1>
          <p className="text-sm text-muted-foreground">Live link between Finance · Store · Inventory · Procurement. All numbers from posted journal entries + open commitments.</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadReports} data-testid="bc-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="budget" data-testid="bc-tab-budget"><Calculator className="h-3.5 w-3.5 mr-1" />Budget Check</TabsTrigger>
          <TabsTrigger value="po" data-testid="bc-tab-po">PO Commitment ({poRows.count})</TabsTrigger>
          <TabsTrigger value="grn" data-testid="bc-tab-grn">GRN-not-billed ({grnRows.count})</TabsTrigger>
          <TabsTrigger value="bill" data-testid="bc-tab-bill">Bill w/o GRN ({billRows.count})</TabsTrigger>
          <TabsTrigger value="rollup" data-testid="bc-tab-rollup">Project Roll-up</TabsTrigger>
          <TabsTrigger value="alerts" data-testid="bc-tab-alerts">Project Alerts</TabsTrigger>
          <TabsTrigger value="bva" data-testid="bc-tab-bva">Budget vs Actual</TabsTrigger>
          <TabsTrigger value="statutory" data-testid="bc-tab-statutory">Statutory</TabsTrigger>
        </TabsList>

        {/* Budget Check */}
        <TabsContent value="budget">
          <Card><CardContent className="p-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Project</Label>
                <Select value={projectId || undefined} onValueChange={setProjectId}>
                  <SelectTrigger data-testid="bc-project"><SelectValue placeholder="— select project —" /></SelectTrigger>
                  <SelectContent>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Proposed new amount (₹)</Label>
                <Input type="number" value={amount} onChange={e => setAmount(e.target.value)} data-testid="bc-amount" placeholder="e.g. 250000" />
              </div>
              <div className="flex items-end">
                <Button onClick={loadBudget} disabled={loading} className="w-full" data-testid="bc-check"><Calculator className="h-4 w-4 mr-1" />Check budget</Button>
              </div>
            </div>

            {budget && (
              <div className="border rounded-sm p-4 bg-slate-50">
                <div className="text-sm font-semibold">{budget.project_code} · {budget.project_name}</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-3 text-sm">
                  <Row label="Total Budget" value={fmt(budget.budget_value)} tone="slate" />
                  <Row label="Open PO Commitment" value={fmt(budget.committed_pos_sos)} tone="blue" />
                  <Row label="Approved Bills (Spent)" value={fmt(budget.spent_approved_bills)} tone="rose" />
                  <Row label="Pending Bills" value={fmt(budget.pending_bills)} tone="amber" />
                  <Row label="Available" value={fmt(budget.available)} tone="emerald" />
                  <Row label="Utilisation" value={budget.utilisation_pct != null ? `${budget.utilisation_pct}%` : "—"} tone="slate" />
                </div>
                {budget.requested_amount > 0 && (
                  <div className={`mt-3 p-3 rounded-sm border ${budget.within_budget ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`} data-testid="bc-verdict">
                    {budget.within_budget ? (
                      <span className="inline-flex items-center gap-2 text-emerald-800"><CheckCircle2 className="h-4 w-4" /> Within budget · ₹{Number(budget.available_after_request).toLocaleString("en-IN")} remains after this request.</span>
                    ) : (
                      <span className="inline-flex items-center gap-2 text-rose-800"><AlertTriangle className="h-4 w-4" /> Exceeds budget by ₹{Math.abs(budget.available_after_request).toLocaleString("en-IN")}. Requires variation approval.</span>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent></Card>
        </TabsContent>

        {/* PO Commitment */}
        <TabsContent value="po">
          <Card><CardContent className="p-0">
            <div className="px-3 py-2 bg-slate-50 text-sm flex items-center gap-2"><FileWarning className="h-4 w-4" />Total open commitment: <b>{fmt(poRows.total_open_commitment)}</b> across {poRows.count} PO(s)</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr><th className="px-3 py-2 text-left">PO #</th><th className="px-3 py-2 text-left">Date</th><th className="px-3 py-2 text-left">Vendor</th><th className="px-3 py-2 text-left">Project</th><th className="px-3 py-2 text-right">PO Total</th><th className="px-3 py-2 text-right">Received</th><th className="px-3 py-2 text-right">Open</th></tr>
              </thead>
              <tbody>
                {poRows.rows.map(r => (
                  <tr key={r.id} className="border-b" data-testid={`po-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono text-xs">{r.po_number}</td>
                    <td className="px-3 py-2 text-xs">{r.po_date}</td>
                    <td className="px-3 py-2 text-xs">{r.vendor_name}</td>
                    <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.po_total)}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.received_value)}</td>
                    <td className="px-3 py-2 text-right font-semibold">{fmt(r.open_commitment)}</td>
                  </tr>
                ))}
                {!poRows.rows.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-emerald-600">No open commitments</td></tr>}
              </tbody>
            </table>
            <div className="px-3 py-2 border-t flex items-center gap-2">
              <Input className="h-8 w-48" placeholder="Search…" value={poList.search} onChange={(e) => poList.setSearch(e.target.value)} data-testid="bc-po-search" />
              <TableViewsMenu pagination={poList.pagination} testidPrefix="bc-po" />
              <div className="flex-1"><TablePager pagination={poList.pagination} testidPrefix="bc-po" /></div>
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* GRN-not-billed */}
        <TabsContent value="grn">
          <Card><CardContent className="p-0">
            <div className="px-3 py-2 bg-slate-50 text-sm flex items-center gap-2"><FileWarning className="h-4 w-4" />Open GRNI (provision risk): <b>{fmt(grnRows.total_open_grni)}</b> across {grnRows.count} GRN(s)</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr><th className="px-3 py-2 text-left">GRN #</th><th className="px-3 py-2 text-left">Date</th><th className="px-3 py-2 text-right">Age (d)</th><th className="px-3 py-2 text-left">Vendor</th><th className="px-3 py-2 text-left">PO #</th><th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2 text-left">Severity</th></tr>
              </thead>
              <tbody>
                {grnRows.rows.map(r => (
                  <tr key={r.id} className="border-b" data-testid={`grn-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono text-xs">{r.grn_number}</td>
                    <td className="px-3 py-2 text-xs">{r.grn_date}</td>
                    <td className="px-3 py-2 text-right text-xs">{r.age_days ?? "—"}</td>
                    <td className="px-3 py-2 text-xs">{r.vendor_name || "—"}</td>
                    <td className="px-3 py-2 text-xs">{r.po_number || "—"}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.grn_amount)}</td>
                    <td className="px-3 py-2"><Badge className={SEV_TONE[r.severity] || ""}>{r.severity}</Badge></td>
                  </tr>
                ))}
                {!grnRows.rows.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-emerald-600">All GRNs are matched to vendor bills</td></tr>}
              </tbody>
            </table>
            <div className="px-3 py-2 border-t flex items-center gap-2">
              <Input className="h-8 w-48" placeholder="Search…" value={grnList.search} onChange={(e) => grnList.setSearch(e.target.value)} data-testid="bc-grn-search" />
              <TableViewsMenu pagination={grnList.pagination} testidPrefix="bc-grn" />
              <div className="flex-1"><TablePager pagination={grnList.pagination} testidPrefix="bc-grn" /></div>
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* Bill without GRN */}
        <TabsContent value="bill">
          <Card><CardContent className="p-0">
            <div className="px-3 py-2 bg-slate-50 text-sm flex items-center gap-2">
              <FileWarning className="h-4 w-4" />
              {billRows.count} bills without GRN · <b className="text-rose-700">{billRows.audit_risk_count} audit-risk</b> (non-service material without PO)
            </div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr><th className="px-3 py-2 text-left">Bill #</th><th className="px-3 py-2 text-left">Date</th><th className="px-3 py-2 text-left">Vendor</th><th className="px-3 py-2 text-left">Project</th><th className="px-3 py-2 text-left">PO #</th><th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2 text-left">Type</th></tr>
              </thead>
              <tbody>
                {billRows.rows.map(r => (
                  <tr key={r.id} className={`border-b ${(!r.is_service && !r.po_number) ? "bg-rose-50" : ""}`} data-testid={`bill-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono text-xs">{r.bill_number}</td>
                    <td className="px-3 py-2 text-xs">{r.bill_date}</td>
                    <td className="px-3 py-2 text-xs">{r.vendor_name}</td>
                    <td className="px-3 py-2 text-xs">{r.project_code || "—"}</td>
                    <td className="px-3 py-2 text-xs">{r.po_number || "—"}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.amount)}</td>
                    <td className="px-3 py-2 text-xs">{r.is_service ? <Badge className="bg-blue-100 text-blue-700">Service</Badge> : (r.po_number ? <Badge className="bg-amber-100 text-amber-700">No GRN</Badge> : <Badge className="bg-rose-100 text-rose-700">Audit risk</Badge>)}</td>
                  </tr>
                ))}
                {!billRows.rows.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-emerald-600">No bills without GRN</td></tr>}
              </tbody>
            </table>
            <div className="px-3 py-2 border-t flex items-center gap-2">
              <Input className="h-8 w-48" placeholder="Search…" value={billList.search} onChange={(e) => billList.setSearch(e.target.value)} data-testid="bc-bill-search" />
              <TableViewsMenu pagination={billList.pagination} testidPrefix="bc-bill" />
              <div className="flex-1"><TablePager pagination={billList.pagination} testidPrefix="bc-bill" /></div>
            </div>
          </CardContent></Card>
        </TabsContent>

        {/* Roll-up */}
        <TabsContent value="rollup">
          <Card><CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr><th className="px-3 py-2 text-left">Project</th><th className="px-3 py-2 text-right">Budget</th><th className="px-3 py-2 text-right">PO Open</th><th className="px-3 py-2 text-right">GRN Value</th><th className="px-3 py-2 text-right">Approved Bills</th><th className="px-3 py-2 text-right">Pending</th></tr>
              </thead>
              <tbody>
                {rollup.rows.map(r => (
                  <tr key={r.project_id} className="border-b" data-testid={`rollup-row-${r.project_id}`}>
                    <td className="px-3 py-2 text-xs"><span className="font-mono">{r.project_code}</span> · {r.project_name}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.budget)}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.po_committed_open)}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.grn_received_value)}</td>
                    <td className="px-3 py-2 text-right font-semibold">{fmt(r.approved_bills)}</td>
                    <td className="px-3 py-2 text-right text-amber-700">{fmt(r.pending_bills)}</td>
                  </tr>
                ))}
                {!rollup.rows.length && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">No project data yet</td></tr>}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        {/* Project Alerts */}
        <TabsContent value="alerts">
          <ProjectAlertsTab projects={projects} />
        </TabsContent>

        {/* Budget vs Actual */}
        <TabsContent value="bva">
          <BudgetVsActualTab projects={projects} />
        </TabsContent>

        {/* Statutory */}
        <TabsContent value="statutory">
          <StatutoryTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ProjectAlertsTab({ projects }) {
  const [pid, setPid] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const load = async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/finance/project-alerts/${id}`);
      setData(data);
    } catch (e) { toast.error("Load failed"); }
    finally { setLoading(false); }
  };
  return (
    <Card><CardContent className="p-4 space-y-3">
      <div className="flex items-center gap-3">
        <Select value={pid || undefined} onValueChange={(v) => { setPid(v); load(v); }}>
          <SelectTrigger className="max-w-md" data-testid="alerts-project"><SelectValue placeholder="— pick project —" /></SelectTrigger>
          <SelectContent>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}</SelectContent>
        </Select>
        {loading && <span className="text-slate-400 text-xs">Loading…</span>}
      </div>
      {data && (
        <div className="space-y-2">
          <div className="text-sm"><b>{data.alert_count}</b> alert(s) · <span className="text-rose-700"><b>{data.critical_count}</b> critical</span></div>
          <ul className="divide-y border rounded-sm">
            {data.alerts.length === 0 && <li className="p-4 text-emerald-600 text-sm"><CheckCircle2 className="h-4 w-4 inline mr-1" /> All clear — no finance alerts for this project.</li>}
            {data.alerts.map((a, i) => (
              <li key={i} className="p-2 flex items-center gap-3" data-testid={`alert-${a.kind}`}>
                <Badge className={SEV_TONE[a.severity] || ""}>{a.severity}</Badge>
                <span className="text-sm flex-1">{a.message}</span>
                <span className="text-[10px] font-mono text-slate-400">{a.kind}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </CardContent></Card>
  );
}

function BudgetVsActualTab({ projects }) {
  const [pid, setPid] = useState("");
  const [data, setData] = useState(null);
  const load = async (id) => {
    if (!id) return;
    try {
      const { data } = await api.get(`/finance/budget-vs-actual/${id}`);
      setData(data);
    } catch (e) { toast.error("Load failed"); }
  };
  return (
    <Card><CardContent className="p-4 space-y-3">
      <Select value={pid || undefined} onValueChange={(v) => { setPid(v); load(v); }}>
        <SelectTrigger className="max-w-md" data-testid="bva-project"><SelectValue placeholder="— pick project —" /></SelectTrigger>
        <SelectContent>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}</SelectContent>
      </Select>
      {data && (
        <>
          <div className="text-sm">Budget: <b>{fmt(data.total_budget)}</b> · Actual: <b>{fmt(data.total_actual)}</b> · Variance: <b className={data.total_variance < 0 ? "text-rose-700" : "text-emerald-700"}>{fmt(data.total_variance)}</b></div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase">
              <tr><th className="p-2 text-left">Head</th><th className="p-2 text-right">Budget</th><th className="p-2 text-right">Actual</th><th className="p-2 text-right">Variance</th><th className="p-2 text-right">%</th><th className="p-2 text-left">Status</th></tr>
            </thead>
            <tbody>
              {data.heads.map(h => (
                <tr key={h.head} className="border-b" data-testid={`bva-row-${h.head}`}>
                  <td className="p-2">{h.label}</td>
                  <td className="p-2 text-right">{fmt(h.budget)}</td>
                  <td className="p-2 text-right">{fmt(h.actual)}</td>
                  <td className={`p-2 text-right ${h.variance < 0 ? "text-rose-700" : ""}`}>{fmt(h.variance)}</td>
                  <td className="p-2 text-right text-xs">{h.variance_pct != null ? `${h.variance_pct}%` : "—"}</td>
                  <td className="p-2"><Badge className={h.status === "over" ? "bg-rose-100 text-rose-700" : h.status === "under" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"}>{h.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </CardContent></Card>
  );
}

function StatutoryTab() {
  const [data, setData] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/finance/statutory-summary");
        setData(data);
      } catch (e) { /* ignore */ }
    })();
  }, []);
  return (
    <Card><CardContent className="p-4 space-y-3">
      {!data && <span className="text-slate-400 text-sm">Loading…</span>}
      {data && (
        <>
          <div className="text-sm">Period: <b>{data.from} → {data.to}</b></div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase">
              <tr><th className="p-2 text-left">Liability</th><th className="p-2 text-right">Accrued</th><th className="p-2 text-right">Paid</th><th className="p-2 text-right">Balance Payable</th></tr>
            </thead>
            <tbody>
              {data.by_account.map(r => (
                <tr key={r.account_code} className="border-b" data-testid={`stat-row-${r.account_code}`}>
                  <td className="p-2"><span className="font-mono text-[10px] text-slate-400">{r.account_code}</span> · {r.account_name}</td>
                  <td className="p-2 text-right">{fmt(r.accrued)}</td>
                  <td className="p-2 text-right">{fmt(r.paid)}</td>
                  <td className="p-2 text-right font-semibold">{fmt(r.balance_payable)}</td>
                </tr>
              ))}
              {!data.by_account.length && <tr><td colSpan={4} className="p-8 text-center text-slate-400">No statutory accruals in this period</td></tr>}
            </tbody>
          </table>
        </>
      )}
    </CardContent></Card>
  );
}

function Row({ label, value, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white",
    blue: "border-blue-200 bg-blue-50",
    emerald: "border-emerald-200 bg-emerald-50",
    amber: "border-amber-200 bg-amber-50",
    rose: "border-rose-200 bg-rose-50",
  };
  return (
    <div className={`p-2 rounded-sm border ${tones[tone] || tones.slate}`}>
      <div className="text-[11px] text-slate-600">{label}</div>
      <div className="text-lg font-bold tabular-nums">{value}</div>
    </div>
  );
}
