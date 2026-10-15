import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CalendarClock, CalendarPlus, RefreshCw, Truck, Wallet, Ban, PlayCircle } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { inr } from "./shared";

const MONTH_TONE = {
  not_raised: "bg-slate-100 text-slate-700 border-slate-300",
  payment_pending: "bg-amber-50 text-amber-800 border-amber-300",
  paid: "bg-emerald-50 text-emerald-800 border-emerald-300",
  rejected: "bg-red-50 text-red-800 border-red-300",
};
const MONTH_LABEL = { not_raised: "Not raised", payment_pending: "Payment in process", paid: "Paid", rejected: "Rejected" };

const Kpi = ({ label, value, sub, icon: Icon, testid }) => (
  <div className="border rounded-sm bg-white p-3" data-testid={testid}>
    <div className="flex items-start justify-between">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-xl font-semibold mt-0.5">{value}</div>
        {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
      </div>
      <Icon className="h-4 w-4 text-slate-400" />
    </div>
  </div>
);

export default function ServiceRecurring() {
  const [rows, setRows] = useState([]);
  const [cards, setCards] = useState({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [months, setMonths] = useState([]);
  const [payFor, setPayFor] = useState(null);
  const [payForm, setPayForm] = useState({ amount: "", vendor_invoice_no: "", invoice_date: "", remarks: "" });
  const [extendFor, setExtendFor] = useState(null);
  const [extendForm, setExtendForm] = useState({ validity_to: "", remarks: "" });

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [r, d] = await Promise.all([
        api.get("/service-recurring", { params: q ? { q } : {} }),
        api.get("/service-recurring/dashboard"),
      ]);
      setRows(r.data || []);
      setCards(d.data || {});
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (c) => {
    try {
      const r = await api.get(`/service-recurring/${c.id}/months`);
      setDetail(r.data.contract); setMonths(r.data.months || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const openPay = (m) => {
    setPayForm({ amount: String(m.amount || detail?.monthly_amount || ""), vendor_invoice_no: "", invoice_date: "", remarks: "" });
    setPayFor(m);
  };

  const submitPay = async () => {
    setBusy(true);
    try {
      await api.post(`/service-recurring/${detail.id}/months/${payFor.month}/raise`, {
        amount: Number(payForm.amount || 0), vendor_invoice_no: payForm.vendor_invoice_no,
        invoice_date: payForm.invoice_date, remarks: payForm.remarks,
      });
      toast.success(`${payFor.label} payment sent to Accounts for processing`);
      setPayFor(null); await openDetail(detail); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const submitExtend = async () => {
    setBusy(true);
    try {
      await api.post(`/service-recurring/${extendFor.id}/extend`, extendForm);
      toast.success("Service validity extended — monthly payments continue");
      setExtendFor(null); load();
      if (detail?.id === extendFor.id) await openDetail(extendFor);
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const setStatus = async (c, status) => {
    setBusy(true);
    try {
      await api.post(`/service-recurring/${c.id}/status`, { status, remarks: "" });
      toast.success(`Contract ${status}`);
      load(); if (detail?.id === c.id) await openDetail(c);
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const dueNow = useMemo(() => rows.filter((r) => r.due_this_month), [rows]);

  return (
    <div className="space-y-4" data-testid="svc-recurring-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Monthly Service Payments</h1>
          <p className="text-xs text-muted-foreground">
            Fixed monthly services (transport, vehicles) — the Service Request, RFQ and PO are raised <b>once</b> for the project duration.
            Logistics then raises only the monthly payment, which follows the normal Accounts approval process.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="PO, vendor, project…"
            className="rounded-sm h-9 w-56" data-testid="svc-recurring-search" />
          <Button size="sm" variant="outline" className="rounded-sm h-9" onClick={load} disabled={busy}
            data-testid="svc-recurring-refresh">
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${busy ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Active Contracts" value={cards.active ?? 0} icon={Truck} testid="svc-recurring-kpi-active" />
        <Kpi label="Due This Month" value={cards.due_this_month ?? 0} sub={dueNow.length ? "Raise the monthly payment" : "All raised"}
          icon={CalendarClock} testid="svc-recurring-kpi-due" />
        <Kpi label="Monthly Commitment" value={inr(cards.monthly_commitment)} icon={Wallet} testid="svc-recurring-kpi-commitment" />
        <Kpi label="Validity Ending Soon" value={cards.expiring_soon ?? 0} sub="Extend with the project"
          icon={CalendarPlus} testid="svc-recurring-kpi-expiring" />
      </div>

      <div className="border rounded-sm bg-white overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {["PO / SR", "Service", "Vendor", "Project", "Monthly Amount", "Validity", "Months", "PO Value Used", "Status", "Action"]
                .map((h, i) => <TableHead key={i} className="text-[11px] uppercase tracking-wider whitespace-nowrap">{h}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={10} className="text-center text-sm text-slate-500 py-8">
                No monthly service contracts yet — open an approved Service PO and choose “Monthly Recurring”.
              </TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`svc-recurring-row-${r.po_no}`}>
                <TableCell className="text-xs font-mono whitespace-nowrap">
                  <div>{r.po_no}</div><div className="text-[10px] text-slate-500">{r.sr_no}</div>
                </TableCell>
                <TableCell className="text-xs max-w-[200px] truncate" title={r.service_label}>{r.service_label}</TableCell>
                <TableCell className="text-xs">{r.vendor_name}</TableCell>
                <TableCell className="text-[11px]">
                  <div>{r.project_code}</div>
                  <div className="text-slate-500">{r.project_status}</div>
                </TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(r.monthly_amount)}</TableCell>
                <TableCell className="text-[11px] whitespace-nowrap">
                  {r.validity_from} → {r.validity_to}
                  {r.project_end_date && r.project_end_date !== r.validity_to && (
                    <div className="text-amber-700">Project ends {r.project_end_date}</div>
                  )}
                </TableCell>
                <TableCell className="text-[11px] whitespace-nowrap">
                  {r.months_raised}/{r.months_total} raised · {r.paid_count} paid
                  {r.due_this_month && <Badge className="ml-1 bg-amber-100 text-amber-800 border border-amber-300" data-testid={`svc-recurring-due-${r.po_no}`}>Due</Badge>}
                </TableCell>
                <TableCell className="text-[11px] whitespace-nowrap">
                  {inr(r.committed_value)} / {inr(r.po_value)}
                  <div className="text-slate-500">Left {inr(r.remaining_value)}</div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px] capitalize">{r.project_closed ? "project closed" : r.status}</Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="outline" className="rounded-sm h-7 text-xs" onClick={() => openDetail(r)}
                      data-testid={`svc-recurring-open-${r.po_no}`}>Months</Button>
                    <Button size="sm" variant="outline" className="rounded-sm h-7 text-xs"
                      onClick={() => { setExtendForm({ validity_to: r.project_end_date || "", remarks: "" }); setExtendFor(r); }}
                      data-testid={`svc-recurring-extend-${r.po_no}`}>Extend</Button>
                    {r.status === "active"
                      ? <Button size="sm" variant="ghost" className="rounded-sm h-7 text-xs" onClick={() => setStatus(r, "paused")}
                          data-testid={`svc-recurring-pause-${r.po_no}`}><Ban className="h-3 w-3" /></Button>
                      : r.status === "paused" && <Button size="sm" variant="ghost" className="rounded-sm h-7 text-xs" onClick={() => setStatus(r, "active")}
                          data-testid={`svc-recurring-resume-${r.po_no}`}><PlayCircle className="h-3 w-3" /></Button>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Month grid */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-3xl rounded-sm" data-testid="svc-recurring-months-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Monthly payments — {detail?.po_no}</DialogTitle>
            <DialogDescription className="text-xs">
              {detail?.service_label} · {detail?.vendor_name} · {detail?.project_code} · {inr(detail?.monthly_amount)} / month ·
              validity {detail?.validity_from} → {detail?.validity_to}
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[55vh] overflow-y-auto border rounded-sm">
            <Table>
              <TableHeader>
                <TableRow>
                  {["Month", "Amount", "Status", "Invoice No", "Action"].map((h, i) => (
                    <TableHead key={i} className="text-[11px] uppercase tracking-wider">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {months.map((m) => (
                  <TableRow key={m.month} data-testid={`svc-recurring-month-${m.month}`}>
                    <TableCell className="text-xs whitespace-nowrap">{m.label}</TableCell>
                    <TableCell className="text-xs whitespace-nowrap">{inr(m.payment?.gross || m.amount)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-[10px] ${MONTH_TONE[m.status] || ""}`}>
                        {MONTH_LABEL[m.status] || m.status}
                      </Badge>
                      {m.payment?.auto_drafted && <span className="ml-1 text-[10px] text-slate-500">auto</span>}
                    </TableCell>
                    <TableCell className="text-[11px]">{m.payment?.vendor_invoice_no || "—"}</TableCell>
                    <TableCell>
                      {m.can_raise
                        ? <Button size="sm" className="rounded-sm h-7 text-xs" onClick={() => openPay(m)}
                            data-testid={`svc-recurring-raise-${m.month}`}>Raise Payment</Button>
                        : <span className="text-[10px] text-slate-500">{m.blocked_reason}</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </DialogContent>
      </Dialog>

      {/* Raise monthly payment */}
      <Dialog open={!!payFor} onOpenChange={(o) => !o && setPayFor(null)}>
        <DialogContent className="max-w-sm rounded-sm" data-testid="svc-recurring-pay-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Raise payment — {payFor?.label}</DialogTitle>
            <DialogDescription className="text-xs">
              {detail?.vendor_name} · PO {detail?.po_no}. No new Service Request, RFQ, PO or SRN is needed — this goes straight
              to the Accounts payment approval process.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Amount (excl. tax) *</Label>
              <Input type="number" value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })}
                className="rounded-sm mt-1 h-9" data-testid="svc-recurring-pay-amount" />
              <p className="text-[10px] text-slate-500 mt-1">Tax {detail?.tax_pct || 0}% is added from the PO. PO value left: {inr(detail?.remaining_value)}</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Vendor Invoice No</Label>
                <Input value={payForm.vendor_invoice_no} onChange={(e) => setPayForm({ ...payForm, vendor_invoice_no: e.target.value })}
                  className="rounded-sm mt-1 h-9" data-testid="svc-recurring-pay-invoice" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Invoice Date</Label>
                <Input type="date" value={payForm.invoice_date} onChange={(e) => setPayForm({ ...payForm, invoice_date: e.target.value })}
                  className="rounded-sm mt-1 h-9" data-testid="svc-recurring-pay-date" />
              </div>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Remarks / Justification</Label>
              <Textarea rows={2} value={payForm.remarks} onChange={(e) => setPayForm({ ...payForm, remarks: e.target.value })}
                className="rounded-sm mt-1" data-testid="svc-recurring-pay-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setPayFor(null)}>Cancel</Button>
            <Button className="rounded-sm" disabled={busy || !Number(payForm.amount)} onClick={submitPay}
              data-testid="svc-recurring-pay-submit">Send to Accounts</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Extend validity */}
      <Dialog open={!!extendFor} onOpenChange={(o) => !o && setExtendFor(null)}>
        <DialogContent className="max-w-sm rounded-sm" data-testid="svc-recurring-extend-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Extend validity — {extendFor?.po_no}</DialogTitle>
            <DialogDescription className="text-xs">
              Current validity ends {extendFor?.validity_to}. Project target completion is {extendFor?.project_end_date || "not set"}.
              Extend the project in Project Master first if you need to go beyond it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">New validity end date *</Label>
              <Input type="date" value={extendForm.validity_to} onChange={(e) => setExtendForm({ ...extendForm, validity_to: e.target.value })}
                className="rounded-sm mt-1 h-9" data-testid="svc-recurring-extend-date" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
              <Textarea rows={2} value={extendForm.remarks} onChange={(e) => setExtendForm({ ...extendForm, remarks: e.target.value })}
                className="rounded-sm mt-1" data-testid="svc-recurring-extend-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setExtendFor(null)}>Cancel</Button>
            <Button className="rounded-sm" disabled={busy || !extendForm.validity_to} onClick={submitExtend}
              data-testid="svc-recurring-extend-submit">Extend Validity</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
