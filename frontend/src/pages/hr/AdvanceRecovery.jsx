import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { DepartmentSelect } from "@/components/DepartmentSelect";
import { Calculator, Upload, FileText, TrendingDown, AlertCircle, Download } from "lucide-react";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const currentMonth = () => new Date().toISOString().slice(0, 7);

export default function AdvanceRecovery() {
  const [tab, setTab] = useState("run");

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="advance-recovery-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Calculator className="h-6 w-6 text-teal-600" /> Advance Recovery & Reports
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Monthly EMI run with preview/override, reports, and bulk import of historical balances.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="run" data-testid="tab-run">Monthly Run</TabsTrigger>
          <TabsTrigger value="outstanding" data-testid="tab-outstanding">Outstanding Report</TabsTrigger>
          <TabsTrigger value="recovery" data-testid="tab-recovery-report">Monthly Recovery</TabsTrigger>
          <TabsTrigger value="aging" data-testid="tab-aging">Aging</TabsTrigger>
          <TabsTrigger value="import" data-testid="tab-import">Bulk Import</TabsTrigger>
        </TabsList>

        <TabsContent value="run"><MonthlyRunTab /></TabsContent>
        <TabsContent value="outstanding"><OutstandingTab /></TabsContent>
        <TabsContent value="recovery"><MonthlyRecoveryTab /></TabsContent>
        <TabsContent value="aging"><AgingTab /></TabsContent>
        <TabsContent value="import"><ImportTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function MonthlyRunTab() {
  const [month, setMonth] = useState(currentMonth());
  const [proposals, setProposals] = useState(null);
  const [skipped, setSkipped] = useState([]);
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState({});  // advance_id -> override amount

  const preview = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/advances/recovery/run", { month, dry_run: true });
      setProposals(data.proposals || []);
      setSkipped(data.skipped || []);
      const e = {};
      (data.proposals || []).forEach((p) => { e[p.advance_id] = p.emi; });
      setEdits(e);
      toast.success(`${(data.proposals || []).length} EMI line(s) ready · ₹${data.total_emi?.toLocaleString("en-IN") || 0}`);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const commit = async () => {
    if (!proposals?.length) { toast.error("Run preview first"); return; }
    if (!confirm(`Commit ${proposals.length} EMI deductions for ${month}? This will update employee balances.`)) return;
    setBusy(true);
    try {
      // Apply per-line overrides first
      for (const p of proposals) {
        const overridden = Number(edits[p.advance_id]);
        if (Number.isFinite(overridden) && Math.abs(overridden - p.emi) > 0.5) {
          await api.post("/advances/recovery/override", { advance_id: p.advance_id, month, amount: overridden, note: "Override before commit" });
        }
      }
      const remaining = proposals.filter((p) => Math.abs(Number(edits[p.advance_id]) - p.emi) <= 0.5);
      if (remaining.length) {
        // Manual deletion: build a fresh commit which auto-skips already-processed rows
        await api.post("/advances/recovery/run", { month, dry_run: false });
      }
      toast.success("Committed");
      setProposals(null);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const total = proposals ? proposals.reduce((s, p) => s + Number(edits[p.advance_id] || p.emi), 0) : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Compute &amp; Commit EMI Deductions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label>Run Month</Label>
            <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" data-testid="run-month" />
          </div>
          <Button onClick={preview} disabled={busy} data-testid="run-preview-btn">{busy ? "…" : "Preview"}</Button>
          <Button onClick={commit} disabled={busy || !proposals?.length} variant="default" className="bg-teal-600 hover:bg-teal-700" data-testid="run-commit-btn">
            Commit {proposals?.length ? `(${proposals.length} lines · ${inr(total)})` : ""}
          </Button>
        </div>

        {proposals && (
          <>
            <div className="overflow-x-auto border rounded">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Advance #</TableHead><TableHead>Employee</TableHead><TableHead>Dept</TableHead>
                  <TableHead className="text-right">Outstanding Before</TableHead>
                  <TableHead className="text-right">Proposed EMI</TableHead>
                  <TableHead className="text-right w-32">Override</TableHead>
                  <TableHead className="text-right">After</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {proposals.map((p) => (
                    <TableRow key={p.advance_id} data-testid={`run-row-${p.advance_no}`}>
                      <TableCell className="font-mono text-xs">{p.advance_no}</TableCell>
                      <TableCell>{p.employee_name}</TableCell>
                      <TableCell>{p.department}</TableCell>
                      <TableCell className="text-right">{inr(p.outstanding_before)}</TableCell>
                      <TableCell className="text-right">{inr(p.emi)}</TableCell>
                      <TableCell className="text-right">
                        <Input type="number" value={edits[p.advance_id] ?? p.emi}
                          className="w-28 text-right ml-auto"
                          onChange={(e) => setEdits({ ...edits, [p.advance_id]: e.target.value })}
                          data-testid={`override-${p.advance_no}`} />
                      </TableCell>
                      <TableCell className="text-right">{inr(p.outstanding_before - Number(edits[p.advance_id] || p.emi))}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {skipped.length > 0 && (
              <div className="p-3 border rounded bg-amber-50 text-xs">
                <strong>{skipped.length} skipped:</strong> {skipped.slice(0, 5).map((s) => `${s.advance_no} (${s.reason})`).join(", ")}{skipped.length > 5 && "…"}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function OutstandingTab() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ department: "", site: "" });
  const [total, setTotal] = useState(0);
  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.department) params.append("department", filter.department);
      if (filter.site) params.append("site", filter.site);
      const { data } = await api.get(`/advances/reports/outstanding?${params}`);
      setRows(data.rows || []);
      setTotal(data.total_outstanding || 0);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const exportCSV = () => {
    const csv = ["advance_no,employee_name,department,advance_type,approved,recovered,outstanding,emi,remaining"]
      .concat(rows.map((r) => `${r.advance_no},"${r.employee_name}",${r.department || ""},${r.advance_type},${r.approved_amount},${r.recovered_amount || 0},${r.outstanding},${r.emi},${r.remaining_installments}`))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `outstanding-advances-${new Date().toISOString().slice(0,10)}.csv`; a.click();
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Outstanding Report · Total {inr(total)}</CardTitle>
        <div className="w-40">
          <DepartmentSelect label="" value={filter.department} onChange={(v) => setFilter({ ...filter, department: v })} testid="ar-filter-department" />
        </div>
        <Input placeholder="Site" className="w-40" value={filter.site} onChange={(e) => setFilter({ ...filter, site: e.target.value })} />
        <Button onClick={load}>Load</Button>
        <Button variant="outline" onClick={exportCSV} disabled={!rows.length}><Download className="h-4 w-4 mr-1" />Export CSV</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Advance #</TableHead><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Approved</TableHead><TableHead className="text-right">Recovered</TableHead><TableHead className="text-right">Outstanding</TableHead><TableHead className="text-right">EMI × left</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-6">No outstanding advances</TableCell></TableRow>}
              {rows.map((r) => (
                <TableRow key={r.advance_no}><TableCell className="font-mono text-xs">{r.advance_no}</TableCell><TableCell>{r.employee_name}</TableCell><TableCell>{r.department}</TableCell><TableCell><Badge variant="outline">{r.advance_type}</Badge></TableCell><TableCell className="text-right">{inr(r.approved_amount)}</TableCell><TableCell className="text-right">{inr(r.recovered_amount)}</TableCell><TableCell className="text-right font-medium">{inr(r.outstanding)}</TableCell><TableCell className="text-right text-xs">{inr(r.emi)} × {r.remaining_installments}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function MonthlyRecoveryTab() {
  const [month, setMonth] = useState(currentMonth());
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const load = async () => {
    try {
      const { data } = await api.get(`/advances/reports/monthly-recovery?month=${month}`);
      setRows(data.rows || []);
      setTotal(data.total_recovered || 0);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Monthly Recovery · Total {inr(total)}</CardTitle>
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" />
        <Button onClick={load}>Load</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded">
          <Table>
            <TableHeader><TableRow><TableHead>Advance #</TableHead><TableHead>Employee</TableHead><TableHead>Dept</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Types</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-6">No data</TableCell></TableRow>}
              {rows.map((r) => (
                <TableRow key={r.advance_no}><TableCell className="font-mono text-xs">{r.advance_no}</TableCell><TableCell>{r.employee_name}</TableCell><TableCell>{r.department}</TableCell><TableCell className="text-right">{inr(r.amount)}</TableCell><TableCell>{(r.types || []).map((t) => <Badge key={t} variant="outline" className="mr-1">{t}</Badge>)}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function AgingTab() {
  const [buckets, setBuckets] = useState(null);
  const [total, setTotal] = useState(0);
  const load = async () => {
    try {
      const { data } = await api.get("/advances/reports/aging");
      setBuckets(data.buckets); setTotal(data.total);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Aging · Total Outstanding {inr(total)}</CardTitle>
        <Button onClick={load}>Refresh</Button>
      </CardHeader>
      <CardContent>
        {buckets ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(buckets).map(([k, v]) => (
              <div key={k} className="p-4 border rounded bg-slate-50">
                <div className="text-xs uppercase text-muted-foreground">{k} days</div>
                <div className="text-2xl font-bold mt-1">{inr(v)}</div>
                <div className="text-xs text-muted-foreground mt-1">{total > 0 ? Math.round((v / total) * 100) : 0}%</div>
              </div>
            ))}
          </div>
        ) : <div className="text-sm text-muted-foreground">Click Refresh to load aging buckets</div>}
      </CardContent>
    </Card>
  );
}

function ImportTab() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!file) { toast.error("Pick a CSV file"); return; }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/advances/bulk-import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`Imported ${data.created} row(s) · ${data.errors.length} error(s)`);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  const downloadTemplate = () => {
    const csv = "employee_code,advance_type,approved_amount,paid_amount,recovered_amount,outstanding,installments,emi,repayment_start_month,reason,remarks\nE-1006,Salary Advance,50000,50000,20000,30000,10,5000,2026-04,Family event,Migrated from spreadsheet\n";
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "advance-import-template.csv"; a.click();
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Bulk Import Historical Advances (CSV)</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="text-xs p-3 border rounded bg-blue-50">
          <strong>Required columns:</strong> employee_code, advance_type, approved_amount, installments, emi, repayment_start_month · <strong>Optional:</strong> paid_amount, recovered_amount, outstanding, reason, remarks, request_date.
          Rows are imported directly as <code>under_recovery</code> (or <code>closed</code> if outstanding ≤ 0) — no approval workflow.
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={downloadTemplate} data-testid="dl-template-btn"><Download className="h-4 w-4 mr-1" /> Download Template</Button>
          <Input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0])} className="max-w-md" data-testid="import-file" />
          <Button onClick={submit} disabled={busy || !file} data-testid="import-submit-btn"><Upload className="h-4 w-4 mr-1" />{busy ? "Importing…" : "Import"}</Button>
        </div>
        {result && (
          <div className="space-y-2">
            <div className="text-sm"><Badge className="bg-emerald-100 text-emerald-700 mr-2">{result.created}</Badge>created · <Badge className="bg-rose-100 text-rose-700 mx-2">{result.errors.length}</Badge>errors</div>
            {result.samples?.length > 0 && (
              <div className="text-xs"><strong>Samples:</strong> {result.samples.map((s) => `${s.advance_no} (${s.employee})`).join(", ")}</div>
            )}
            {result.errors.length > 0 && (
              <div className="border rounded max-h-60 overflow-y-auto p-2 bg-rose-50 text-xs">
                {result.errors.map((e, i) => <div key={i}><strong>Line {e.line}:</strong> {e.error}</div>)}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
