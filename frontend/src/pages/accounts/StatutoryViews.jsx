/**
 * Statutory Views · Phase 6
 * ==========================
 * Bank Rec · GSTR-1 · GSTR-3B · TDS 26AS · Fixed Assets
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, RefreshCcw, Link2, Play } from "lucide-react";
import { fmt } from "./AccountsViews";
import { ClientSelect } from "@/components/MasterSelect";

function Field({ label, children }) {
  return <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>{children}</div>;
}

/* ═══════ Bank Reconciliation ═══════ */
export function BankRecView() {
  const [data, setData] = useState({ bank_lines: [], je_lines: [], suggestions: [], summary: {} });
  const [account, setAccount] = useState("1100");
  const load = () => api.get(`/statutory/bank-rec/unmatched?bank_account_code=${account}`).then(r => setData(r.data));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [account]);

  const autoMatch = async () => {
    try {
      const r = await api.post(`/statutory/bank-rec/auto-match?bank_account_code=${account}`);
      toast.success(`Auto-matched ${r.data.applied}`); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const matchPair = async (bId, jId) => {
    try { await api.post("/statutory/bank-rec/match", { bank_line_id: bId, je_id: jId }); toast.success("Matched"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Bank Reconciliation</CardTitle>
        <div className="flex gap-2">
          <select className="h-8 rounded-sm border bg-background px-2 text-sm" value={account} onChange={e => setAccount(e.target.value)}>
            <option value="1100">1100 Bank — Operating</option>
            <option value="1101">1101 Bank — Current 2</option>
            <option value="1110">1110 Cash on Hand</option>
          </select>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={autoMatch} data-testid="stat-bank-automatch"><Link2 className="h-3.5 w-3.5 mr-1" />Auto-Match ({data.suggestions?.length || 0})</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-2">
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Unmatched Bank Lines</div><div className="text-lg font-bold">{data.summary?.unmatched_bank || 0}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Unmatched JE Lines</div><div className="text-lg font-bold">{data.summary?.unmatched_je || 0}</div></div>
          <div className="p-3 border rounded bg-emerald-50"><div className="text-[10px] uppercase text-slate-500">Auto-Match Candidates</div><div className="text-lg font-bold text-emerald-700">{data.summary?.auto_match_candidates || 0}</div></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold mb-1">Bank Statement Lines</div>
            <div className="border rounded-md overflow-hidden max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs sticky top-0"><tr><th className="text-left px-2 py-1">Date</th><th className="text-left px-2 py-1">Description</th><th className="text-right px-2 py-1">Amount</th></tr></thead>
                <tbody>
                  {(data.bank_lines || []).map(b => (
                    <tr key={b.id} className="border-t hover:bg-slate-50">
                      <td className="px-2 py-1 font-mono text-xs">{b.date}</td>
                      <td className="px-2 py-1 text-xs">{b.description}</td>
                      <td className={`px-2 py-1 text-right tabular-nums ${b.amount >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmt(b.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold mb-1">Unmatched JE Lines</div>
            <div className="border rounded-md overflow-hidden max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs sticky top-0"><tr><th className="text-left px-2 py-1">Date</th><th className="text-left px-2 py-1">Voucher</th><th className="text-right px-2 py-1">Amount</th></tr></thead>
                <tbody>
                  {(data.je_lines || []).map((j, i) => (
                    <tr key={i} className="border-t hover:bg-slate-50">
                      <td className="px-2 py-1 font-mono text-xs">{j.date}</td>
                      <td className="px-2 py-1 font-mono text-xs">{j.voucher_number}</td>
                      <td className={`px-2 py-1 text-right tabular-nums ${j.amount >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmt(j.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        {(data.suggestions || []).length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold mb-1">Suggested Matches</div>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-2 py-1">Bank Line</th><th className="text-left px-2 py-1">JE</th><th></th></tr></thead>
                <tbody>
                  {data.suggestions.map((s, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1 font-mono text-xs">{s.bank_line_id?.slice(0, 8)}</td>
                      <td className="px-2 py-1 font-mono text-xs">{s.je_id?.slice(0, 8)}</td>
                      <td className="px-2 py-1 text-right"><Button size="sm" variant="outline" onClick={() => matchPair(s.bank_line_id, s.je_id)}><Link2 className="h-3 w-3 mr-1" />Match</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ═══════ GSTR-1 ═══════ */
export function GSTR1View() {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState({ b2b: { rows: [], count: 0 }, b2c: { rows: [], count: 0 }, hsn_summary: [], totals: {} });
  const load = () => api.get(`/statutory/gst/gstr-1?period=${period}`).then(r => setData(r.data));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GSTR-1 · Outward Supplies</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="2026-06" value={period} onChange={e => setPeriod(e.target.value)} className="h-8 w-32" />
          <Button size="sm" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-5 gap-2">
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Taxable</div><div className="text-lg font-bold tabular-nums">{fmt(data.totals?.taxable)}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">CGST</div><div className="text-lg font-bold tabular-nums">{fmt(data.totals?.cgst)}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">SGST</div><div className="text-lg font-bold tabular-nums">{fmt(data.totals?.sgst)}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">IGST</div><div className="text-lg font-bold tabular-nums">{fmt(data.totals?.igst)}</div></div>
          <div className="p-3 border rounded-md border-2 border-blue-400 bg-white"><div className="text-[10px] uppercase text-slate-500">Gross</div><div className="text-lg font-bold tabular-nums text-blue-700">{fmt(data.totals?.gross)}</div></div>
        </div>
        {["b2b", "b2c"].map(t => (
          <div key={t}>
            <div className="text-xs uppercase tracking-wider font-semibold mb-1">{t.toUpperCase()} · {data[t]?.count || 0} invoice(s)</div>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-2 py-1">Invoice #</th><th className="text-left px-2 py-1">Date</th><th className="text-left px-2 py-1">Client</th><th className="text-left px-2 py-1">GSTIN</th><th className="text-right px-2 py-1">Taxable</th><th className="text-right px-2 py-1">CGST</th><th className="text-right px-2 py-1">SGST</th><th className="text-right px-2 py-1">IGST</th><th className="text-right px-2 py-1">Gross</th></tr></thead>
                <tbody>
                  {(data[t]?.rows || []).map(r => (
                    <tr key={r.invoice_no} className="border-t hover:bg-slate-50">
                      <td className="px-2 py-1 font-mono text-xs">{r.invoice_no}</td>
                      <td className="px-2 py-1 font-mono text-xs">{r.invoice_date}</td>
                      <td className="px-2 py-1 text-xs">{r.client_name}</td>
                      <td className="px-2 py-1 font-mono text-xs">{r.client_gstin || "—"}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(r.taxable_value)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(r.cgst)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(r.sgst)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmt(r.igst)}</td>
                      <td className="px-2 py-1 text-right tabular-nums font-semibold">{fmt(r.gross_value)}</td>
                    </tr>
                  ))}
                  {(data[t]?.rows || []).length === 0 && <tr><td colSpan={9} className="text-center py-3 text-xs text-slate-400">No {t.toUpperCase()} invoices.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        <div>
          <div className="text-xs uppercase tracking-wider font-semibold mb-1">HSN / Service Summary</div>
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-2 py-1">HSN / Service</th><th className="text-right px-2 py-1">Qty</th><th className="text-right px-2 py-1">Taxable</th><th className="text-right px-2 py-1">CGST</th><th className="text-right px-2 py-1">SGST</th><th className="text-right px-2 py-1">IGST</th></tr></thead>
              <tbody>
                {(data.hsn_summary || []).map(h => (
                  <tr key={h.hsn_or_service} className="border-t">
                    <td className="px-2 py-1 text-xs">{h.hsn_or_service}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{h.qty}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{fmt(h.taxable)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{fmt(h.cgst)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{fmt(h.sgst)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{fmt(h.igst)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════ GSTR-3B ═══════ */
export function GSTR3BView() {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState({ outward_supplies: {}, input_tax_credit: {}, net_liability: {} });
  const load = () => api.get(`/statutory/gst/gstr-3b?period=${period}`).then(r => setData(r.data));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">GSTR-3B · Monthly Return Summary</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="2026-06" value={period} onChange={e => setPeriod(e.target.value)} className="h-8 w-32" />
          <Button size="sm" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Apply</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-4">
          {[
            { title: "Outward Supplies (Output GST)", color: "emerald", data: data.outward_supplies },
            { title: "Input Tax Credit (Purchase GST)", color: "blue", data: data.input_tax_credit },
            { title: "Net Liability (Output − Input)", color: "rose", data: data.net_liability, isNet: true },
          ].map((b, i) => (
            <div key={i} className="border rounded-md p-3">
              <div className={`text-xs uppercase tracking-wider font-semibold mb-2 text-${b.color}-700`}>{b.title}</div>
              {["taxable", "cgst", "sgst", "igst"].filter(k => k in (b.data || {})).map(k => (
                <div key={k} className="flex justify-between border-b py-1 text-sm">
                  <span className="text-slate-500 uppercase text-xs">{k}</span>
                  <span className={`font-semibold tabular-nums ${(b.data[k] || 0) < 0 ? "text-emerald-700" : ""}`}>{fmt(b.data[k])}</span>
                </div>
              ))}
              {b.isNet && (
                <div className="mt-2 p-2 rounded bg-rose-50 border-2 border-rose-300">
                  <div className="text-[10px] uppercase text-rose-700">Total Payable</div>
                  <div className="text-xl font-bold tabular-nums text-rose-700">{fmt(b.data?.total_payable)}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════ TDS 26AS Match ═══════ */
export function TDS26ASView() {
  const [data, setData] = useState({ matches: [], summary: {} });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [upForm, setUpForm] = useState({ client_name: "", section: "194C", amount_credited: 0, tds_deducted: 0, date_of_credit: new Date().toISOString().slice(0, 10), quarter: "Q1" });

  const load = () => api.get("/statutory/tds/26as/match").then(r => setData(r.data));
  useEffect(() => { load(); }, []);

  const upload = async () => {
    if (!upForm.client_name || upForm.tds_deducted <= 0) { toast.error("Client name + TDS amount required"); return; }
    try {
      await api.post("/statutory/tds/26as/upload", [upForm]);
      toast.success("26AS entry uploaded");
      setUploadOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">TDS 26AS Reconciliation</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setUploadOpen(true)}><Plus className="h-3.5 w-3.5 mr-1" />Upload 26AS Entry</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="p-3 border rounded bg-emerald-50"><div className="text-[10px] uppercase text-slate-500">Matched</div><div className="text-lg font-bold text-emerald-700">{data.summary?.matched || 0}</div></div>
          <div className="p-3 border rounded bg-rose-50"><div className="text-[10px] uppercase text-slate-500">Mismatch</div><div className="text-lg font-bold text-rose-700">{data.summary?.mismatch || 0}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Total In Books</div><div className="text-lg font-bold tabular-nums">{fmt(data.summary?.total_books)}</div></div>
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Total In 26AS</div><div className="text-lg font-bold tabular-nums">{fmt(data.summary?.total_26as)}</div></div>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600"><tr><th className="text-left px-3 py-2">Client</th><th className="text-right px-3 py-2">In Books</th><th className="text-right px-3 py-2">In 26AS</th><th className="text-right px-3 py-2">Diff</th><th className="text-center px-3 py-2">Status</th></tr></thead>
            <tbody>
              {(data.matches || []).map(m => (
                <tr key={m.client_name} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5">{m.client_name}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(m.in_books)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(m.in_26as)}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${m.diff !== 0 ? "text-rose-700" : "text-emerald-700"}`}>{fmt(m.diff)}</td>
                  <td className="px-3 py-1.5 text-center"><span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${m.status === "matched" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>{m.status}</span></td>
                </tr>
              ))}
              {(data.matches || []).length === 0 && <tr><td colSpan={5} className="text-center py-6 text-xs text-slate-400">No TDS data to reconcile.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle>Upload 26AS Entry</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Client *"><ClientSelect value={upForm.client_name} valueKey="name" label={null} testid={null} onChange={(v) => setUpForm({ ...upForm, client_name: v })} /></Field>
            <Field label="Section"><Input value={upForm.section} onChange={e => setUpForm({ ...upForm, section: e.target.value })} /></Field>
            <Field label="Amount Credited"><Input type="number" value={upForm.amount_credited} onChange={e => setUpForm({ ...upForm, amount_credited: Number(e.target.value) })} /></Field>
            <Field label="TDS Deducted *"><Input type="number" value={upForm.tds_deducted} onChange={e => setUpForm({ ...upForm, tds_deducted: Number(e.target.value) })} /></Field>
            <Field label="Date of Credit"><Input type="date" value={upForm.date_of_credit} onChange={e => setUpForm({ ...upForm, date_of_credit: e.target.value })} /></Field>
            <Field label="Quarter">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={upForm.quarter} onChange={e => setUpForm({ ...upForm, quarter: e.target.value })}>
                <option>Q1</option><option>Q2</option><option>Q3</option><option>Q4</option>
              </select>
            </Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(false)}>Cancel</Button>
            <Button onClick={upload}>Upload</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ═══════ Fixed Assets Register ═══════ */
export function FixedAssetsView() {
  const [data, setData] = useState({ rows: [], summary: {} });
  const [runs, setRuns] = useState({ runs: [], by_period: [] });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    asset_name: "", category: "plant_machinery",
    purchase_date: new Date().toISOString().slice(0, 10),
    purchase_cost: 0, useful_life_years: 10, salvage_value: 0, location: "", serial_no: "",
  });
  const [depPeriod, setDepPeriod] = useState(new Date().toISOString().slice(0, 7));

  const load = () => {
    api.get("/statutory/fixed-assets").then(r => setData(r.data));
    api.get("/statutory/fixed-assets/depreciation/runs").then(r => setRuns(r.data));
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.asset_name || form.purchase_cost <= 0) { toast.error("Name + cost required"); return; }
    try {
      await api.post("/statutory/fixed-assets", form);
      toast.success("Asset added"); setOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const runDep = async () => {
    if (!window.confirm(`Run depreciation for ${depPeriod}? Posts JEs for all active assets (idempotent).`)) return;
    try {
      const r = await api.post(`/statutory/fixed-assets/depreciation/run?period=${depPeriod}`);
      toast.success(`Depreciation: ${r.data.posted} posted, ${r.data.skipped} skipped`); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Fixed Asset Register</CardTitle>
        <div className="flex gap-2">
          <Input placeholder="2026-06" value={depPeriod} onChange={e => setDepPeriod(e.target.value)} className="h-8 w-28" />
          <Button size="sm" variant="outline" onClick={runDep}><Play className="h-3.5 w-3.5 mr-1" />Run Depreciation</Button>
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5 mr-1" />Add Asset</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-4 gap-2">
          <div className="p-3 border rounded bg-slate-50"><div className="text-[10px] uppercase text-slate-500">Assets</div><div className="text-lg font-bold">{data.summary?.count || 0}</div></div>
          <div className="p-3 border rounded bg-blue-50"><div className="text-[10px] uppercase text-slate-500">Total Cost</div><div className="text-lg font-bold tabular-nums text-blue-700">{fmt(data.summary?.total_cost)}</div></div>
          <div className="p-3 border rounded bg-rose-50"><div className="text-[10px] uppercase text-slate-500">Accum. Depreciation</div><div className="text-lg font-bold tabular-nums text-rose-700">{fmt(data.summary?.accumulated_depreciation)}</div></div>
          <div className="p-3 border rounded bg-emerald-50"><div className="text-[10px] uppercase text-slate-500">Book Value</div><div className="text-lg font-bold tabular-nums text-emerald-700">{fmt(data.summary?.book_value)}</div></div>
        </div>
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
              <tr><th className="text-left px-3 py-2">Asset #</th><th className="text-left px-3 py-2">Name</th><th className="text-left px-3 py-2">Category</th><th className="text-left px-3 py-2">Purchased</th><th className="text-right px-3 py-2">Cost</th><th className="text-right px-3 py-2">Monthly Dep</th><th className="text-right px-3 py-2">Accum</th><th className="text-right px-3 py-2">Book Value</th></tr>
            </thead>
            <tbody>
              {(data.rows || []).map(r => (
                <tr key={r.asset_code} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.asset_code}</td>
                  <td className="px-3 py-1.5">{r.asset_name}</td>
                  <td className="px-3 py-1.5 text-xs">{r.category}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.purchase_date}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.purchase_cost)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.monthly_depreciation)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.accumulated_depreciation)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(r.book_value)}</td>
                </tr>
              ))}
              {(data.rows || []).length === 0 && <tr><td colSpan={8} className="text-center py-6 text-xs text-slate-400">No fixed assets registered.</td></tr>}
            </tbody>
          </table>
        </div>
        {(runs.by_period || []).length > 0 && (
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold mb-1">Depreciation History</div>
            <div className="border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs"><tr><th className="text-left px-3 py-1">Period</th><th className="text-right px-3 py-1">Assets</th><th className="text-right px-3 py-1">Total</th></tr></thead>
                <tbody>
                  {runs.by_period.map(p => (
                    <tr key={p.period} className="border-t">
                      <td className="px-3 py-1 font-mono">{p.period}</td>
                      <td className="px-3 py-1 text-right">{p.count}</td>
                      <td className="px-3 py-1 text-right tabular-nums">{fmt(p.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Add Fixed Asset</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Asset Name *"><Input value={form.asset_name} onChange={e => setForm({ ...form, asset_name: e.target.value })} /></Field>
            <Field label="Category">
              <select className="h-9 w-full rounded-sm border bg-background px-2" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                <option value="plant_machinery">Plant & Machinery (1600)</option>
                <option value="vehicle">Vehicle (1610)</option>
                <option value="office_equipment">Office Equipment (1620)</option>
              </select>
            </Field>
            <Field label="Purchase Date *"><Input type="date" value={form.purchase_date} onChange={e => setForm({ ...form, purchase_date: e.target.value })} /></Field>
            <Field label="Purchase Cost *"><Input type="number" value={form.purchase_cost} onChange={e => setForm({ ...form, purchase_cost: Number(e.target.value) })} /></Field>
            <Field label="Useful Life (years)"><Input type="number" value={form.useful_life_years} onChange={e => setForm({ ...form, useful_life_years: Number(e.target.value) })} /></Field>
            <Field label="Salvage Value"><Input type="number" value={form.salvage_value} onChange={e => setForm({ ...form, salvage_value: Number(e.target.value) })} /></Field>
            <Field label="Location"><Input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} /></Field>
            <Field label="Serial #"><Input value={form.serial_no} onChange={e => setForm({ ...form, serial_no: e.target.value })} /></Field>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create}>Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
