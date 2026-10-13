import { useEffect, useMemo, useState, useCallback } from "react";
import { RefreshCw, Wallet, CheckCircle2, Banknote, Paperclip, Download, FileSpreadsheet, IndianRupee, XCircle } from "lucide-react";
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
import BulkUtrDialog from "@/components/BulkUtrDialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import RowAttachments from "@/components/RowAttachments";
import useAutoSync from "@/hooks/useAutoSync";
import { fmtDT } from "@/lib/datetime";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const STAGE_BADGE = {
  pending_verification: <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900 bg-amber-50">Pending Verification</Badge>,
  verified: <Badge className="rounded-sm bg-blue-100 text-blue-900 border-blue-300">Verified</Badge>,
  rejected: <Badge variant="destructive" className="rounded-sm">Rejected</Badge>,
  in_bank_file: <Badge className="rounded-sm bg-violet-100 text-violet-900 border-violet-300">In Bank File</Badge>,
  paid: <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300">Paid</Badge>,
};

const blankVerify = (row) => {
  const vb = row?.vendor_master?.bank;
  const vm = row?.vendor_master;
  return {
    decision: "verified",
    vendor_name: vb?.beneficiary_name || vm?.name || row?.vendor
      || row?.employee_bank?.beneficiary_name || row?.employee_name || row?.upi_any_name || "",
    vendor_account_no: vb?.account_no || row?.employee_bank?.account_no || "",
    ifsc: (vb?.ifsc || row?.employee_bank?.ifsc || "").toUpperCase(),
    bank_name: vb?.bank_name || row?.employee_bank?.bank_name || "",
    vendor_email: vm?.email || "",
    gst_applicable: !!vm?.gstin, gstin: vm?.gstin || "", gst_amount: 0,
    invoice_type: "bill", invoice_no: row?.invoice_no || "", invoice_date: row?.invoice_date || "",
    verified_amount: Number(row?.est_value || 0),
    tds_applicable: false, tds_pct: 0, tds_amount: 0, advance_adjusted: 0,
    expense_account_code: row?.pay_debit_account_code || "5150", remarks: "",
  };
};

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

function ExportButtons({ stage }) {
  const dl = async (fmt) => {
    try {
      const res = await api.get(`/accounts/payment-queue/export/${fmt}?stage=${stage}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `Payment-${stage}.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("Export failed"); }
  };
  return (
    <div className="flex justify-end gap-2 mb-2">
      <Button size="sm" variant="outline" className="h-7 rounded-sm text-xs" onClick={() => dl("xlsx")} data-testid={`ppc-export-xlsx-${stage}`}>Excel</Button>
      <Button size="sm" variant="outline" className="h-7 rounded-sm text-xs" onClick={() => dl("pdf")} data-testid={`ppc-export-pdf-${stage}`}>PDF</Button>
    </div>
  );
}

function QueueTable({ rows, cols, renderActions, emptyText, testid }) {
  return (
    <div className="border rounded-sm bg-white overflow-x-auto" data-testid={testid}>
      <Table>
        <TableHeader>
          <TableRow>
            {cols.map((c, i) => <TableHead key={i} className="text-[11px] uppercase tracking-wider whitespace-nowrap">{c}</TableHead>)}
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
  const [saveBank, setSaveBank] = useState(false);
  const [saveVendorBank, setSaveVendorBank] = useState(false);
  const [reportDate, setReportDate] = useState(new Date().toISOString().slice(0, 10));
  const [reportTo, setReportTo] = useState("");
  const [report, setReport] = useState({ label: "", rows: [], totals: {} });
  const [reportLoading, setReportLoading] = useState(false);
  const [tab, setTab] = useState("pending");
  const [attachFor, setAttachFor] = useState(null);
  const [selected, setSelected] = useState({});
  const [payFor, setPayFor] = useState(null);
  const [payForm, setPayForm] = useState({ utr_no: "", paid_date: new Date().toISOString().slice(0, 10) });
  const [debitAcNo, setDebitAcNo] = useState(localStorage.getItem("ppc_debit_ac_no") || "169405500094");
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({ q: "", status: "all", basis: "raised", from: "", to: "" });
  const [rejectFor, setRejectFor] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  const stageDate = (r, basis) => {
    const v = r.verification || {};
    if (basis === "verified") return (v.verified_at || "").slice(0, 10);
    if (basis === "paid") return (v.paid_date || v.paid_at || "").slice(0, 10);
    return (r.created_at || "").slice(0, 10);
  };

  const filteredRows = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filters.status !== "all" && r.pay_stage !== filters.status) return false;
      if (filters.from || filters.to) {
        const d = stageDate(r, filters.basis);
        if (!d) return false;
        if (filters.from && d < filters.from) return false;
        if (filters.to && d > filters.to) return false;
      }
      if (!q) return true;
      const v = r.verification || {};
      return [r.request_no, r.project_code, r.project_name, r.vendor, r.employee_name, r.employee_code,
        v.vendor_name, v.invoice_no, v.utr_no, r.request_type_label, r.cost_center_name, r.description,
        r.raised_by, v.bank_file_no]
        .some((f) => String(f || "").toLowerCase().includes(q));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, filters]);

  const filtersActive = filters.q || filters.status !== "all" || filters.from || filters.to;
  const STATUS_TO_TAB = { pending_verification: "pending", verified: "verified", in_bank_file: "bank", paid: "paid", rejected: "rejected" };
  const applyStatus = (s) => {
    setFilters((p) => ({ ...p, status: s }));
    if (STATUS_TO_TAB[s]) setTab(STATUS_TO_TAB[s]);
  };

  const submitReject = async () => {
    const reason = rejectReason.trim();
    if (reason.length < 3) { toast.error("Rejection reason is mandatory"); return; }
    setBusy(true);
    try {
      await api.post(`/accounts/payment-queue/${rejectFor.id}/reject-payment`, { reason });
      toast.success(`Payment ${rejectFor.request_no} rejected`);
      setRejectFor(null); setRejectReason("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reject the payment");
    } finally { setBusy(false); }
  };

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
  useAutoSync(async () => {
    const [q, bf] = await Promise.all([
      api.get("/accounts/payment-queue"),
      api.get("/accounts/payment-queue/bank-files"),
    ]);
    setRows(q.data || []);
    setBankFiles(bf.data || []);
  });
  useEffect(() => {
    api.get("/accounts/chart-of-accounts").then((r) => setCoa(r.data || [])).catch(() => {});
  }, []);

  const byStage = useMemo(() => {
    const g = { pending: [], verified: [], bank: [], paid: [], rejected: [] };
    filteredRows.forEach((r) => {
      const s = r.pay_stage;
      if (s === "verified") g.verified.push(r);
      else if (s === "in_bank_file") g.bank.push(r);
      else if (s === "paid") g.paid.push(r);
      else if (s === "rejected") g.rejected.push(r);
      else g.pending.push(r);
    });
    return g;
  }, [filteredRows]);

  const allByStage = useMemo(() => {
    const g = { pending: 0, verified: 0, bank: 0, paid: 0, rejected: 0, paidAmt: 0 };
    rows.forEach((r) => {
      const s = r.pay_stage;
      if (s === "verified") g.verified += 1;
      else if (s === "in_bank_file") g.bank += 1;
      else if (s === "paid") { g.paid += 1; g.paidAmt += Number(r.verification?.verified_amount || 0); }
      else if (s === "rejected") g.rejected += 1;
      else g.pending += 1;
    });
    return g;
  }, [rows]);

  const expenseAccounts = useMemo(() => coa.filter((a) => a.type === "expense"), [coa]);

  const openVerify = (row) => {
    const v = row.verification;
    const base = blankVerify(row);
    setVform(v ? { ...base, ...Object.fromEntries(Object.entries(v).filter(([, val]) => val !== "" && val !== null && val !== undefined)), decision: "verified" } : base);
    setSaveBank(!!(row.employee_record_id || row.employee_id || row.employee_code) && !row.employee_bank);
    setSaveVendorBank(!!row.vendor_master && !(row.vendor_master.bank?.account_no && row.vendor_master.bank?.ifsc));
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
      if (decision === "verified" && saveBank &&
          (verifyFor.employee_record_id || verifyFor.employee_id || verifyFor.employee_code)) {
        await api.post(`/accounts/payment-queue/${verifyFor.id}/save-bank-details`, {
          beneficiary_name: vform.vendor_name, bank_name: vform.bank_name,
          account_no: vform.vendor_account_no, ifsc: vform.ifsc,
        });
        toast.success("Bank details saved to Employee Master");
      }
      if (decision === "verified" && saveVendorBank && verifyFor.vendor_master) {
        try {
          await api.post(`/accounts/payment-queue/${verifyFor.id}/save-vendor-bank-details`, {
            beneficiary_name: vform.vendor_name, bank_name: vform.bank_name,
            account_no: vform.vendor_account_no, ifsc: vform.ifsc,
          });
          toast.success(`Bank details saved to Vendor Master — ${verifyFor.vendor_master.name}`);
        } catch (e) {
          toast.error(e?.response?.data?.detail || "Could not save bank details to Vendor Master");
        }
      }
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
    if (!debitAcNo.trim()) { toast.error("Debit A/c No is required"); return; }
    localStorage.setItem("ppc_debit_ac_no", debitAcNo.trim());
    setBusy(true);
    try {
      const res = await api.post("/accounts/payment-queue/bank-file",
        { request_ids: ids, debit_ac_no: debitAcNo.trim() }, { responseType: "blob" });
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
      const res = await api.post(`/accounts/payment-queue/${payFor.id}/mark-paid`, payForm);
      const adv = res.data?.advice_status;
      if (adv === "sent" || adv === "queued") toast.success(`Marked paid — JE posted · payment advice emailed to ${res.data.advice_to}`);
      else if (adv === "no_email") toast.success("Marked paid — JE posted (no vendor email on record, advice not sent)");
      else toast.success("Marked paid — Journal Entry posted");
      setPayFor(null);
      setPayForm({ utr_no: "", paid_date: new Date().toISOString().slice(0, 10) });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mark paid failed");
    } finally { setBusy(false); }
  };

  const selectedCount = Object.values(selected).filter(Boolean).length;
  const allVerifiedSelected = byStage.verified.length > 0 && byStage.verified.every((r) => selected[r.id]);
  const selectedTotal = byStage.verified.reduce((s, r) => selected[r.id]
    ? s + Number(r.verification?.net_payable ?? r.verification?.verified_amount ?? 0) : s, 0);
  const toggleSelectAll = (checked) => {
    if (checked) {
      const next = {};
      byStage.verified.forEach((r) => { next[r.id] = true; });
      setSelected(next);
    } else setSelected({});
  };

  const loadReport = useCallback(async (d = reportDate, to = reportTo) => {
    if (!d) return;
    setReportLoading(true);
    try {
      const params = to && to !== d ? { date_from: d, date_to: to } : { date: d };
      const r = await api.get("/accounts/payment-queue/verification-report", { params });
      setReport(r.data || { label: "", rows: [], totals: {} });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load payment report");
    } finally { setReportLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportDate, reportTo]);

  const saveReportRemark = async (row, remarks) => {
    setReport((p) => ({ ...p, rows: p.rows.map((x) => x.request_id === row.request_id ? { ...x, remarks } : x) }));
    try {
      await api.patch(`/accounts/payment-queue/${row.request_id}/report-remarks`, { remarks });
    } catch (e) { toast.error("Could not save remark"); }
  };

  const downloadReport = async (fmt) => {
    try {
      const params = reportTo && reportTo !== reportDate
        ? `date_from=${reportDate}&date_to=${reportTo}` : `date=${reportDate}`;
      const res = await api.get(`/accounts/payment-queue/verification-report/export/${fmt}?${params}`,
        { responseType: "blob" });
      downloadBlob(res.data, `Payment-Verification-Report-${reportDate}.${fmt}`);
    } catch { toast.error("Download failed"); }
  };

  const baseCells = (r) => (
    <>
      <TableCell className="font-mono text-xs whitespace-nowrap">{r.request_no}</TableCell>
      <TableCell className="text-xs">
        <div>{r.request_type_label}</div>
        {r.cost_center_name && (
          <div className="text-[10px] text-slate-500 max-w-[160px] truncate" title={r.cost_center_name}
            data-testid={`ppc-cc-${r.request_no}`}>CC: {r.cost_center_name}</div>
        )}
        {r.source === "advance" && r.raised_by && (
          <div className="text-[10px] text-slate-500 whitespace-nowrap" data-testid={`ppc-raised-by-${r.request_no}`}>Raised by: {r.raised_by}</div>
        )}
      </TableCell>
      <TableCell className="text-xs">
        <div className="whitespace-nowrap font-medium">{r.project_code}</div>
        <div className="text-[10px] text-slate-500 max-w-[180px] truncate" title={r.project_name}>{r.project_name}</div>
        {r.project_manager && <div className="text-[10px] text-slate-500 whitespace-nowrap">PM: {r.project_manager}</div>}
      </TableCell>
      <TableCell className="text-xs">
        <div>{r.verification?.vendor_name || r.vendor || (r.employee_name ? "" : (r.upi_any_name || "—"))}</div>
        {r.employee_name && <div className="text-[10px] text-slate-500 whitespace-nowrap">{r.employee_code ? `${r.employee_code} · ` : ""}{r.employee_name}</div>}
        {r.upi_any_name && !r.vendor && !r.employee_name && <div className="text-[10px] text-amber-600">Manual name (UPI)</div>}
      </TableCell>
      <TableCell className="text-xs whitespace-nowrap" data-testid={`ppc-approved-at-${r.request_no}`}>
        {r.approved_at ? (
          <>
            <div>{fmtDT(r.approved_at)}</div>
            {r.approved_by && <div className="text-[10px] text-slate-500">by {r.approved_by}</div>}
          </>
        ) : <span className="text-slate-400">—</span>}
      </TableCell>
    </>
  );

  const attachBtn = (r) => (
    <Button size="sm" variant="ghost" className="rounded-sm h-7 px-2" onClick={() => setAttachFor(r)}
      data-testid={`ppc-attach-${r.request_no}`}><Paperclip className="h-3.5 w-3.5" /></Button>
  );

  const upiRows = rows.filter((r) => r.payment_mode === "UPI" && String(r.priority || "").toLowerCase() === "high"
    && ["pending_verification", "verified", "rejected"].includes(r.pay_stage));

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

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Pending Verification" value={allByStage.pending} icon={Wallet} testid="ppc-kpi-pending" />
        <Kpi label="Verified — Ready for Bank" value={allByStage.verified} icon={CheckCircle2} testid="ppc-kpi-verified" />
        <Kpi label="In Bank File" value={allByStage.bank} icon={FileSpreadsheet} testid="ppc-kpi-bank" />
        <Kpi label="Paid" value={allByStage.paid} sub={inr(allByStage.paidAmt)} icon={IndianRupee} testid="ppc-kpi-paid" />
        <Kpi label="Rejected" value={allByStage.rejected} icon={XCircle} testid="ppc-kpi-rejected" />
      </div>

      <div className="border rounded-sm bg-white p-3 flex items-end gap-3 flex-wrap" data-testid="ppc-filters">
        <div className="flex-1 min-w-[220px]">
          <Label className="text-[10px] uppercase tracking-wider">Search</Label>
          <Input value={filters.q} onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
            placeholder="Request no, vendor, project, UTR, invoice…"
            className="rounded-sm mt-1 h-9" data-testid="ppc-filter-search" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Payment Stage / Status</Label>
          <select value={filters.status} onChange={(e) => applyStatus(e.target.value)}
            className="mt-1 h-9 w-52 border rounded-sm text-sm px-2 bg-white" data-testid="ppc-filter-status">
            <option value="all">All stages</option>
            <option value="pending_verification">Pending Verification</option>
            <option value="verified">Verified — Ready for Bank</option>
            <option value="in_bank_file">In Bank File</option>
            <option value="paid">Paid</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Date Basis</Label>
          <select value={filters.basis} onChange={(e) => setFilters((p) => ({ ...p, basis: e.target.value }))}
            className="mt-1 h-9 w-36 border rounded-sm text-sm px-2 bg-white" data-testid="ppc-filter-basis">
            <option value="raised">Raised On</option>
            <option value="verified">Verified On</option>
            <option value="paid">Paid On</option>
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">From</Label>
          <Input type="date" value={filters.from} onChange={(e) => setFilters((p) => ({ ...p, from: e.target.value }))}
            className="rounded-sm mt-1 h-9 w-40" data-testid="ppc-filter-from" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">To</Label>
          <Input type="date" value={filters.to} onChange={(e) => setFilters((p) => ({ ...p, to: e.target.value }))}
            className="rounded-sm mt-1 h-9 w-40" data-testid="ppc-filter-to" />
        </div>
        {filtersActive && (
          <Button size="sm" variant="ghost" className="rounded-sm h-9 text-xs"
            onClick={() => setFilters({ q: "", status: "all", basis: "raised", from: "", to: "" })}
            data-testid="ppc-filter-clear">Clear filters</Button>
        )}
        <div className="text-[11px] text-slate-500 ml-auto" data-testid="ppc-filter-count">
          {filteredRows.length} of {rows.length} payment(s)
        </div>
      </div>

      {upiRows.length > 0 && (
        <div className="border-2 border-amber-400 rounded-sm bg-amber-50/60" data-testid="ppc-upi-lane">
          <div className="px-3 py-2 border-b border-amber-300 flex items-center justify-between">
            <div className="text-sm font-semibold text-amber-900">⚡ UPI Quick Pay — HIGH priority ({upiRows.length})</div>
            <div className="text-[11px] text-amber-800">Requester chose UPI · verify &amp; mark paid directly with the UPI transaction reference — no bank file needed</div>
          </div>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Request No</TableHead><TableHead>Project</TableHead><TableHead>Paid To</TableHead>
              <TableHead>Amount</TableHead><TableHead>Stage</TableHead><TableHead className="text-right">Quick Action</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {upiRows.map((r) => {
                const v = r.verification || {};
                const net = v.net_payable ?? v.verified_amount ?? r.est_value;
                return (
                  <TableRow key={r.id} data-testid={`ppc-upi-row-${r.request_no}`}>
                    <TableCell className="font-mono text-xs">{r.request_no}<div className="text-[10px] text-amber-700 font-sans">UPI · HIGH</div></TableCell>
                    <TableCell className="text-xs">{r.project_code}</TableCell>
                    <TableCell className="text-xs">{v.vendor_name || r.vendor || r.employee_name || r.upi_any_name || "—"}{r.upi_any_name && !r.vendor && !r.employee_name ? <div className="text-[10px] text-amber-600">Manual name (UPI)</div> : ""}</TableCell>
                    <TableCell className="text-xs font-semibold whitespace-nowrap">{inr(net)}</TableCell>
                    <TableCell>{STAGE_BADGE[r.pay_stage] || r.pay_stage}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {canWrite && r.pay_stage !== "verified" &&
                        <Button size="sm" className="rounded-sm h-7" onClick={() => openVerify(r)} data-testid={`ppc-upi-verify-${r.request_no}`}>Verify</Button>}
                      {canWrite && r.pay_stage === "verified" &&
                        <Button size="sm" className="rounded-sm h-7 bg-amber-600 hover:bg-amber-700" onClick={() => setPayFor(r)} data-testid={`ppc-upi-pay-${r.request_no}`}>Quick Pay (UPI)</Button>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v === "report" && report.rows.length === 0) loadReport(); }}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="pending" className="rounded-sm text-xs" data-testid="ppc-tab-pending">Pending Verification ({byStage.pending.length})</TabsTrigger>
          <TabsTrigger value="verified" className="rounded-sm text-xs" data-testid="ppc-tab-verified">Verified / Bank File ({byStage.verified.length})</TabsTrigger>
          <TabsTrigger value="bank" className="rounded-sm text-xs" data-testid="ppc-tab-bank">Bank Files & Mark Paid ({byStage.bank.length})</TabsTrigger>
          <TabsTrigger value="paid" className="rounded-sm text-xs" data-testid="ppc-tab-paid">Paid History ({byStage.paid.length})</TabsTrigger>
          <TabsTrigger value="rejected" className="rounded-sm text-xs" data-testid="ppc-tab-rejected">Rejected ({byStage.rejected.length})</TabsTrigger>
          <TabsTrigger value="report" className="rounded-sm text-xs" data-testid="ppc-tab-report">Today's Payment Report</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="mt-3">
          <ExportButtons stage="pending" />
          <QueueTable testid="ppc-pending-table" emptyText="No payments awaiting verification"
            cols={["Request No", "Type", "Project", "Paid To", "Approved On", "Est. Value", "Stage", "Docs", "Action"]}
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
          <div className="flex justify-between items-end gap-2 flex-wrap">
            <label className="flex items-center gap-2 text-xs cursor-pointer border rounded-sm bg-white px-3 h-9"
              data-testid="ppc-select-all-label">
              <Checkbox checked={allVerifiedSelected} onCheckedChange={toggleSelectAll} data-testid="ppc-select-all" />
              Select All ({selectedCount}/{byStage.verified.length} selected)
              {selectedCount > 0 && <span className="font-semibold ml-1" data-testid="ppc-selected-total">· {inr(selectedTotal)}</span>}
            </label>
            <div className="flex items-end gap-2 flex-wrap">
              {selectedCount > 0 && (
                <Button size="sm" variant="ghost" className="rounded-sm h-9 text-xs" onClick={() => setSelected({})}
                  data-testid="ppc-clear-selection">Clear selection</Button>
              )}
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Debit A/c No (repeated on all rows)</Label>
                <Input value={debitAcNo} onChange={(e) => setDebitAcNo(e.target.value)}
                  className="rounded-sm mt-1 h-9 w-52 font-mono" data-testid="ppc-debit-ac-no" />
              </div>
              {canWrite && <Button size="sm" className="rounded-sm h-9" onClick={generateBankFile} disabled={busy}
                data-testid="ppc-generate-bank-file">
                <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Generate Bank File ({selectedCount})
              </Button>}
            </div>
          </div>
          <p className="text-[11px] text-slate-500 text-right">CMS bank-upload format · Pay Mod "N" (blank for ICICI beneficiaries) · Date auto-stamped</p>
          <QueueTable testid="ppc-verified-table" emptyText="No verified payments waiting for a bank file"
            cols={[<Checkbox key="sa" checked={allVerifiedSelected} onCheckedChange={toggleSelectAll}
              data-testid="ppc-select-all-header" />,
              "Request No", "Type", "Project", "Paid To", "Approved On", "Verified Amt", "TDS", "Advance Adj.", "Net Payable", "Verified At", "Docs"]}
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
                  <TableCell className="text-xs whitespace-nowrap">
                    <div>{fmtDT(v.verified_at)}</div>
                    <div className="text-[10px] text-slate-500">{v.verified_by}</div>
                  </TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                </TableRow>
              );
            }} />
        </TabsContent>

        <TabsContent value="bank" className="mt-3 space-y-4">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <ExportButtons stage="bank" />
            {canWrite && <BulkUtrDialog onDone={load} />}
          </div>
          <QueueTable testid="ppc-bank-table" emptyText="No payments in bank files awaiting UTR"
            cols={["Request No", "Type", "Project", "Paid To", "Approved On", "Net Payable", "Bank File", "Docs", "Action"]}
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
                    {canWrite && <div className="flex items-center gap-1.5">
                      <Button size="sm" className="rounded-sm h-7 bg-emerald-600 hover:bg-emerald-700"
                        onClick={() => setPayFor(r)} data-testid={`ppc-mark-paid-btn-${r.request_no}`}>
                        <Banknote className="h-3.5 w-3.5 mr-1" /> Mark Paid</Button>
                      <Button size="sm" variant="outline" className="rounded-sm h-7 border-red-300 text-red-700 hover:bg-red-50"
                        onClick={() => { setRejectReason(""); setRejectFor(r); }}
                        data-testid={`ppc-reject-payment-btn-${r.request_no}`}>
                        <XCircle className="h-3.5 w-3.5 mr-1" /> Reject Payment</Button>
                    </div>}
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
                  <TableCell className="text-xs whitespace-nowrap">{fmtDT(f.created_at)}</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" className="rounded-sm h-7" onClick={() => downloadBankFile(f)}
                      data-testid={`ppc-download-${f.file_no}`}><Download className="h-3.5 w-3.5" /></Button>
                  </TableCell>
                </TableRow>
              )} />
          </div>
        </TabsContent>

        <TabsContent value="paid" className="mt-3">
          <ExportButtons stage="paid" />
          <QueueTable testid="ppc-paid-table" emptyText="No payments completed yet"
            cols={["Request No", "Type", "Project", "Paid To", "Approved On", "Paid Amt", "UTR", "Paid Date", "Voucher", "Advice", "Docs"]}
            rows={byStage.paid}
            renderActions={(r) => {
              const v = r.verification || {};
              const adv = v.advice_status;
              return (
                <TableRow key={r.id} data-testid={`ppc-paid-row-${r.request_no}`}>
                  {baseCells(r)}
                  <TableCell className="text-xs font-semibold whitespace-nowrap">{inr(v.net_payable ?? v.verified_amount)}</TableCell>
                  <TableCell className="text-xs font-mono">{v.utr_no}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{v.paid_date}</TableCell>
                  <TableCell className="text-xs font-mono">{v.voucher_number || "—"}</TableCell>
                  <TableCell>
                    {(adv === "sent" || adv === "queued")
                      ? <Badge className="rounded-sm bg-emerald-100 text-emerald-900 border-emerald-300" title={v.advice_to}>Emailed</Badge>
                      : adv === "no_email"
                        ? <Badge variant="outline" className="rounded-sm text-slate-500">No Email</Badge>
                        : adv ? <Badge variant="outline" className="rounded-sm border-amber-300 text-amber-900">{adv}</Badge> : <span className="text-xs text-slate-400">—</span>}
                  </TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                </TableRow>
              );
            }} />
        </TabsContent>

        <TabsContent value="rejected" className="mt-3">
          <QueueTable testid="ppc-rejected-table" emptyText="No rejected payments"
            cols={["Request No", "Type", "Project", "Paid To", "Approved On", "Amount", "Rejected At", "Rejection Reason", "Docs", "Action"]}
            rows={byStage.rejected}
            renderActions={(r) => {
              const v = r.verification || {};
              return (
                <TableRow key={r.id} data-testid={`ppc-rejected-row-${r.request_no}`}>
                  {baseCells(r)}
                  <TableCell className="text-xs whitespace-nowrap">{inr(v.net_payable ?? v.verified_amount ?? r.est_value)}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    <div>{fmtDT(v.rejected_at || v.verified_at)}</div>
                    <div className="text-[10px] text-slate-500">{v.rejected_by || v.verified_by}</div>
                    {v.rejected_from_stage && <div className="text-[10px] text-slate-400">from {String(v.rejected_from_stage).replace("_", " ")}</div>}
                  </TableCell>
                  <TableCell className="text-xs max-w-[280px]">
                    <span className="text-red-700">{v.rejection_reason || v.remarks || "—"}</span>
                  </TableCell>
                  <TableCell>{attachBtn(r)}</TableCell>
                  <TableCell>
                    {canWrite && <Button size="sm" variant="outline" className="rounded-sm h-7"
                      onClick={() => openVerify(r)} data-testid={`ppc-reverify-btn-${r.request_no}`}>Re-verify</Button>}
                  </TableCell>
                </TableRow>
              );
            }} />
        </TabsContent>


        <TabsContent value="report" className="mt-3 space-y-3">
          <div className="border rounded-sm bg-white p-3 flex items-end gap-3 flex-wrap" data-testid="ppc-report-filters">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Payment / Verification Date</Label>
              <Input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)}
                className="rounded-sm mt-1 h-9 w-44" data-testid="ppc-report-date" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">To (optional — date range)</Label>
              <Input type="date" value={reportTo} onChange={(e) => setReportTo(e.target.value)}
                className="rounded-sm mt-1 h-9 w-44" data-testid="ppc-report-date-to" />
            </div>
            <Button size="sm" className="rounded-sm h-9" onClick={() => loadReport()} disabled={reportLoading}
              data-testid="ppc-report-load">
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${reportLoading ? "animate-spin" : ""}`} /> Show Report
            </Button>
            <Button size="sm" variant="outline" className="rounded-sm h-9" onClick={() => { setReportDate(new Date().toISOString().slice(0, 10)); setReportTo(""); loadReport(new Date().toISOString().slice(0, 10), ""); }}
              data-testid="ppc-report-today">Today</Button>
            <div className="ml-auto flex items-end gap-2">
              <Button size="sm" variant="outline" className="rounded-sm h-9 text-xs" onClick={() => downloadReport("xlsx")}
                data-testid="ppc-report-xlsx"><FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Excel</Button>
              <Button size="sm" variant="outline" className="rounded-sm h-9 text-xs" onClick={() => downloadReport("pdf")}
                data-testid="ppc-report-pdf"><Download className="h-3.5 w-3.5 mr-1" /> PDF</Button>
            </div>
          </div>

          <div className="border rounded-sm bg-white">
            <div className="px-3 py-2 border-b bg-slate-50 flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="text-sm font-semibold" data-testid="ppc-report-title">Payment Verification Report</div>
                <div className="text-[11px] text-slate-500" data-testid="ppc-report-label">
                  {report.label || "Pick a date and press Show Report"} · {report.rows.length} payment(s)
                </div>
              </div>
              <div className="text-xs text-right">
                <div>Verified: <span className="font-semibold">{inr(report.totals?.verified_amount)}</span></div>
                <div className="text-[11px] text-slate-500">TDS {inr(report.totals?.tds_amount)} · Net <span className="font-semibold" data-testid="ppc-report-net-total">{inr(report.totals?.net_amount)}</span></div>
              </div>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {["S. No.", "Req No.", "Beneficiary Name", "Bank A/c · IFSC", "Payment Purpose", "Project",
                      "Verified Amt", "TDS", "Net Amt", "Verification Date", "Verified By", "Remarks"].map((h, i) => (
                        <TableHead key={i} className="text-[11px] uppercase tracking-wider whitespace-nowrap">{h}</TableHead>
                      ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.rows.length === 0 && (
                    <TableRow><TableCell colSpan={12} className="text-center text-sm text-slate-500 py-8">
                      No payments verified for this date
                    </TableCell></TableRow>
                  )}
                  {report.rows.map((r) => (
                    <TableRow key={r.request_id} data-testid={`ppc-report-row-${r.request_no}`}>
                      <TableCell className="text-xs">{r.s_no}</TableCell>
                      <TableCell className="text-xs font-mono whitespace-nowrap">{r.request_no}</TableCell>
                      <TableCell className="text-xs max-w-[200px]">{r.beneficiary_name || "—"}</TableCell>
                      <TableCell className="text-[11px] whitespace-pre-line font-mono">{r.bank_details || "—"}</TableCell>
                      <TableCell className="text-xs max-w-[220px]">
                        <div>{r.purpose}</div>
                        {r.description && <div className="text-[10px] text-slate-500 truncate" title={r.description}>{r.description}</div>}
                      </TableCell>
                      <TableCell className="text-[11px] max-w-[160px] truncate" title={r.project}>{r.project || "—"}</TableCell>
                      <TableCell className="text-xs text-right whitespace-nowrap">{inr(r.verified_amount)}</TableCell>
                      <TableCell className="text-xs text-right whitespace-nowrap">{r.tds_amount ? inr(r.tds_amount) : "—"}</TableCell>
                      <TableCell className="text-xs text-right font-semibold whitespace-nowrap">{inr(r.net_amount)}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{r.verified_on}</TableCell>
                      <TableCell className="text-xs">{r.verified_by}</TableCell>
                      <TableCell>
                        <Input defaultValue={r.remarks} placeholder="Add remark…" disabled={!canWrite}
                          className="rounded-sm h-8 text-xs w-44"
                          onBlur={(e) => e.target.value !== (r.remarks || "") && saveReportRemark(r, e.target.value)}
                          data-testid={`ppc-report-remark-${r.request_no}`} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── Verify dialog ── */}
      <Dialog open={!!verifyFor} onOpenChange={(o) => !o && setVerifyFor(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm">
          <DialogHeader>
            <DialogTitle className="text-base">Verify Payment — {verifyFor?.request_no}</DialogTitle>
            <DialogDescription className="text-xs">
              {verifyFor?.request_type_label} · {verifyFor?.project_code} — {verifyFor?.project_name}
              {verifyFor?.project_manager ? ` · PM: ${verifyFor.project_manager}` : ""} · Requested {inr(verifyFor?.est_value)}
              {verifyFor?.employee_name ? ` · Employee: ${verifyFor.employee_code || ""} ${verifyFor.employee_name}` : ""}
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
              {verifyFor?.vendor_master && (() => {
                const vb = verifyFor.vendor_master.bank;
                const complete = !!(vb?.account_no && vb?.ifsc);
                return (
                <div className="col-span-2 border rounded-sm p-2 bg-slate-50" data-testid="ppc-v-vendor-source">
                  {complete
                    ? <p className="text-[10px] text-emerald-700">
                        Bank details auto-fetched from the Vendor Master — {verifyFor.vendor_master.name}
                        {verifyFor.vendor_master.code ? ` (${verifyFor.vendor_master.code})` : ""}. Edit above if the bank has changed.
                      </p>
                    : <p className="text-[10px] text-amber-700">
                        {vb ? `Vendor Master has incomplete bank details for ${verifyFor.vendor_master.name}${vb.ifsc ? "" : " (IFSC missing)"} — complete them below and they will auto-fill next time.`
                            : `No bank account on the Vendor Master for ${verifyFor.vendor_master.name} — enter it once below and it will auto-fill next time.`}
                      </p>}
                  <label className="flex items-center gap-2 text-xs mt-1 cursor-pointer">
                    <input type="checkbox" checked={saveVendorBank} onChange={(e) => setSaveVendorBank(e.target.checked)}
                      data-testid="ppc-v-save-vendor-bank" />
                    Save/update these bank details on the Vendor Master (auto-fills future payments)
                  </label>
                </div>
                );
              })()}
              {(verifyFor?.employee_record_id || verifyFor?.employee_id || verifyFor?.employee_code) && (
                <div className="col-span-2 border rounded-sm p-2 bg-slate-50" data-testid="ppc-v-bank-source">
                  {verifyFor?.employee_bank
                    ? <p className="text-[10px] text-emerald-700">Bank details auto-fetched from the Employee/Worker Master ({verifyFor.employee_code || verifyFor.employee_name}). Edit above if the bank has changed.</p>
                    : <p className="text-[10px] text-amber-700">No bank details on the Employee/Worker Master for {verifyFor?.employee_code || verifyFor?.employee_name} — enter them above.</p>}
                  <label className="flex items-center gap-2 text-xs mt-1 cursor-pointer">
                    <input type="checkbox" checked={saveBank} onChange={(e) => setSaveBank(e.target.checked)} data-testid="ppc-v-save-bank" />
                    Save/update these bank details on the Employee Master (auto-fills future payments)
                  </label>
                </div>
              )}
              <div className="col-span-2">
                <Label className="text-[10px] uppercase tracking-wider">Vendor Email (payment advice sent here on payment)</Label>
                <Input type="email" value={vform.vendor_email} onChange={(e) => setVform({ ...vform, vendor_email: e.target.value })}
                  placeholder="vendor@company.com" className="rounded-sm mt-1" data-testid="ppc-v-email" />
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
              {payFor?.verification?.vendor_email ? ` Payment advice will be emailed to ${payFor.verification.vendor_email}.` : ""}
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

      {/* ── Reject Payment dialog ── */}
      <Dialog open={!!rejectFor} onOpenChange={(o) => !o && setRejectFor(null)}>
        <DialogContent className="max-w-sm rounded-sm" data-testid="ppc-reject-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Reject Payment — {rejectFor?.request_no}</DialogTitle>
            <DialogDescription className="text-xs">
              {rejectFor?.verification?.vendor_name} · {inr(rejectFor?.verification?.net_payable ?? rejectFor?.verification?.verified_amount)}.
              The payment moves to the Rejected stage (no Journal Entry is posted) and can be re-verified later.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Rejection Reason *</Label>
            <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3}
              placeholder="Why is this payment being rejected? (mandatory)"
              className="rounded-sm mt-1" data-testid="ppc-reject-reason" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRejectFor(null)}>Cancel</Button>
            <Button className="rounded-sm bg-red-600 hover:bg-red-700" disabled={busy || rejectReason.trim().length < 3}
              onClick={submitReject} data-testid="ppc-reject-submit">Confirm Rejection</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
        parentType={attachFor?.source === "vendor_bill" ? "vendor_bills" : "project_requests"}
        parentId={attachFor?.source === "vendor_bill" ? attachFor?.source_id : attachFor?.id}
        recordTitle={`Documents — ${attachFor?.request_no || ""}`} />
    </div>
  );
}
