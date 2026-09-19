/**
 * Accounts Module · Phase 1 Sub-Views
 * ====================================
 * Imported by /app/frontend/src/pages/Accounts.jsx (shell with left sidebar).
 *
 * Exports one component per submenu item:
 *   Dashboard, CoA, Ledger, Vouchers (parametrized), JournalEntry, OpeningBalance,
 *   TrialBalance, GeneralLedger, DayBook, ApprovalInbox, AuditTrail, Settings
 *
 * All endpoints live under /api/accounts/* — see accounts_router.py.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Plus, RefreshCcw, Trash2, AlertCircle, FileSpreadsheet, CheckCircle2, RotateCcw,
} from "lucide-react";

export const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const TYPE_COLOR = {
  asset:     "bg-blue-50 text-blue-800 border-blue-300",
  liability: "bg-rose-50 text-rose-800 border-rose-300",
  equity:    "bg-violet-50 text-violet-800 border-violet-300",
  revenue:   "bg-emerald-50 text-emerald-800 border-emerald-300",
  expense:   "bg-amber-50 text-amber-800 border-amber-300",
};

const VOUCHER_LABELS = {
  SV: "Sales Voucher", PUV: "Purchase Voucher", PV: "Payment Voucher", RV: "Receipt Voucher",
  JV: "Journal Voucher", CV: "Contra Voucher", DN: "Debit Note", CN: "Credit Note",
  EV: "Expense Voucher", PYV: "Payroll Voucher", ADJ: "Adjustment Voucher", REV: "Reversal Voucher",
};

const STATUS_COLOR = {
  posted: "bg-emerald-50 text-emerald-800 border-emerald-300",
  draft:  "bg-slate-100 text-slate-700 border-slate-300",
  pending_approval: "bg-amber-50 text-amber-800 border-amber-300",
};

function Field({ label, children }) {
  return <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>{children}</div>;
}

/* ═══════════════════════════ Dashboard ═══════════════════════════ */
export function AccountsDashboardView({ onJump }) {
  const [data, setData] = useState(null);

  const load = async () => {
    try {
      const { data: d } = await api.get("/accounts/dashboard");
      setData(d);
    } catch { toast.error("Failed to load dashboard"); }
  };
  useEffect(() => {
    let cancelled = false;
    api.get("/accounts/dashboard").then(r => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) toast.error("Failed to load dashboard"); });
    return () => { cancelled = true; };
  }, []);

  if (!data) return <Card><CardContent className="py-12 text-center text-sm text-slate-400">Loading control-centre…</CardContent></Card>;

  const cards = data.cards || {};
  const groups = [
    { title: "Receivables", color: "emerald", items: [
      ["total_receivables", "Total Receivables"],
      ["retention_receivable", "Retention Receivable"],
      ["employee_advances", "Employee Advances"],
      ["vendor_advances", "Vendor Advances"],
    ]},
    { title: "Payables", color: "rose", items: [
      ["total_payables", "Total Payables"],
      ["vendor_payable", "Vendor Payable"],
      ["retention_payable", "Retention Payable"],
      ["client_advances", "Client Advances"],
    ]},
    { title: "Cash & Bank", color: "blue", items: [
      ["bank_balance", "Bank Balance"],
      ["cash_balance", "Cash on Hand"],
      ["petty_cash", "Petty Cash"],
      ["net_cash_flow", "Net Cash Flow (MTD)"],
    ]},
    { title: "Statutory & Payroll", color: "violet", items: [
      ["gst_payable", "GST Payable"],
      ["tds_payable", "TDS Payable"],
      ["salary_payable", "Salary Payable"],
      ["labour_payable", "Labour Payable"],
    ]},
    { title: "MTD P&L", color: "amber", items: [
      ["monthly_income", "Monthly Income"],
      ["monthly_expenses", "Monthly Expenses"],
    ]},
    { title: "Workflow Alerts", color: "slate", items: [
      ["pending_vouchers", "Pending Vouchers"],
      ["unposted_vouchers", "Unposted Drafts"],
      ["missing_attachment_alerts", "Missing Attachments"],
    ]},
  ];

  return (
    <div className="space-y-6" data-testid="acc-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">As of</div>
          <div className="text-sm font-mono">{data.as_of?.slice(0, 19)?.replace("T", " ") || "—"}</div>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="acc-dash-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
        </Button>
      </div>

      {groups.map(g => (
        <div key={g.title}>
          <div className="text-xs uppercase tracking-wider text-slate-600 mb-2 font-semibold">{g.title}</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {g.items.map(([key, label]) => {
              const v = cards[key];
              const isCount = ["pending_vouchers", "unposted_vouchers", "missing_attachment_alerts"].includes(key);
              return (
                <button
                  key={key}
                  onClick={() => onJump?.(key)}
                  data-testid={`acc-card-${key}`}
                  className={`text-left p-4 rounded-md border-2 bg-white hover:bg-${g.color}-50 hover:border-${g.color}-300 transition`}
                >
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
                  <div className={`text-lg font-bold tabular-nums mt-1 text-${g.color}-700`}>
                    {isCount ? (v || 0) : fmt(v)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Recent Transactions</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-2 py-1">Date</th><th className="text-left px-2 py-1">Voucher #</th><th className="text-left px-2 py-1">Narration</th><th className="text-left px-2 py-1">Type</th><th className="text-right px-2 py-1">Amount</th></tr>
            </thead>
            <tbody>
              {(data.recent_transactions || []).map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono text-xs">{r.date}</td>
                  <td className="px-2 py-1 font-mono text-xs">{r.voucher_number || r.je_number}</td>
                  <td className="px-2 py-1">{r.narration}</td>
                  <td className="px-2 py-1 text-xs"><span className="inline-block px-1.5 py-0.5 rounded border text-[10px] bg-slate-50">{r.voucher_type || "JV"}</span></td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.total_debit || r.amount)}</td>
                </tr>
              ))}
              {!data.recent_transactions?.length && <tr><td colSpan={5} className="text-center py-4 text-slate-400 text-xs">No recent transactions.</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

/* ═══════════════════════════ Chart of Accounts ═══════════════════════════ */
export function CoAView() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", type: "asset", subtype: "" });

  const load = () => api.get("/accounts/chart-of-accounts").then(r => setRows(r.data || []));
  useEffect(() => { load(); }, []);

  const filtered = rows.filter(r =>
    (!filter || `${r.code} ${r.name}`.toLowerCase().includes(filter.toLowerCase())) &&
    (!typeFilter || r.type === typeFilter)
  );

  const reseed = async () => {
    if (!window.confirm("Seed missing default accounts (idempotent)?")) return;
    try {
      const { data } = await api.post("/accounts/chart-of-accounts/seed");
      toast.success(`${data.inserted} account(s) added (total: ${data.total})`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Seed failed"); }
  };

  const create = async () => {
    if (!form.code || !form.name) { toast.error("Code + Name required"); return; }
    try {
      await api.post("/accounts/chart-of-accounts", form);
      toast.success("Account added");
      setAddOpen(false); setForm({ code: "", name: "", type: "asset", subtype: "" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const disable = async (r) => {
    if (!window.confirm(`Disable ${r.code} – ${r.name}? Historical JEs keep referencing it.`)) return;
    await api.delete(`/accounts/chart-of-accounts/${r.id}`);
    toast.success("Disabled"); load();
  };

  // Group by type
  const grouped = useMemo(() => {
    const g = { asset: [], liability: [], equity: [], revenue: [], expense: [] };
    filtered.forEach(r => g[r.type]?.push(r));
    return g;
  }, [filtered]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Chart of Accounts <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <Input placeholder="Search code/name…" value={filter} onChange={e => setFilter(e.target.value)} className="h-8 w-56" data-testid="acc-coa-search" />
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
            <option value="">All types</option>
            <option value="asset">Asset</option><option value="liability">Liability</option>
            <option value="equity">Equity</option><option value="revenue">Revenue</option>
            <option value="expense">Expense</option>
          </select>
          <Button variant="outline" size="sm" onClick={reseed} data-testid="acc-coa-seed"><RefreshCcw className="h-3.5 w-3.5 mr-1" />Seed Defaults</Button>
          <Button size="sm" onClick={() => setAddOpen(true)} data-testid="acc-coa-add"><Plus className="h-3.5 w-3.5 mr-1" />Add</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {Object.entries(grouped).map(([type, items]) => items.length > 0 && (
          <div key={type}>
            <div className={`text-xs uppercase tracking-wider font-semibold mb-1 px-2 py-1 rounded inline-block ${TYPE_COLOR[type]}`}>{type} · {items.length}</div>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                  <tr><th className="text-left px-3 py-2">Code</th><th className="text-left px-3 py-2">Name</th><th className="text-left px-3 py-2">Subtype</th><th className="text-right px-3 py-2">Opening Bal</th><th></th></tr>
                </thead>
                <tbody>
                  {items.map(r => (
                    <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`acc-coa-row-${r.code}`}>
                      <td className="px-3 py-1.5 font-mono">{r.code}</td>
                      <td className="px-3 py-1.5">{r.name}</td>
                      <td className="px-3 py-1.5 text-xs text-slate-500">{r.subtype || "—"}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.opening_balance)}</td>
                      <td className="px-3 py-1.5 text-right"><Button size="sm" variant="ghost" onClick={() => disable(r)}><Trash2 className="h-3 w-3" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        {filtered.length === 0 && <div className="text-center py-6 text-slate-400 text-xs">No accounts match.</div>}
      </CardContent>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Account</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Field label="Code *"><Input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} data-testid="acc-coa-code" /></Field>
            <Field label="Name *"><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="acc-coa-name" /></Field>
            <Field label="Type *">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
                <option value="asset">Asset</option><option value="liability">Liability</option>
                <option value="equity">Equity</option><option value="revenue">Revenue</option>
                <option value="expense">Expense</option>
              </select>
            </Field>
            <Field label="Subtype"><Input value={form.subtype} onChange={e => setForm({ ...form, subtype: e.target.value })} /></Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={create} data-testid="acc-coa-save">Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════════════ Vouchers (unified) ═══════════════════════════ */
/** Renders create + list for a SINGLE voucher type. Used by every voucher submenu. */
export function VoucherView({ voucherType, title }) {
  const { rows, pagination, search, setSearch, reload } = usePagedList("/accounts/vouchers", { voucher_type: voucherType }, {
    viewKey: `accounts_vouchers_${voucherType.toLowerCase()}`, errorLabel: "vouchers", defaultSort: { by: "date", dir: "desc" },
    searchKeys: "voucher_number,je_number,voucher_no,party_name,narration,status",
  });
  const [coa, setCoa] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    narration: "",
    party_name: "",
    lines: [
      { account_code: "", debit: 0, credit: 0 },
      { account_code: "", debit: 0, credit: 0 },
    ],
    status: "posted",
  });

  const load = () => reload();
  useEffect(() => {
    api.get("/accounts/chart-of-accounts").then(r => setCoa(r.data || []));
  }, [voucherType]);

  const totalDr = form.lines.reduce((a, b) => a + Number(b.debit || 0), 0);
  const totalCr = form.lines.reduce((a, b) => a + Number(b.credit || 0), 0);
  const balanced = Math.abs(totalDr - totalCr) < 0.01 && totalDr > 0;

  const submit = async () => {
    if (form.status === "posted" && !balanced) {
      toast.error("DR must equal CR and be > 0 to post");
      return;
    }
    try {
      await api.post("/accounts/vouchers", { ...form, voucher_type: voucherType });
      toast.success(`${title} ${form.status === "posted" ? "posted" : "saved as " + form.status}`);
      setOpen(false);
      setForm({
        date: new Date().toISOString().slice(0, 10), narration: "", party_name: "",
        lines: [{ account_code: "", debit: 0, credit: 0 }, { account_code: "", debit: 0, credit: 0 }],
        status: "posted",
      });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const reverse = async (v) => {
    if (!window.confirm(`Create reversal voucher for ${v.voucher_number}?`)) return;
    try {
      await api.post(`/accounts/vouchers/${v.id}/reverse`);
      toast.success("Reversal voucher posted");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title} <span className="text-xs text-slate-500 font-normal">({pagination.total})</span></CardTitle>
        <div className="flex gap-2 items-center">
          <Input className="h-8 w-56 rounded-sm" placeholder="Search voucher #, party, narration…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid={`acc-vch-${voucherType.toLowerCase()}-search`} />
          <TableViewsMenu pagination={pagination} testidPrefix={`acc-vch-${voucherType.toLowerCase()}`} />
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setOpen(true)} data-testid={`acc-vch-${voucherType.toLowerCase()}-add`}>
            <Plus className="h-3.5 w-3.5 mr-1" />New {title}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Voucher #</th><th className="text-left px-3 py-2">Date</th>
                <th className="text-left px-3 py-2">Party</th><th className="text-left px-3 py-2">Narration</th>
                <th className="text-right px-3 py-2">Amount</th><th className="text-center px-3 py-2">Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`acc-vch-row-${r.voucher_number || r.je_number}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.voucher_number || r.je_number}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.date}</td>
                  <td className="px-3 py-1.5 text-xs">{r.party_name || "—"}</td>
                  <td className="px-3 py-1.5">{r.narration}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.total_debit || r.amount)}</td>
                  <td className="px-3 py-1.5 text-center">
                    <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] ${STATUS_COLOR[r.status] || "bg-slate-100"}`}>{r.status || "posted"}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {r.status === "posted" && !r.reversed_by && (
                      <Button size="sm" variant="ghost" onClick={() => reverse(r)} title="Reverse" data-testid={`acc-vch-reverse-${r.voucher_number}`}>
                        <RotateCcw className="h-3 w-3" />
                      </Button>
                    )}
                    {r.reversed_by && <span className="text-[10px] text-slate-500">↩ {r.reversed_by}</span>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400 text-xs">No vouchers yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pt-2"><TablePager pagination={pagination} testidPrefix={`acc-vch-${voucherType.toLowerCase()}`} /></div>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>New {title}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Date *"><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></Field>
            <Field label="Party Name"><Input value={form.party_name} onChange={e => setForm({ ...form, party_name: e.target.value })} placeholder="Client / Vendor / Employee" /></Field>
            <Field label="Status">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
                <option value="posted">Post immediately</option>
                <option value="draft">Save as draft</option>
                <option value="pending_approval">Send for approval</option>
              </select>
            </Field>
          </div>
          <Field label="Narration *"><Input value={form.narration} onChange={e => setForm({ ...form, narration: e.target.value })} data-testid={`acc-vch-${voucherType.toLowerCase()}-narration`} /></Field>

          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs">
                <tr><th className="text-left px-2 py-1">Account</th><th className="text-right px-2 py-1">Debit</th><th className="text-right px-2 py-1">Credit</th><th></th></tr>
              </thead>
              <tbody>
                {form.lines.map((ln, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-2 py-1">
                      <select
                        className="h-8 w-full rounded-sm border bg-background px-1 text-xs"
                        value={ln.account_code}
                        onChange={e => { const lines = [...form.lines]; lines[i].account_code = e.target.value; setForm({ ...form, lines }); }}
                        data-testid={`acc-vch-line-${i}-account`}
                      >
                        <option value="">— pick account —</option>
                        {coa.map(c => <option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-1"><Input type="number" className="h-8 text-right" value={ln.debit} onChange={e => { const lines = [...form.lines]; lines[i].debit = e.target.value; setForm({ ...form, lines }); }} /></td>
                    <td className="px-2 py-1"><Input type="number" className="h-8 text-right" value={ln.credit} onChange={e => { const lines = [...form.lines]; lines[i].credit = e.target.value; setForm({ ...form, lines }); }} /></td>
                    <td><Button size="sm" variant="ghost" onClick={() => setForm({ ...form, lines: form.lines.filter((_, x) => x !== i) })}><Trash2 className="h-3 w-3" /></Button></td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-slate-50 text-xs">
                <tr>
                  <td className="px-2 py-1.5 font-semibold">Total</td>
                  <td className="px-2 py-1.5 text-right font-mono">{fmt(totalDr)}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{fmt(totalCr)}</td><td></td>
                </tr>
              </tfoot>
            </table>
          </div>
          <Button variant="outline" size="sm" onClick={() => setForm({ ...form, lines: [...form.lines, { account_code: "", debit: 0, credit: 0 }] })}>+ Line</Button>
          {form.status === "posted" && !balanced && totalDr + totalCr > 0 && (
            <div className="text-xs text-destructive flex items-center gap-1"><AlertCircle className="h-3 w-3" />DR ≠ CR · diff {fmt(Math.abs(totalDr - totalCr))}</div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              disabled={form.status === "posted" && !balanced}
              onClick={submit}
              data-testid={`acc-vch-${voucherType.toLowerCase()}-save`}
            >
              {form.status === "posted" ? "Post Voucher" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════════════════════════ Opening Balance ═══════════════════════════ */
export function OpeningBalanceView() {
  const [coa, setCoa] = useState([]);
  const [date, setDate] = useState("2026-04-01");
  const [entries, setEntries] = useState([
    { account_code: "", debit: 0, credit: 0 },
    { account_code: "", debit: 0, credit: 0 },
  ]);

  useEffect(() => {
    api.get("/accounts/chart-of-accounts").then(r => setCoa(r.data || []));
  }, []);

  const totalDr = entries.reduce((a, b) => a + Number(b.debit || 0), 0);
  const totalCr = entries.reduce((a, b) => a + Number(b.credit || 0), 0);
  const balanced = Math.abs(totalDr - totalCr) < 0.01 && totalDr > 0;

  const submit = async () => {
    if (!balanced) { toast.error("DR must equal CR and be > 0"); return; }
    try {
      await api.post("/accounts/opening-balance", {
        entries: entries.filter(e => e.account_code),
        date,
        narration: "Opening balance as on " + date,
      });
      toast.success("Opening balance posted");
      setEntries([{ account_code: "", debit: 0, credit: 0 }, { account_code: "", debit: 0, credit: 0 }]);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Opening Balance Entry</CardTitle>
        <p className="text-xs text-slate-500 mt-1">
          Set opening balances at the start of a financial period. Creates a balanced JE and stamps the
          opening_balance field on each touched Chart-of-Accounts row.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <Field label="As of date"><Input type="date" value={date} onChange={e => setDate(e.target.value)} data-testid="acc-ob-date" /></Field>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-2 py-1">Account</th><th className="text-right px-2 py-1">Debit</th><th className="text-right px-2 py-1">Credit</th><th></th></tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className="border-t">
                  <td className="px-2 py-1">
                    <select
                      className="h-8 w-full rounded-sm border bg-background px-1 text-xs"
                      value={e.account_code}
                      onChange={ev => { const ents = [...entries]; ents[i].account_code = ev.target.value; setEntries(ents); }}
                      data-testid={`acc-ob-line-${i}-account`}
                    >
                      <option value="">— pick account —</option>
                      {coa.map(c => <option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-1"><Input type="number" className="h-8 text-right" value={e.debit} onChange={ev => { const ents = [...entries]; ents[i].debit = ev.target.value; setEntries(ents); }} /></td>
                  <td className="px-2 py-1"><Input type="number" className="h-8 text-right" value={e.credit} onChange={ev => { const ents = [...entries]; ents[i].credit = ev.target.value; setEntries(ents); }} /></td>
                  <td><Button size="sm" variant="ghost" onClick={() => setEntries(entries.filter((_, x) => x !== i))}><Trash2 className="h-3 w-3" /></Button></td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-50 text-xs">
              <tr>
                <td className="px-2 py-1.5 font-semibold">Total</td>
                <td className="px-2 py-1.5 text-right font-mono">{fmt(totalDr)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{fmt(totalCr)}</td><td></td>
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setEntries([...entries, { account_code: "", debit: 0, credit: 0 }])}>+ Line</Button>
          <Button disabled={!balanced} onClick={submit} data-testid="acc-ob-save">Post Opening Balance</Button>
        </div>
        {!balanced && totalDr + totalCr > 0 && (
          <div className="text-xs text-destructive flex items-center gap-1"><AlertCircle className="h-3 w-3" />DR ≠ CR · diff {fmt(Math.abs(totalDr - totalCr))}</div>
        )}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Trial Balance ═══════════════════════════ */
export function TrialBalanceView() {
  const [data, setData] = useState({ rows: [], totals: { debit: 0, credit: 0, diff: 0 } });
  const [f, setF] = useState({ start: "", end: "" });

  const run = () => {
    const params = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    api.get(`/accounts/reports/trial-balance?${params}`).then(r => setData(r.data));
  };
  useEffect(() => { run(); /* eslint-disable-next-line */ }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Trial Balance</CardTitle>
        <div className="flex gap-2">
          <Input type="date" className="h-8 w-36" value={f.start} onChange={e => setF({ ...f, start: e.target.value })} />
          <Input type="date" className="h-8 w-36" value={f.end} onChange={e => setF({ ...f, end: e.target.value })} />
          <Button size="sm" variant="outline" onClick={run}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
          <Button size="sm" variant="outline" onClick={() => window.print()}><FileSpreadsheet className="h-3.5 w-3.5 mr-1" />Print</Button>
        </div>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr><th className="text-left px-3 py-2">Code</th><th className="text-left px-3 py-2">Account</th><th className="text-left px-3 py-2">Type</th><th className="text-right px-3 py-2">Debit</th><th className="text-right px-3 py-2">Credit</th><th className="text-right px-3 py-2">Balance</th></tr>
          </thead>
          <tbody>
            {data.rows.map(r => (
              <tr key={r.code} className="border-t hover:bg-slate-50" data-testid={`acc-tb-row-${r.code}`}>
                <td className="px-3 py-1.5 font-mono text-xs">{r.code}</td>
                <td className="px-3 py-1.5">{r.name}</td>
                <td className="px-3 py-1.5"><span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] ${TYPE_COLOR[r.type] || ""}`}>{r.type}</span></td>
                <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.debit_total)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.credit_total)}</td>
                <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${r.balance < 0 ? "text-rose-700" : ""}`}>{fmt(Math.abs(r.balance))} {r.balance < 0 ? "Cr" : "Dr"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-slate-100 font-semibold">
            <tr>
              <td colSpan={3} className="px-3 py-2 text-right">Totals</td>
              <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals.debit)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{fmt(data.totals.credit)}</td>
              <td className={`px-3 py-2 text-right tabular-nums ${Math.abs(data.totals.diff) > 0.01 ? "text-rose-700" : "text-emerald-700"}`}>diff {fmt(data.totals.diff)}</td>
            </tr>
          </tfoot>
        </table>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ General Ledger ═══════════════════════════ */
export function GeneralLedgerView() {
  const [coa, setCoa] = useState([]);
  const [code, setCode] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/accounts/chart-of-accounts").then(r => setCoa(r.data || [])); }, []);

  const run = () => {
    if (!code) { toast.error("Pick an account first"); return; }
    api.get(`/accounts/reports/general-ledger?account_code=${code}`).then(r => setData(r.data));
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">General Ledger</CardTitle>
        <div className="flex gap-2">
          <select className="h-8 rounded-sm border bg-background px-2 text-sm w-72" value={code} onChange={e => setCode(e.target.value)} data-testid="acc-gl-account">
            <option value="">— pick account —</option>
            {coa.map(c => <option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}
          </select>
          <Button size="sm" onClick={run} data-testid="acc-gl-run"><RefreshCcw className="h-3.5 w-3.5 mr-1" />Run</Button>
        </div>
      </CardHeader>
      <CardContent>
        {!data && <div className="text-center py-8 text-xs text-slate-400">Select an account and click Run.</div>}
        {data && (
          <>
            <div className="mb-2 text-sm">
              <span className="font-semibold">{data.account.code} · {data.account.name}</span>
              <span className="ml-3 text-xs text-slate-500">Opening: {fmt(data.account.opening_balance)} · Closing: {fmt(data.closing_balance)}</span>
            </div>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                  <tr><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">JE #</th><th className="text-left px-3 py-2">Narration</th><th className="text-right px-3 py-2">Debit</th><th className="text-right px-3 py-2">Credit</th><th className="text-right px-3 py-2">Running</th></tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} className="border-t hover:bg-slate-50">
                      <td className="px-3 py-1.5 font-mono text-xs">{r.date}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.je_number}</td>
                      <td className="px-3 py-1.5 text-xs">{r.narration}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.debit)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.credit)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.running)}</td>
                    </tr>
                  ))}
                  {data.rows.length === 0 && <tr><td colSpan={6} className="text-center py-6 text-slate-400 text-xs">No transactions on this account.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Day Book ═══════════════════════════ */
export function DayBookView() {
  const [data, setData] = useState(null);
  const [date, setDate] = useState("");

  const run = () => {
    const url = date ? `/accounts/reports/day-book?date=${date}` : `/accounts/reports/day-book?start=2026-01-01`;
    api.get(url).then(r => setData(r.data));
  };
  useEffect(() => { run(); /* eslint-disable-next-line */ }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Day Book</CardTitle>
        <div className="flex gap-2">
          <Input type="date" className="h-8 w-40" value={date} onChange={e => setDate(e.target.value)} data-testid="acc-db-date" />
          <Button size="sm" onClick={run}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Run</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {(data?.days || []).map(day => (
          <div key={day.date} data-testid={`acc-db-day-${day.date}`}>
            <div className="flex justify-between bg-slate-100 px-3 py-1 rounded font-semibold text-sm">
              <span>{day.date}</span>
              <span className="text-xs">DR {fmt(day.total_debit)} · CR {fmt(day.total_credit)} · {day.entries.length} entries</span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {day.entries.map(e => (
                  <tr key={e.id} className="border-b hover:bg-slate-50">
                    <td className="px-3 py-1 font-mono text-xs w-32">{e.voucher_number || e.je_number}</td>
                    <td className="px-3 py-1 text-xs"><span className="inline-block px-1 rounded border bg-slate-50 text-[10px]">{e.voucher_type || "JV"}</span></td>
                    <td className="px-3 py-1">{e.narration}</td>
                    <td className="px-3 py-1 text-right tabular-nums w-32">{fmt(e.total_debit || e.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {data && !data.days?.length && <div className="text-center py-8 text-xs text-slate-400">No entries.</div>}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Approval Inbox ═══════════════════════════ */
export function ApprovalInboxView() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/accounts/approval-inbox").then(r => setRows(r.data || []));
  useEffect(() => { load(); }, []);

  const approve = async (v) => {
    try {
      await api.post(`/accounts/vouchers/${v.id}/approve`);
      toast.success("Voucher posted"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Approval Inbox <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Voucher #</th><th className="text-left px-3 py-2">Type</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Narration</th><th className="text-right px-3 py-2">Amount</th><th className="text-center px-3 py-2">Status</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`acc-inbox-row-${r.voucher_number || r.je_number}`}>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.voucher_number || r.je_number}</td>
                  <td className="px-3 py-1.5 text-xs">{VOUCHER_LABELS[r.voucher_type] || r.voucher_type || "—"}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.date}</td>
                  <td className="px-3 py-1.5">{r.narration}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.total_debit || r.amount)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] ${STATUS_COLOR[r.status] || ""}`}>{r.status}</span></td>
                  <td className="px-3 py-1.5 text-right">
                    <Button size="sm" onClick={() => approve(r)} data-testid={`acc-inbox-approve-${r.voucher_number}`}>
                      <CheckCircle2 className="h-3 w-3 mr-1" />Approve & Post
                    </Button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-slate-400 text-xs">No vouchers awaiting approval.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Audit Trail ═══════════════════════════ */
export function AuditTrailView() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/accounts/audit-trail?limit=200").then(r => setRows(r.data || []));
  useEffect(() => { load(); }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Audit Trail (Accounts) <span className="text-xs text-slate-500 font-normal">({rows.length})</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">When</th><th className="text-left px-3 py-2">Actor</th><th className="text-left px-3 py-2">Role</th><th className="text-left px-3 py-2">Action</th><th className="text-left px-3 py-2">Resource</th><th className="text-left px-3 py-2">Record</th><th className="text-left px-3 py-2">IP</th></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.ts?.slice(0, 19)?.replace("T", " ")}</td>
                  <td className="px-3 py-1.5 text-xs">{r.actor_name}</td>
                  <td className="px-3 py-1.5 text-xs"><span className="inline-block px-1.5 py-0.5 rounded border text-[10px] bg-slate-50">{r.actor_role}</span></td>
                  <td className="px-3 py-1.5 text-xs">{r.action}</td>
                  <td className="px-3 py-1.5 text-xs">{r.resource}</td>
                  <td className="px-3 py-1.5 text-xs font-mono">{(r.after?.voucher_number) || (r.after?.je_number) || r.record_id?.slice(0, 8) || "—"}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-500">{r.ip || "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-slate-400 text-xs">No audit entries.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Aging (AR / AP) ═══════════════════════════ */
export function AgingView({ kind }) {
  const [data, setData] = useState({ rows: [], buckets: { "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0 }, total_outstanding: 0 });
  const run = () => api.get(`/accounts/reports/${kind}-aging`).then(r => setData(r.data));
  useEffect(() => { run(); /* eslint-disable-next-line */ }, [kind]);

  const label = kind === "ar" ? "Accounts Receivable Aging" : "Accounts Payable Aging";
  const colour = kind === "ar" ? "text-emerald-700" : "text-amber-700";
  const partyKey = kind === "ar" ? "client" : "vendor";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{label}</CardTitle>
        <Button size="sm" variant="outline" onClick={run}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2 mb-4">
          {Object.entries(data.buckets).map(([k, v]) => (
            <div key={k} className="p-3 rounded-md border bg-slate-50" data-testid={`acc-${kind}-bucket-${k}`}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{k} days</div>
              <div className={`text-lg font-bold tabular-nums ${colour}`}>{fmt(v)}</div>
            </div>
          ))}
          <div className="p-3 rounded-md border-2 border-slate-400 bg-white">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Total Outstanding</div>
            <div className="text-lg font-bold tabular-nums">{fmt(data.total_outstanding)}</div>
          </div>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Inv #</th><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">{kind === "ar" ? "Client" : "Vendor"}</th><th className="text-right px-3 py-2">Gross</th><th className="text-right px-3 py-2">Paid</th><th className="text-right px-3 py-2">Outstanding</th><th className="text-center px-3 py-2">Bucket</th></tr>
            </thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.invoice_id} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.invoice_no}</td>
                  <td className="px-3 py-1.5 text-xs">{r.date}</td>
                  <td className="px-3 py-1.5">{r[partyKey]}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.gross)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{fmt(r.paid)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.outstanding)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-2 py-0.5 rounded border text-[10px] ${r.days_overdue > 90 ? "bg-rose-50 text-rose-800 border-rose-300" : r.days_overdue > 60 ? "bg-amber-50 text-amber-800 border-amber-300" : "bg-emerald-50 text-emerald-800 border-emerald-300"}`}>{r.bucket} · {r.days_overdue}d</span></td>
                </tr>
              ))}
              {data.rows.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-xs text-slate-400">Nothing outstanding.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════ Settings (stub) ═══════════════════════════ */
export function SettingsView() {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Accounts Settings</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 border rounded">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Financial Year</div>
            <div className="font-semibold">2026-2027 (Apr-Mar)</div>
          </div>
          <div className="p-3 border rounded">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Base Currency</div>
            <div className="font-semibold">INR (₹)</div>
          </div>
          <div className="p-3 border rounded">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">GSTIN</div>
            <div className="font-semibold">23ITLPL2024XX1Z5</div>
          </div>
          <div className="p-3 border rounded">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Period Lock</div>
            <div className="font-semibold text-emerald-700">Unlocked</div>
          </div>
        </div>
        <p className="text-xs text-slate-500 pt-2">
          Phase-1 read-only — period lock, voucher numbering series prefix overrides, default cost-centres,
          GST templates and approval thresholds will be editable in Phase 2.
        </p>
      </CardContent>
    </Card>
  );
}
