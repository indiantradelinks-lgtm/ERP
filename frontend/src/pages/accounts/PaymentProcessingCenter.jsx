import { useEffect, useMemo, useState, useCallback } from "react";
import { RefreshCw, Wallet, CheckCircle2, Banknote, Paperclip, Download, FileSpreadsheet, IndianRupee } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import RowAttachments from "@/components/RowAttachments";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const STAGE_BADGE = {
  pending_verification: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Verification</Badge>,
  verified: <Badge className="rounded-sm bg-blue-100 text-blue-900 border-blue-300">Verified</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
  in_bank_file: <Badge className="rounded-sm bg-violet-100 text-violet-900 border-violet-300">In Bank File</Badge>,
  paid: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Paid</Badge>,
};

const blankVerify = (row) => ({
  decision: "verified", vendor_name: row?.vendor || "", vendor_account_no: "", ifsc: "", bank_name: "",
  gst_applicable: false, gstin: "", gst_amount: 0,
  invoice_type: "bill", invoice_no: "", invoice_date: "",
  verified_amount: Number(row?.est_value || 0),
  tds_applicable: false, tds_pct: 0, tds_amount: 0, advance_adjusted: 0,
  expense_account_code: "5150", remarks: "",
});

function Kpi({ label, value, sub, icon: Icon, testid }) {
  return (
    <div className="border rounded-sm bg-white p-3 flex items-start gap-3" data-testid={testid}>
      <div className="p-2 rounded-sm bg-slate-100"><Icon className="h-4 w-4 text-slate-600" /></div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-lg font-semibold">{value}</div>
        {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
      </div>
    </div>
  );
}

function QueueTable({ rows, cols, renderActions, emptyText, testid }) {
  return (
    <div className="border rounded-sm bg-white overflow-x-auto" data-testid={testid}>
      <Table>
        <TableHeader>
          <TableRow>
            {cols.map((c) => <TableHead key={c} className="text-[11px] uppercase tracking-wider whitespace-nowrap">{c}</TableHead>)}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 && (
            <TableRow><TableCell colSpan={cols.length} className="text-center text-sm text-slate-500 py-8">{emptyText}</TableCell></TableRow>
          )}
          {rows.map(renderActions)}
        </TableBody>
      </Table>
    </div>
  );
}

export default function PaymentProcessingCenter() {
  const { can } = useAuth();
  const canWrite = !!can && can("accounting", "write");
  const [rows, setRows] = useState([]);
  const [bankFiles, setBankFiles] = useState([]);
  const [coa, setCoa] = useState([]);
  const [loading, setLoading] = useState(true);
  const [verifyFor, setVerifyFor] = useState(null);
  const [vform, setVform] = useState(blankVerify(null));
  const [attachFor, setAttachFor] = useState(null);
  const [selected, setSelected] = useState({});
  const [payFor, setPayFor] = useState(null);
  const [payForm, setPayForm] = useState({ utr_no: "", paid_date: new Date().toISOString().slice(0, 10) });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [q, bf] = await Promise.all([
        api.get("/accounts/payment-queue"),
        api.get("/accounts/payment-queue/bank-files"),
      ]);
      setRows(q.data || []);
      setBankFiles(bf.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load payment queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/accounts/chart-of-accounts").then((r) => setCoa(r.data || [])).catch(() => {});
  }, []);

  const byStage = useMemo(() => {
    const g = { pending: [], verified: [], bank: [], paid: [] };
    rows.forEach((r) => {
      const s = r.pay_stage;
      if (s === "verified") g.verified.push(r);
      else if (s === "in_bank_file") g.bank.push(r);
      else if (s === "paid") g.paid.push(r);
      else g.pending.push(r); // pending_verification + rejected (re-verifiable)
    });
    return g;
  }, [rows]);

  const expenseAccounts = useMemo(() => coa.filter((a) => a.type === "expense"), [coa]);

  const openVerify = (row) => {
    const v = row.verification;
    setVform(v ? { ...blankVerify(row), ...v, decision: "verified" } : blankVerify(row));
    setVerifyFor(row);
  };

  const netPayable = Math.round((Number(vform.verified_amount || 0) - Number(vform.tds_amount || 0) - Number(vform.advance_adjusted || 0)) * 100) / 100;

  const setTds = (patch) => {
    const next = { ...vform, ...patch };
    if (next.tds_applicable) {
      const pct = Number(next.tds_pct || 0);
      if (patch.tds_pct !== undefined || patch.verified_amount !== undefined || patch.tds_applicable) {
        next.tds_amount = Math.round(Number(next.verified_amount || 0) * pct) / 100;
      }
    } else {
      next.tds_pct = 0; next.tds_amount = 0;
    }
    setVform(next);
  };

  const submitVerify = async (decision) => {
    setBusy(true);
    try {
      await api.post(`/accounts/payment-queue/${verifyFor.id}/verify`, {
        ...vform, decision,
        verified_amount: Number(vform.verified_amount || 0), gst_amount: Number(vform.gst_amount || 0),
        tds_pct: Number(vform.tds_pct || 0), tds_amount: Number(vform.tds_amount || 0),
        advance_adjusted: Number(vform.advance_adjusted || 0),
      });
      toast.success(decision === "verified" ? "Payment verified — ready for bank file" : "Payment rejected");
      setVerifyFor(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Verification failed");
    } finally { setBusy(false); }
  };

  const downloadBlob = (data, name) => {
    const url = URL.createObjectURL(new Blob([data]));
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  };

  const generateBankFile = async () => {
    const ids = Object.keys(selected).filter((k) => selected[k]);
    if (!ids.length) { toast.error("Select at least one verified payment"); return; }
    setBusy(true);
    try {
      const res = await api.post("/accounts/payment-queue/bank-file",
        { request_ids: ids, payment_mode: "NEFT" }, { responseType: "blob" });
      const fileNo = res.headers["x-file-no"] || "BANK_PAYMENT";
      downloadBlob(res.data, `${fileNo}.xlsx`);
      toast.success(`Bank file ${fileNo} generated & downloaded`);
      setSelected({});
      load();
    } catch (e) {
      let msg = "Bank file generation failed";
      try { msg = JSON.parse(await e?.response?.data?.text())?.detail || msg; } catch { /* noop */ }
      toast.error(msg);
    } finally { setBusy(false); }
  };

  const downloadBankFile = async (f) => {
    try {
      const res = await api.get(`/accounts/payment-queue/bank-files/${f.id}/download`, { responseType: "blob" });
      downloadBlob(res.data, `${f.file_no}.xlsx`);
    } catch { toast.error("Download failed"); }
  };

  const markPaid = async () => {
    if (!payForm.utr_no.trim()) { toast.error("UTR number is required"); return; }
    setBusy(true);
    try {
      await api.post(`/accounts/payment-queue/${payFor.id}/mark-paid`, payForm);
      toast.success("Marked paid — Journal Entry posted");
      setPayFor(null);
      setPayForm({ utr_no: "", paid_date: new Date().toISOString().slice(0, 10) });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mark paid failed");
    } finally { setBusy(false); }
  };

  const baseCells = (r) => (
    <>
      <TableCell className="font-mono text-xs whitespace-nowrap">{r.request_no}</TableCell>
      <TableCell className="text-xs">{r.request_type_label}</TableCell>
      <TableCell className="text-xs whitespace-nowrap">{r.project_code}</TableCell>
      <TableCell className="text-xs">{r.verification?.vendor_name || r.vendor || "—"}</TableCell>
    </>
  );

  const attachBtn = (r) => (
    <Button size="sm" variant="ghost" className="rounded-sm h-7 px-2" onClick={() => setAttachFor(r)}
      data-testid={`ppc-attach-${r.request_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
  );

  const paidThisMonth = byStage.paid.reduce((s, r) => s + Number(r.verification?.verified_amount || 0), 0);

  return (
    <div className="p-4 md:p-6 space-y-4" data-testid="payment-processing-center">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2"><Wallet className="h-5 w-5" /> Payment Processing Center</h1>
          <p className="text-xs text-slate-500">Approved departmental payment requests → verify → bank file → mark paid (auto Journal Entry)</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm" onClick={load} data-testid="ppc-refresh">
          <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Pending Verification" value={byStage.pending.length} icon={Wallet} testid="ppc-kpi-pending" />
        <Kpi label="Verified — Ready for Bank" value={byStage.verified.length} icon={CheckCircle2} testid="ppc-kpi-verified" />
        <Kpi label="In Bank File" value={byStage.bank.length} icon={FileSpreadsheet} testid="ppc-kpi-bank" />
        <Kpi label="Paid" value={byStage.paid.length} sub={inr(paidThisMonth)} icon={IndianRupee} testid="ppc-kpi-paid" />
      </div>

      <Tabs defaultValue="pending">
        <TabsList className="rounded-sm">
          <TabsTrigger value="pending" className="rounded-sm text-xs" data-testid="ppc-tab-pending">Pending Verification ({byStage.pending.length})</TabsTrigger>
          <TabsTrigger value="verified" className="rounded-sm text-xs" data-testid="ppc-tab-verified">Verified / Bank File ({byStage.verified.length})</TabsTrigger>
          <TabsTrigger value="bank" className="rounded-sm text-xs" data-testid="ppc-tab-bank">Bank Files & Mark Paid ({byStage.bank.length})</TabsTrigger>
          <TabsTrigger value="paid" className="rounded-sm text-xs" data-testid="ppc-tab-paid">Paid History ({byStage.paid.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="mt-3">
          <QueueTable testid="ppc-pending-table" emptyText="No payments awaiting verification"
            cols={["Request No", "Type", "Project", "Vendor", "Est. Value", "Stage", "Docs", "Action"]}
            rows={byStage.pending}
            renderActions={(r) => (
              <TableRow key={r.id} data-testid={`ppc-pending-row-${r.request_no}`}>
                {baseCells(r)}
                <TableCell className="text-xs whitespace-nowrap">{inr(r.est_value)}</TableCell>
                <TableCell>{STAGE_BADGE[r.pay_stage] || r.pay_stage}</TableCell>
                <TableCell>{attachBtn(r)}</TableCell>
                <TableCell>
                  {canWrite && <Button size="sm" className="rounded-sm h-7" onClick={() => openVerify(r)}
                    data-testid={`ppc-verify-btn-${r.request_no}`}>Verify</Button>}
                </TableCell>
              </TableRow>
            )} />
        </TabsContent>

        <TabsContent value="verified" className="mt-3 space-y-3">
          <div className="flex justify-end">
            {canWrite && <Button size="sm" className="rounded-sm" onClick={generateBankFile} disabled={busy}
              data-testid="ppc-generate-bank-file">
              <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Generate Bank File ({Object.values(selected).filter(Boolean).length})
            </Button>}
          </div>
          <QueueTable testid="ppc-verified-table" emptyText="No verified payments waiting for a bank file"
            cols={["", "Request No", "Type", "Project", "Vendor", "Verified Amt", "TDS", "Advance Adj.", "Net Payable", "Docs"]}
            rows={byStage.verified}
            renderActions={(r) => {
              const v = r.verification || {};
              const net = v.net_payable !== undefined && v.net_payable !== null ? v.net_payable : v.verified_amount;
              return (
                <TableRow key={r.id} data-testid={`ppc-verified-row-${r.request_no}`}>
                  <TableCell>
                    <Checkbox checked={!!selected[r.id]} onCheckedChange={(c) => setSelected((p) => ({ ...p, [r.id]: !!c }))}
                      data-testid={`ppc-select-${r.request_no}`} />
                  </TableCell>
                  {baseCells(r)}
                  <TableCell className="text-xs whitespace-nowrap">{inr(v.verified_amount)}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{v.tds_amount ? inr(v.tds_amount) : "—"}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{v.advance_adjusted ? inr(v.advance_adjusted) : "—"}</TableCell>
                  <TableCell className="text-xs font-semibold whitespace-nowrap">{inr(net)}</TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                </TableRow>
              );
            }} />
        </TabsContent>

        <TabsContent value="bank" className="mt-3 space-y-4">
          <QueueTable testid="ppc-bank-table" emptyText="No payments in bank files awaiting UTR"
            cols={["Request No", "Type", "Project", "Vendor", "Net Payable", "Bank File", "Docs", "Action"]}
            rows={byStage.bank}
            renderActions={(r) => {
              const v = r.verification || {};
              return (
                <TableRow key={r.id} data-testid={`ppc-bank-row-${r.request_no}`}>
                  {baseCells(r)}
                  <TableCell className="text-xs font-semibold whitespace-nowrap">{inr(v.net_payable ?? v.verified_amount)}</TableCell>
                  <TableCell className="text-xs font-mono">{v.bank_file_no || "—"}</TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                  <TableCell>
                    {canWrite && <Button size="sm" className="rounded-sm h-7 bg-emerald-600 hover:bg-emerald-700"
                      onClick={() => setPayFor(r)} data-testid={`ppc-mark-paid-btn-${r.request_no}`}>
                      <Banknote className="h-3.5 w-3.5 mr-1" /> Mark Paid</Button>}
                  </TableCell>
                </TableRow>
              );
            }} />

          <div>
            <h3 className="text-sm font-semibold mb-2">Generated Bank Files</h3>
            <QueueTable testid="ppc-bank-files-table" emptyText="No bank files generated yet"
              cols={["File No", "Payments", "Total", "Mode", "Created By", "Created At", "Download"]}
              rows={bankFiles}
              renderActions={(f) => (
                <TableRow key={f.id} data-testid={`ppc-bank-file-${f.file_no}`}>
                  <TableCell className="font-mono text-xs">{f.file_no}</TableCell>
                  <TableCell className="text-xs">{(f.rows || []).length}</TableCell>
                  <TableCell className="text-xs font-semibold">{inr(f.total_amount)}</TableCell>
                  <TableCell className="text-xs">{f.payment_mode}</TableCell>
                  <TableCell className="text-xs">{f.created_by}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{(f.created_at || "").slice(0, 16).replace("T", " ")}</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" className="rounded-sm h-7" onClick={() => downloadBankFile(f)}
                      data-testid={`ppc-download-${f.file_no}`}><Download className="h-3.5 w-3.5" /></Button>
                  </TableCell>
                </TableRow>
              )} />
          </div>
        </TabsContent>

        <TabsContent value="paid" className="mt-3">
          <QueueTable testid="ppc-paid-table" emptyText="No payments completed yet"
            cols={["Request No", "Type", "Project", "Vendor", "Paid Amt", "UTR", "Paid Date", "Voucher", "Docs"]}
            rows={byStage.paid}
            renderActions={(r) => {
              const v = r.verification || {};
              return (
                <TableRow key={r.id} data-testid={`ppc-paid-row-${r.request_no}`}>
                  {baseCells(r)}
                  <TableCell className="text-xs font-semibold whitespace-nowrap">{inr(v.net_payable ?? v.verified_amount)}</TableCell>
                  <TableCell className="text-xs font-mono">{v.utr_no}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{v.paid_date}</TableCell>
                  <TableCell className="text-xs font-mono">{v.voucher_number || "—"}</TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                </TableRow>
              );
            }} />
        </TabsContent>
      </Tabs>

      {/* ── Verify dialog ── */}
      <Dialog open={!!verifyFor} onOpenChange={(o) => !o && setVerifyFor(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm">
          <DialogHeader>
            <DialogTitle className="text-base">Verify Payment — {verifyFor?.request_no}</DialogTitle>
            <DialogDescription className="text-xs">
              {verifyFor?.request_type_label} · {verifyFor?.project_code} · Requested {inr(verifyFor?.est_value)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Vendor / Beneficiary Name *</Label>
                <Input value={vform.vendor_name} onChange={(e) => setVform({ ...vform, vendor_name: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-vendor" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Bank Name</Label>
                <Input value={vform.bank_name} onChange={(e) => setVform({ ...vform, bank_name: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-bank" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Account Number *</Label>
                <Input value={vform.vendor_account_no} onChange={(e) => setVform({ ...vform, vendor_account_no: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-account" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">IFSC *</Label>
                <Input value={vform.ifsc} onChange={(e) => setVform({ ...vform, ifsc: e.target.value.toUpperCase() })}
                  className="rounded-sm mt-1" data-testid="ppc-v-ifsc" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 border rounded-sm p-3 bg-slate-50">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Invoice Type</Label>
                <Select value={vform.invoice_type} onValueChange={(v) => setVform({ ...vform, invoice_type: v })}>
                  <SelectTrigger className="rounded-sm mt-1 h-9" data-testid="ppc-v-invtype"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bill">Tax Invoice / Bill</SelectItem>
                    <SelectItem value="proforma">Proforma Invoice</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Invoice No *</Label>
                <Input value={vform.invoice_no} onChange={(e) => setVform({ ...vform, invoice_no: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-invno" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Invoice Date</Label>
                <Input type="date" value={vform.invoice_date} onChange={(e) => setVform({ ...vform, invoice_date: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-invdate" />
              </div>
              <div className="flex items-center gap-2 pt-1 col-span-1">
                <Checkbox checked={vform.gst_applicable} onCheckedChange={(c) => setVform({ ...vform, gst_applicable: !!c })}
                  data-testid="ppc-v-gst-check" />
                <Label className="text-xs">GST Applicable</Label>
              </div>
              {vform.gst_applicable && (
                <>
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider">GSTIN *</Label>
                    <Input value={vform.gstin} onChange={(e) => setVform({ ...vform, gstin: e.target.value.toUpperCase() })}
                      className="rounded-sm mt-1" data-testid="ppc-v-gstin" />
                  </div>
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider">GST Amount</Label>
                    <Input type="number" value={vform.gst_amount} onChange={(e) => setVform({ ...vform, gst_amount: e.target.value })}
                      className="rounded-sm mt-1" data-testid="ppc-v-gstamt" />
                  </div>
                </>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Verified Amount (Gross) *</Label>
                <Input type="number" value={vform.verified_amount}
                  onChange={(e) => setTds({ verified_amount: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-amount" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Expense Account</Label>
                <Select value={vform.expense_account_code} onValueChange={(v) => setVform({ ...vform, expense_account_code: v })}>
                  <SelectTrigger className="rounded-sm mt-1 h-9" data-testid="ppc-v-expacct"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-64">
                    {expenseAccounts.map((a) => (
                      <SelectItem key={a.code} value={a.code}>{a.code} — {a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="border rounded-sm p-3 bg-amber-50/50 space-y-3">
              <div className="flex items-center gap-2">
                <Checkbox checked={vform.tds_applicable} onCheckedChange={(c) => setTds({ tds_applicable: !!c })}
                  data-testid="ppc-v-tds-check" />
                <Label className="text-xs font-medium">TDS Deduction</Label>
              </div>
              {vform.tds_applicable && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider">TDS %</Label>
                    <Input type="number" value={vform.tds_pct} onChange={(e) => setTds({ tds_pct: e.target.value })}
                      className="rounded-sm mt-1" data-testid="ppc-v-tds-pct" />
                  </div>
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider">TDS Amount</Label>
                    <Input type="number" value={vform.tds_amount} onChange={(e) => setVform({ ...vform, tds_amount: e.target.value })}
                      className="rounded-sm mt-1" data-testid="ppc-v-tds-amt" />
                  </div>
                </div>
              )}
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Vendor Advance Adjusted</Label>
                <Input type="number" value={vform.advance_adjusted}
                  onChange={(e) => setVform({ ...vform, advance_adjusted: e.target.value })}
                  className="rounded-sm mt-1" data-testid="ppc-v-advance" />
                <p className="text-[10px] text-slate-500 mt-1">Amount already paid as advance to this vendor (credits Vendor Advances 1510)</p>
              </div>
              <div className="flex justify-between items-center border-t pt-2">
                <span className="text-xs font-medium">Net Payable to Bank</span>
                <span className={`text-sm font-bold ${netPayable < 0 ? "text-red-600" : ""}`} data-testid="ppc-v-net">{inr(netPayable)}</span>
              </div>
            </div>

            <div>
              <Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
              <Textarea value={vform.remarks} onChange={(e) => setVform({ ...vform, remarks: e.target.value })}
                className="rounded-sm mt-1 min-h-[60px]" data-testid="ppc-v-remarks" />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" className="rounded-sm" onClick={() => setAttachFor(verifyFor)} data-testid="ppc-v-docs">
              <Paperclip className="h-3.5 w-3.5 mr-1" /> View Documents
            </Button>
            <Button variant="destructive" className="rounded-sm" disabled={busy} onClick={() => submitVerify("rejected")}
              data-testid="ppc-v-reject">Reject</Button>
            <Button className="rounded-sm" disabled={busy || netPayable < 0} onClick={() => submitVerify("verified")}
              data-testid="ppc-v-submit">Verify Payment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Mark Paid dialog ── */}
      <Dialog open={!!payFor} onOpenChange={(o) => !o && setPayFor(null)}>
        <DialogContent className="max-w-sm rounded-sm">
          <DialogHeader>
            <DialogTitle className="text-base">Mark Paid — {payFor?.request_no}</DialogTitle>
            <DialogDescription className="text-xs">
              {payFor?.verification?.vendor_name} · Net {inr(payFor?.verification?.net_payable ?? payFor?.verification?.verified_amount)}.
              Posts Journal Entry (DR expense / CR bank{Number(payFor?.verification?.tds_amount) > 0 ? " / CR TDS Payable" : ""}{Number(payFor?.verification?.advance_adjusted) > 0 ? " / CR Vendor Advances" : ""}).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">UTR / Transaction Ref *</Label>
              <Input value={payForm.utr_no} onChange={(e) => setPayForm({ ...payForm, utr_no: e.target.value })}
                className="rounded-sm mt-1" data-testid="ppc-pay-utr" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Paid Date *</Label>
              <Input type="date" value={payForm.paid_date} onChange={(e) => setPayForm({ ...payForm, paid_date: e.target.value })}
                className="rounded-sm mt-1" data-testid="ppc-pay-date" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setPayFor(null)}>Cancel</Button>
            <Button className="rounded-sm bg-emerald-600 hover:bg-emerald-700" disabled={busy} onClick={markPaid}
              data-testid="ppc-pay-submit">Confirm Paid</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
        parentType="project_requests" parentId={attachFor?.id}
        recordTitle={`Documents — ${attachFor?.request_no || ""}`} />
    </div>
  );
}
