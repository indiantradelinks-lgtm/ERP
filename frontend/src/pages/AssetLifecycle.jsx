import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Wrench, FileText, Calendar, Activity, Shield, Plus, ArrowLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function AssetLifecycle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [assets, setAssets] = useState([]);
  const [selectedId, setSelectedId] = useState(id || "");
  const [lifecycle, setLifecycle] = useState(null);
  const [openDlg, setOpenDlg] = useState(null);  // "dep" | "amc" | "cal" | "warr"
  const [form, setForm] = useState({});

  useEffect(() => {
    api.get("/assets").then((r) => setAssets(r.data || [])).catch(() => setAssets([]));
  }, []);

  useEffect(() => {
    if (!selectedId) { setLifecycle(null); return; }
    api.get(`/assets/${selectedId}/lifecycle`)
      .then((r) => setLifecycle(r.data))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load lifecycle"));
  }, [selectedId]);

  const openWith = (kind) => {
    setForm(kind === "dep" ? { period: new Date().toISOString().slice(0, 7), method: "straight_line", opening_value: 0, depreciation: 0, closing_value: 0 }
      : kind === "amc" ? { vendor_name: "", start_date: new Date().toISOString().slice(0, 10), end_date: "", amount: 0 }
      : kind === "cal" ? { calibrated_by: "", calibration_date: new Date().toISOString().slice(0, 10), next_due_date: "", result: "pass" }
      : { warranty_vendor: lifecycle?.warranty?.vendor || "", warranty_start: lifecycle?.warranty?.start || "", warranty_expiry: lifecycle?.warranty?.expiry || "", warranty_terms: lifecycle?.warranty?.terms || "" });
    setOpenDlg(kind);
  };

  const save = async () => {
    try {
      let url = "";
      let body = { ...form };
      if (openDlg === "dep") { url = `/assets/${selectedId}/depreciation`; ["opening_value", "depreciation", "closing_value"].forEach((k) => body[k] = Number(body[k]) || 0); }
      else if (openDlg === "amc") { url = `/assets/${selectedId}/amc`; body.amount = Number(body.amount) || 0; }
      else if (openDlg === "cal") url = `/assets/${selectedId}/calibration`;
      else if (openDlg === "warr") { await api.put(`/assets/${selectedId}/warranty`, body); toast.success("Warranty saved"); setOpenDlg(null); refresh(); return; }
      const { data } = await api.post(url, body);
      toast.success("Saved");
      setOpenDlg(null);
      refresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const refresh = () => { if (selectedId) api.get(`/assets/${selectedId}/lifecycle`).then((r) => setLifecycle(r.data)); };

  return (
    <div className="space-y-6" data-testid="asset-lifecycle-page">
      <div className="flex items-start gap-3">
        <Button variant="outline" size="sm" className="rounded-sm h-9" onClick={() => navigate(-1)}><ArrowLeft className="h-4 w-4" /></Button>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Wrench className="h-3 w-3" /> Procurement · Asset Lifecycle
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Asset Lifecycle</h1>
          <p className="text-sm text-muted-foreground mt-1">Track depreciation, AMC contracts, calibration records and warranty per asset.</p>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm p-4">
        <Label className="text-xs uppercase tracking-wider">Select Asset</Label>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className="h-9 w-full md:w-96 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="asset-select">
          <option value="">— pick an asset —</option>
          {assets.map((a) => <option key={a.id} value={a.id}>{a.name || a.item_name} {a.serial_no ? `· ${a.serial_no}` : ""}</option>)}
        </select>
      </div>

      {lifecycle && (
        <div className="space-y-6">
          {/* Asset summary */}
          <div className="bg-card border border-border rounded-sm p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Asset" value={lifecycle.asset.name || lifecycle.asset.item_name || "—"} />
            <Stat label="Serial / Code" value={lifecycle.asset.serial_no || lifecycle.asset.code || "—"} />
            <Stat label="Book Value" value={inr(lifecycle.asset.current_book_value)} />
            <Stat label="AMC Active" value={lifecycle.asset.amc_active ? "Yes" : "No"} tone={lifecycle.asset.amc_active ? "success" : "neutral"} />
            <Stat label="Last Calibration" value={lifecycle.asset.last_calibration_date || "—"} />
            <Stat label="Next Due" value={lifecycle.asset.next_calibration_due || "—"} tone={overdue(lifecycle.asset.next_calibration_due) ? "danger" : "neutral"} />
            <Stat label="Warranty Vendor" value={lifecycle.warranty?.vendor || "—"} />
            <Stat label="Warranty Expiry" value={lifecycle.warranty?.expiry || "—"} tone={overdue(lifecycle.warranty?.expiry) ? "danger" : "neutral"} />
          </div>

          {/* Depreciation */}
          <Section title="Depreciation" icon={Activity} testid="lifecycle-dep" onAdd={() => openWith("dep")}>
            {lifecycle.depreciation.length === 0 ? <EmptyMsg /> : (
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">Period</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Method</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Opening</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Dep.</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Closing</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {lifecycle.depreciation.map((d) => (
                    <TableRow key={d.id} data-testid={`dep-row-${d.id}`}>
                      <TableCell className="font-mono-data text-xs">{d.period}</TableCell>
                      <TableCell className="text-xs">{d.method}</TableCell>
                      <TableCell className="text-sm tabular">{inr(d.opening_value)}</TableCell>
                      <TableCell className="text-sm tabular text-warning">{inr(d.depreciation)}</TableCell>
                      <TableCell className="text-sm tabular font-bold">{inr(d.closing_value)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>

          {/* AMC */}
          <Section title="AMC Contracts" icon={Shield} testid="lifecycle-amc" onAdd={() => openWith("amc")}>
            {lifecycle.amcs.length === 0 ? <EmptyMsg /> : (
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Start · End</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Amount</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Coverage</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {lifecycle.amcs.map((a) => (
                    <TableRow key={a.id} data-testid={`amc-row-${a.id}`}>
                      <TableCell className="text-sm font-semibold">{a.vendor_name}</TableCell>
                      <TableCell className="font-mono-data text-xs">{a.start_date} → {a.end_date}</TableCell>
                      <TableCell className="text-sm tabular">{inr(a.amount)}</TableCell>
                      <TableCell className="text-xs">{a.coverage || "—"}</TableCell>
                      <TableCell><StatusBadge text={overdue(a.end_date) ? "expired" : "active"} tone={overdue(a.end_date) ? "danger" : "success"} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>

          {/* Calibration */}
          <Section title="Calibration Logs" icon={Calendar} testid="lifecycle-cal" onAdd={() => openWith("cal")}>
            {lifecycle.calibrations.length === 0 ? <EmptyMsg /> : (
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">By</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Result</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Next Due</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Note</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {lifecycle.calibrations.map((c) => (
                    <TableRow key={c.id} data-testid={`cal-row-${c.id}`}>
                      <TableCell className="font-mono-data text-xs">{c.calibration_date}</TableCell>
                      <TableCell className="text-sm">{c.calibrated_by}</TableCell>
                      <TableCell><StatusBadge text={c.result} tone={c.result === "pass" ? "success" : c.result === "fail" ? "danger" : "warning"} /></TableCell>
                      <TableCell className="font-mono-data text-xs">{c.next_due_date || "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{c.note || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>

          {/* Warranty */}
          <Section title="Warranty" icon={FileText} testid="lifecycle-warr" onAdd={() => openWith("warr")}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3">
              <Stat label="Vendor" value={lifecycle.warranty?.vendor || "—"} />
              <Stat label="Start" value={lifecycle.warranty?.start || "—"} />
              <Stat label="Expiry" value={lifecycle.warranty?.expiry || "—"} tone={overdue(lifecycle.warranty?.expiry) ? "danger" : "neutral"} />
              <Stat label="Terms" value={lifecycle.warranty?.terms || "—"} />
            </div>
          </Section>
        </div>
      )}

      {/* Add dialog */}
      <Dialog open={!!openDlg} onOpenChange={(o) => !o && setOpenDlg(null)}>
        <DialogContent className="max-w-xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">
              {openDlg === "dep" ? "Record Depreciation" : openDlg === "amc" ? "Add AMC" : openDlg === "cal" ? "Log Calibration" : "Update Warranty"}
            </DialogTitle>
            <DialogDescription className="sr-only">Asset lifecycle event entry.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {openDlg === "dep" && (
              <>
                <Two><F label="Period (YYYY-MM)" v={form.period} on={(v) => setForm({ ...form, period: v })} testid="dep-period" /><F label="Method" v={form.method} on={(v) => setForm({ ...form, method: v })} testid="dep-method" /></Two>
                <Two><F label="Opening" type="number" v={form.opening_value} on={(v) => setForm({ ...form, opening_value: v })} testid="dep-open" /><F label="Depreciation" type="number" v={form.depreciation} on={(v) => setForm({ ...form, depreciation: v })} testid="dep-amount" /></Two>
                <F label="Closing" type="number" v={form.closing_value} on={(v) => setForm({ ...form, closing_value: v })} testid="dep-close" />
              </>
            )}
            {openDlg === "amc" && (
              <>
                <F label="Vendor name" v={form.vendor_name} on={(v) => setForm({ ...form, vendor_name: v })} testid="amc-vendor" />
                <Two><F label="Start date" type="date" v={form.start_date} on={(v) => setForm({ ...form, start_date: v })} testid="amc-start" /><F label="End date" type="date" v={form.end_date} on={(v) => setForm({ ...form, end_date: v })} testid="amc-end" /></Two>
                <Two><F label="Amount" type="number" v={form.amount} on={(v) => setForm({ ...form, amount: v })} testid="amc-amount" /><F label="Coverage" v={form.coverage} on={(v) => setForm({ ...form, coverage: v })} testid="amc-coverage" /></Two>
                <F label="Note" v={form.note} on={(v) => setForm({ ...form, note: v })} testid="amc-note" />
              </>
            )}
            {openDlg === "cal" && (
              <>
                <Two><F label="Calibrated by" v={form.calibrated_by} on={(v) => setForm({ ...form, calibrated_by: v })} testid="cal-by" /><F label="Date" type="date" v={form.calibration_date} on={(v) => setForm({ ...form, calibration_date: v })} testid="cal-date" /></Two>
                <Two>
                  <div><Label className="text-xs uppercase tracking-wider">Result</Label><select value={form.result} onChange={(e) => setForm({ ...form, result: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="cal-result"><option value="pass">Pass</option><option value="conditional">Conditional</option><option value="fail">Fail</option></select></div>
                  <F label="Next Due" type="date" v={form.next_due_date} on={(v) => setForm({ ...form, next_due_date: v })} testid="cal-next" />
                </Two>
                <F label="Note" v={form.note} on={(v) => setForm({ ...form, note: v })} testid="cal-note" />
              </>
            )}
            {openDlg === "warr" && (
              <>
                <F label="Vendor" v={form.warranty_vendor} on={(v) => setForm({ ...form, warranty_vendor: v })} testid="warr-vendor" />
                <Two><F label="Start" type="date" v={form.warranty_start} on={(v) => setForm({ ...form, warranty_start: v })} testid="warr-start" /><F label="Expiry" type="date" v={form.warranty_expiry} on={(v) => setForm({ ...form, warranty_expiry: v })} testid="warr-expiry" /></Two>
                <F label="Terms" v={form.warranty_terms} on={(v) => setForm({ ...form, warranty_terms: v })} testid="warr-terms" />
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpenDlg(null)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="lifecycle-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function overdue(d) { return d && new Date(d) < new Date(); }
function Two({ children }) { return <div className="grid grid-cols-2 gap-3">{children}</div>; }
function F({ label, v, on, testid, type = "text" }) {
  return (<div><Label className="text-xs uppercase tracking-wider">{label}</Label><Input type={type} value={v ?? ""} onChange={(e) => on(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} /></div>);
}
function Stat({ label, value, tone = "neutral" }) {
  const c = { success: "text-success", danger: "text-destructive", warning: "text-warning", neutral: "text-foreground" }[tone];
  return (<div><div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div><div className={`text-sm font-semibold mt-0.5 ${c}`}>{value}</div></div>);
}
function Section({ title, icon: Icon, testid, onAdd, children }) {
  return (
    <div className="bg-card border border-border rounded-sm overflow-hidden" data-testid={testid}>
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-1.5"><Icon className="h-3 w-3" /> {title}</div>
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={onAdd} data-testid={`${testid}-add`}><Plus className="h-3 w-3 mr-1" /> Add</Button>
      </div>
      {children}
    </div>
  );
}
function EmptyMsg() { return <div className="text-center text-xs text-muted-foreground py-6">No records yet.</div>; }
