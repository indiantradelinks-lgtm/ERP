import { useEffect, useMemo, useState, Fragment } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Plus, RefreshCw, Search, Trophy, FileText, ChevronRight, Send, Mail, Network, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { Badge } from "@/components/ui/badge";
import LineageTrail from "@/components/LineageTrail";
import { api } from "@/lib/api";
import { downloadPdf } from "@/lib/exports";
import { toast } from "sonner";
import SendEmailDialog from "@/components/SendEmailDialog";

const RFQ_STATUS_TONE = {
  sent: "info", response_pending: "warning", under_evaluation: "info",
  vendor_selected: "success", approved: "success", converted_to_po: "primary",
};

export default function Rfqs() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialPr = searchParams.get("pr") || "";
  const [rows, setRows] = useState([]);
  const [prs, setPrs] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(!!initialPr);
  const [form, setForm] = useState({ pr_id: initialPr, vendor_ids: [], notes: "", response_due_date: "" });
  const [respondOpen, setRespondOpen] = useState(null);
  const [compareOpen, setCompareOpen] = useState(null);
  const [emailFor, setEmailFor] = useState(null);
  const [lineageFor, setLineageFor] = useState(null);

  const load = async () => {
    try {
      const [r, p, v] = await Promise.all([
        api.get("/procurement/rfqs"),
        api.get("/procurement/prs?status=approved"),
        api.get("/vendors"),
      ]);
      setRows(r.data || []); setPrs(p.data || []); setVendors(v.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.pr_id) { toast.error("Pick a PR"); return; }
    if (!form.vendor_ids.length) { toast.error("Pick at least one vendor"); return; }
    try {
      const payload = { pr_id: form.pr_id, vendors: form.vendor_ids.map((vid) => ({ vendor_id: vid })), notes: form.notes, response_due_date: form.response_due_date };
      const { data } = await api.post("/procurement/rfqs", payload);
      toast.success(`${data.rfq_number} created`);
      setOpen(false);
      setForm({ pr_id: "", vendor_ids: [], notes: "", response_due_date: "" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const convertToPO = async (rfq) => {
    if (!rfq.selected_vendor_id) { toast.error("Select a vendor first"); return; }
    if (!window.confirm(`Convert ${rfq.rfq_number} → PO?`)) return;
    try {
      const { data } = await api.post(`/procurement/rfqs/${rfq.id}/convert-to-po`);
      toast.success(`PO ${data.po_number} created`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.rfq_number, r.pr_number, r.status].some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="rfqs-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <FileText className="h-3 w-3" /> Procurement · RFQ
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Request for Quotations</h1>
        <p className="text-sm text-muted-foreground mt-1">Send approved PRs to multiple vendors, record responses and pick the winner via the comparative statement.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search RFQ #, PR #…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="rfqs-search" />
          </div>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => setOpen(true)} data-testid="rfqs-add"><Plus className="h-4 w-4 mr-1" /> New RFQ</Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">RFQ #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">PR #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Vendors</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Selected</TableHead>
                <TableHead className="text-right w-72">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-10 text-sm">No RFQs yet.</TableCell></TableRow>}
              {filtered.map((r) => {
                const responded = (r.vendors || []).filter((v) => v.status === "responded").length;
                const selectedVendor = (r.vendors || []).find((v) => v.vendor_id === r.selected_vendor_id);
                return (
                  <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`rfq-row-${r.id}`}>
                    <TableCell className="font-mono-data text-sm font-bold">{r.rfq_number}</TableCell>
                    <TableCell className="font-mono-data text-xs">{r.pr_number}</TableCell>
                    <TableCell className="text-xs">{(r.vendors || []).length} vendor{r.vendors?.length === 1 ? "" : "s"}<div className="text-[10px] text-muted-foreground">{responded} responded</div></TableCell>
                    <TableCell><StatusBadge text={(r.status || "").replaceAll("_", " ")} tone={RFQ_STATUS_TONE[r.status] || "neutral"} /></TableCell>
                    <TableCell className="text-xs">{selectedVendor ? <StatusBadge text={selectedVendor.vendor_name} tone="success" /> : "—"}</TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setRespondOpen(r)} data-testid={`rfq-respond-${r.id}`}>
                          <Send className="h-3 w-3 mr-1" /> Response
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setEmailFor(r)} data-testid={`rfq-email-${r.id}`}>
                          <Mail className="h-3 w-3 mr-1" /> Email
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setCompareOpen(r)} data-testid={`rfq-compare-${r.id}`}>
                          <Trophy className="h-3 w-3 mr-1" /> Compare
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(r)} data-testid={`rfq-lineage-${r.id}`} title="View end-to-end procurement lineage">
                          <Network className="h-3 w-3 mr-1" /> Lineage
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/rfqs/${r.id}/pdf`, `${r.rfq_number}.pdf`)} data-testid={`rfq-pdf-${r.id}`} title="Download RFQ PDF">
                          <FileDown className="h-3 w-3 mr-1" /> PDF
                        </Button>
                        {r.selected_vendor_id && r.status !== "converted_to_po" && (
                          <Button size="sm" className="h-7 rounded-sm" onClick={() => convertToPO(r)} data-testid={`rfq-convert-${r.id}`}>
                            <ChevronRight className="h-3 w-3 mr-1" /> PO
                          </Button>
                        )}
                        {r.po_number && (
                          <button onClick={() => navigate("/app/purchase-orders")} className="text-xs underline text-primary px-2" data-testid={`rfq-po-link-${r.id}`}>
                            {r.po_number}
                          </button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Create dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">New RFQ</DialogTitle>
            <DialogDescription className="sr-only">Pick an approved PR and one or more vendors to send the RFQ.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-xs uppercase tracking-wider">PR (approved only)</Label>
              <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" value={form.pr_id} onChange={(e) => setForm({ ...form, pr_id: e.target.value })} data-testid="rfq-pr-select">
                <option value="">— pick a PR —</option>
                {prs.map((p) => <option key={p.id} value={p.id}>{p.pr_number} · {p.department || ""} · {(p.items || []).length} items</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Vendors</Label>
              <div className="flex flex-wrap gap-1.5 p-2 border border-input rounded-sm bg-background mt-1 max-h-48 overflow-y-auto" data-testid="rfq-vendor-list">
                {vendors.map((v) => {
                  const active = form.vendor_ids.includes(v.id);
                  return (
                    <button key={v.id} type="button" onClick={() => setForm((f) => ({ ...f, vendor_ids: active ? f.vendor_ids.filter((x) => x !== v.id) : [...f.vendor_ids, v.id] }))}
                      className={`text-[11px] font-bold uppercase tracking-wider px-2 py-1 rounded-sm border ${active ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary/40"}`}
                      data-testid={`rfq-vendor-${v.id}`}>
                      {v.name}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs uppercase tracking-wider">Response Due</Label>
                <Input type="date" value={form.response_due_date} onChange={(e) => setForm({ ...form, response_due_date: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="rfq-due-date" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider">Notes</Label>
                <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="rfq-notes" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="rfq-save">Send RFQ</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Response dialog */}
      {respondOpen && <ResponseDialog rfq={respondOpen} onClose={() => { setRespondOpen(null); load(); }} />}

      {/* Compare dialog */}
      {compareOpen && <CompareDialog rfq={compareOpen} onClose={() => { setCompareOpen(null); load(); }} />}

      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="rfq"
        recordId={emailFor?.id}
      />

      <Dialog open={!!lineageFor} onOpenChange={(o) => !o && setLineageFor(null)}>
        <DialogContent className="max-w-5xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Procurement Lineage — {lineageFor?.rfq_number}</DialogTitle>
            <DialogDescription>End-to-end traceability from the PR origin through the PO and GRNs.</DialogDescription>
          </DialogHeader>
          {lineageFor && <LineageTrail kind="rfq" recordId={lineageFor.id} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ResponseDialog({ rfq, onClose }) {
  const items = rfq.items || [];
  const units = useMemo(() => Array.from(new Set(items.map((i) => i.unit || "Nos"))), [items]);
  const heterogeneous = units.length > 1;
  const [rows, setRows] = useState((rfq.vendors || []).map((v) => ({
    vendor_id: v.vendor_id,
    vendor_name: v.vendor_name,
    rate_quoted: v.rate_quoted ?? "",
    item_rates: { ...(v.item_rates || {}) },
    delivery_days: v.delivery_days ?? "",
    payment_terms: v.payment_terms ?? "",
    technical_score: v.technical_score ?? "",
    note: v.note ?? "",
    status: v.status,
    expanded: heterogeneous,   // auto-expand per-item editor when UoMs differ
  })));

  const setField = (i, patch) => setRows((rs) => rs.map((r, ix) => ix === i ? { ...r, ...patch } : r));
  const setItemRate = (i, idx, val) => setRows((rs) => rs.map((r, ix) => {
    if (ix !== i) return r;
    const next = { ...r.item_rates };
    if (val === "" || val === null) delete next[String(idx)];
    else next[String(idx)] = val;
    return { ...r, item_rates: next };
  }));

  const record = async (row) => {
    const itemRatesNum = {};
    Object.entries(row.item_rates || {}).forEach(([k, v]) => {
      if (v !== "" && v !== null && !isNaN(Number(v))) itemRatesNum[k] = Number(v);
    });
    const hasItemRates = Object.keys(itemRatesNum).length > 0;
    if (!hasItemRates && (row.rate_quoted === "" || row.rate_quoted === null)) {
      toast.error("Enter a quoted rate (or fill per-item rates)"); return;
    }
    try {
      await api.post(`/procurement/rfqs/${rfq.id}/respond`, {
        vendor_id: row.vendor_id,
        rate_quoted: row.rate_quoted === "" || row.rate_quoted === null ? null : Number(row.rate_quoted),
        item_rates: hasItemRates ? itemRatesNum : null,
        delivery_days: row.delivery_days === "" ? null : Number(row.delivery_days),
        payment_terms: row.payment_terms || null,
        technical_score: row.technical_score === "" ? null : Number(row.technical_score),
        note: row.note || null,
      });
      toast.success(`Recorded ${row.vendor_name}`);
      setRows((rs) => rs.map((r) => r.vendor_id === row.vendor_id ? { ...r, status: "responded" } : r));
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Record vendor responses · {rfq.rfq_number}</DialogTitle>
          <DialogDescription className="sr-only">Enter rate, delivery days, payment terms and technical score per vendor. Per-item rates supported.</DialogDescription>
        </DialogHeader>
        {heterogeneous && (
          <div className="bg-warning/10 border border-warning/40 rounded-sm p-2.5 text-xs" data-testid="rfq-hetero-banner">
            <strong className="text-warning">Heterogeneous UoMs detected</strong> · items use {units.join(" · ")}. Use per-item rates for an accurate comparative.
          </div>
        )}
        <Table>
          <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Default Rate</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Delivery (d)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Payment</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Tech Score</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((row, i) => (
              <Fragment key={row.vendor_id}>
                <TableRow data-testid={`rfq-respond-row-${row.vendor_id}`}>
                  <TableCell className="text-sm font-semibold">
                    <div>{row.vendor_name}</div>
                    {items.length > 1 && (
                      <button type="button" className="text-[10px] text-primary underline mt-0.5" onClick={() => setField(i, { expanded: !row.expanded })} data-testid={`rfq-toggle-items-${row.vendor_id}`}>
                        {row.expanded ? "Hide" : "Show"} per-item rates ({items.length} items)
                      </button>
                    )}
                  </TableCell>
                  <TableCell><Input type="number" value={row.rate_quoted} onChange={(e) => setField(i, { rate_quoted: e.target.value })} className="h-8 rounded-sm w-28" placeholder="—" data-testid={`rfq-rate-${row.vendor_id}`} /></TableCell>
                  <TableCell><Input type="number" value={row.delivery_days} onChange={(e) => setField(i, { delivery_days: e.target.value })} className="h-8 rounded-sm w-20" /></TableCell>
                  <TableCell><Input value={row.payment_terms} onChange={(e) => setField(i, { payment_terms: e.target.value })} className="h-8 rounded-sm w-28" /></TableCell>
                  <TableCell><Input type="number" value={row.technical_score} onChange={(e) => setField(i, { technical_score: e.target.value })} className="h-8 rounded-sm w-20" placeholder="0-100" /></TableCell>
                  <TableCell><StatusBadge text={row.status?.replaceAll("_", " ")} tone={row.status === "responded" ? "success" : "warning"} /></TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" className="h-7 rounded-sm" onClick={() => record(row)} data-testid={`rfq-save-${row.vendor_id}`}>Save</Button>
                  </TableCell>
                </TableRow>
                {row.expanded && items.length > 0 && (
                  <TableRow className="bg-muted/20 hover:bg-muted/20" data-testid={`rfq-items-row-${row.vendor_id}`}>
                    <TableCell colSpan={7} className="p-3">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-2">Per-item rates · leave blank to use default ({row.rate_quoted || "—"})</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {items.map((it, idx) => (
                          <div key={`${row.vendor_id}-${idx}`} className="flex items-center gap-2 bg-card border border-border rounded-sm p-2">
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-semibold truncate">{it.name}</div>
                              <div className="text-[10px] text-muted-foreground tabular">{it.quantity} {it.unit || "Nos"}</div>
                            </div>
                            <Input type="number" value={row.item_rates[String(idx)] ?? ""} onChange={(e) => setItemRate(i, idx, e.target.value)} className="h-7 rounded-sm w-24" placeholder="rate" data-testid={`rfq-item-rate-${row.vendor_id}-${idx}`} />
                          </div>
                        ))}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompareDialog({ rfq, onClose }) {
  const [data, setData] = useState(null);
  const [openVendor, setOpenVendor] = useState(null);
  const [justifyFor, setJustifyFor] = useState(null);
  const [justification, setJustification] = useState("");
  useEffect(() => {
    api.get(`/procurement/rfqs/${rfq.id}/comparative`).then((r) => setData(r.data)).catch(() => setData(null));
  }, [rfq.id]);

  const selectVendor = async (vendor_id, isL1) => {
    if (!isL1 && data?.l1_vendor_id) {
      // open the justification modal first
      setJustifyFor(vendor_id);
      return;
    }
    try {
      await api.post(`/procurement/rfqs/${rfq.id}/select-vendor`, { vendor_id });
      toast.success("Vendor selected");
      const { data: refreshed } = await api.get(`/procurement/rfqs/${rfq.id}/comparative`);
      setData(refreshed);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const confirmNonL1 = async () => {
    if (justification.trim().length < 20) {
      toast.error("Please enter at least 20 characters of justification.");
      return;
    }
    try {
      await api.post(`/procurement/rfqs/${rfq.id}/select-vendor`, {
        vendor_id: justifyFor, justification: justification.trim(),
      });
      toast.success("Non-L1 vendor selected with justification");
      setJustifyFor(null); setJustification("");
      const { data: refreshed } = await api.get(`/procurement/rfqs/${rfq.id}/comparative`);
      setData(refreshed);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const inr = (n) => n == null ? "—" : "₹ " + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center justify-between gap-2">
            <span>Comparative Statement · {rfq.rfq_number}</span>
            <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => downloadPdf(`/procurement/rfqs/${rfq.id}/comparative/pdf`, `Comparative-${rfq.rfq_number}.pdf`)} data-testid={`rfq-compare-pdf-${rfq.id}`}>
              <FileDown className="h-3 w-3 mr-1" /> Download PDF
            </Button>
          </DialogTitle>
          <DialogDescription className="sr-only">Per-item landed value comparison across all vendors.</DialogDescription>
        </DialogHeader>
        {!data && <div className="text-sm text-muted-foreground py-6 text-center">Loading…</div>}
        {data?.heterogeneous_uom && (
          <div className="bg-warning/10 border border-warning/40 rounded-sm p-2.5 text-xs" data-testid="rfq-compare-hetero">
            <strong className="text-warning">Heterogeneous UoMs</strong> in this RFQ ({data.units.join(" · ")}). Landed value is summed per item using each vendor's item-specific rate, falling back to the default rate where unset.
          </div>
        )}
        {data && (
          <Table>
            <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Default Rate</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Landed (₹)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Delivery</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Payment</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Tech</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.rows.map((r) => {
                const isOpen = openVendor === r.vendor_id;
                return (
                  <Fragment key={r.vendor_id}>
                    <TableRow data-testid={`rfq-compare-row-${r.vendor_id}`}>
                      <TableCell className="text-sm font-semibold">
                        <div className="flex items-center gap-2">
                          {r.rank_label && (
                            <Badge className={r.rank === 1 ? "bg-amber-100 text-amber-700 font-mono" : "bg-slate-100 text-slate-700 font-mono"}>
                              {r.rank_label}
                            </Badge>
                          )}
                          {r.vendor_name}
                          {r.is_selected && <StatusBadge text="Selected" tone="success" />}
                        </div>
                        {r.delta_vs_l1 != null && (
                          <div className="text-[10px] text-rose-700 mt-0.5">
                            +₹{Number(r.delta_vs_l1).toLocaleString("en-IN")} ({r.delta_pct_vs_l1}%) above L1
                          </div>
                        )}
                        {(r.item_breakdown || []).length > 1 && (
                          <button type="button" className="text-[10px] text-primary underline mt-0.5" onClick={() => setOpenVendor(isOpen ? null : r.vendor_id)} data-testid={`rfq-compare-toggle-${r.vendor_id}`}>
                            {isOpen ? "Hide" : "Show"} per-item breakdown
                          </button>
                        )}
                      </TableCell>
                      <TableCell className="font-mono-data tabular text-sm">{inr(r.rate_quoted)}</TableCell>
                      <TableCell className="font-mono-data tabular text-sm font-bold">{inr(r.landed_value)}</TableCell>
                      <TableCell className="text-xs">{r.delivery_days ?? "—"} d</TableCell>
                      <TableCell className="text-xs">{r.payment_terms || "—"}</TableCell>
                      <TableCell className="text-xs">{r.technical_score ?? "—"}</TableCell>
                      <TableCell className="text-right">
                        {!r.is_selected && r.status === "responded" && (
                          <Button size="sm" className="h-7 rounded-sm" onClick={() => selectVendor(r.vendor_id, r.rank === 1)} data-testid={`rfq-select-${r.vendor_id}`}>
                            <Trophy className="h-3 w-3 mr-1" /> Select{r.rank !== 1 && r.rank_label ? ` (${r.rank_label})` : ""}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="bg-muted/20 hover:bg-muted/20" data-testid={`rfq-compare-items-${r.vendor_id}`}>
                        <TableCell colSpan={7} className="p-3">
                          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mb-2">Per-item landed value</div>
                          <Table>
                            <TableHeader><TableRow className="bg-background hover:bg-background">
                              <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                              <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
                              <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
                              <TableHead className="text-[10px] uppercase tracking-wider">Source</TableHead>
                              <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>
                              {r.item_breakdown.map((b) => (
                                <TableRow key={`${r.vendor_id}-${b.index}`}>
                                  <TableCell className="text-xs font-semibold">{b.name}</TableCell>
                                  <TableCell className="text-xs tabular">{b.quantity} {b.unit || "Nos"}</TableCell>
                                  <TableCell className="text-xs tabular">{inr(b.rate)}</TableCell>
                                  <TableCell className="text-[10px]">
                                    <StatusBadge text={b.source.replaceAll("_", " ")} tone={b.source === "item_rate" ? "success" : b.source === "fallback_rate" ? "info" : "danger"} />
                                  </TableCell>
                                  <TableCell className="text-xs tabular font-bold">{inr(b.value)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>

      <Dialog open={!!justifyFor} onOpenChange={(o) => { if (!o) { setJustifyFor(null); setJustification(""); } }}>
        <DialogContent className="max-w-lg rounded-sm" data-testid="non-l1-justification-dialog">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2 text-amber-700">
              <Trophy className="h-5 w-5" /> Non-L1 Vendor Selection
            </DialogTitle>
            <DialogDescription>
              You're picking a vendor that is NOT L1 (lowest landed cost). A written justification of at least 20 characters is mandatory and will be saved to the RFQ audit trail.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label className="text-xs uppercase tracking-wider">Justification *</Label>
            <textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="e.g. L1 cannot meet our 3-day delivery deadline; L2 has higher technical score and approved track record on similar projects."
              className="w-full min-h-[100px] rounded-sm border border-input bg-background p-2 text-sm"
              data-testid="non-l1-justification-text"
            />
            <div className="text-[10px] text-muted-foreground">{justification.trim().length}/20 characters minimum</div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setJustifyFor(null); setJustification(""); }}>Cancel</Button>
            <Button
              onClick={confirmNonL1}
              disabled={justification.trim().length < 20}
              className="bg-amber-600 hover:bg-amber-700 text-white"
              data-testid="non-l1-confirm"
            >
              Select with justification
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
