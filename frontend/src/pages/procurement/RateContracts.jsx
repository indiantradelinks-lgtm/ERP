/**
 * Rate Contracts · Procurement Extras
 *
 * Approved (vendor, item, period, locked rate) contracts. When a PR is raised
 * for a covered item, system suggests the contract vendor + locked rate.
 *
 * Backend: /api/procurement-extras/rate-contracts/*
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { FileSignature, Plus, RefreshCcw, AlertTriangle, CheckCircle2, X, Trash2 } from "lucide-react";

const STATUS_TONE = {
  active: "bg-emerald-100 text-emerald-700",
  draft: "bg-slate-100 text-slate-700",
  expired: "bg-amber-100 text-amber-700",
  cancelled: "bg-rose-100 text-rose-700",
};

export default function RateContracts() {
  const [tab, setTab] = useState("all");
  const [rows, setRows] = useState([]);
  const [expiring, setExpiring] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openCreate, setOpenCreate] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [rcRes, expRes, vRes] = await Promise.all([
        api.get("/procurement-extras/rate-contracts"),
        api.get("/procurement-extras/rate-contracts/expiring/list?window_days=30"),
        api.get("/vendors?status=approved"),
      ]);
      setRows(rcRes.data || []);
      setExpiring(expRes.data?.rows || []);
      setVendors(vRes.data || []);
    } catch (e) {
      toast.error("Failed to load rate contracts");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadAll(); }, []);

  const filtered = useMemo(() => {
    if (tab === "all") return rows;
    return rows.filter((r) => r.status === tab);
  }, [rows, tab]);

  const activate = async (id) => {
    try {
      await api.post(`/procurement-extras/rate-contracts/${id}/activate`);
      toast.success("Rate contract activated");
      loadAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Activation failed");
    }
  };

  const cancel = async (id) => {
    const reason = window.prompt("Cancel reason (min 3 chars):");
    if (!reason || reason.trim().length < 3) return;
    try {
      await api.post(`/procurement-extras/rate-contracts/${id}/cancel?reason=${encodeURIComponent(reason)}`);
      toast.success("Cancelled");
      loadAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cancel failed");
    }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-rate-contracts">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><FileSignature className="h-6 w-6 text-primary" /> Rate Contracts</h1>
          <p className="text-sm text-muted-foreground">Lock vendor rates by period. PRs for covered items auto-suggest the contract vendor + rate.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} data-testid="rc-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button size="sm" data-testid="rc-new"><Plus className="h-4 w-4 mr-1" />New Rate Contract</Button>
            </DialogTrigger>
            <CreateRCDialog vendors={vendors} onClose={() => { setOpenCreate(false); loadAll(); }} />
          </Dialog>
        </div>
      </div>

      {expiring.length > 0 && (
        <Card className="border-amber-300 bg-amber-50/40" data-testid="rc-expiring-banner">
          <CardContent className="p-3 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <div className="flex-1 text-sm">
              <span className="font-medium">{expiring.length} rate contract(s) expiring within 30 days.</span>
              <span className="ml-2 text-slate-600">{expiring.slice(0, 3).map((e) => `${e.rc_number} (${e.days_to_expiry}d)`).join(" · ")}</span>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {["all", "draft", "active", "expired", "cancelled"].map((s) => (
            <TabsTrigger key={s} value={s} data-testid={`rc-tab-${s}`}>{s.toUpperCase()} ({s === "all" ? rows.length : rows.filter(r => r.status === s).length})</TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={tab}>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-left">RC #</th>
                    <th className="px-3 py-2 text-left">Vendor</th>
                    <th className="px-3 py-2 text-left">Period</th>
                    <th className="px-3 py-2 text-right">Lines</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">Loading…</td></tr>}
                  {!loading && filtered.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">No rate contracts</td></tr>}
                  {filtered.map((r) => (
                    <tr key={r.id} className="border-b" data-testid={`rc-row-${r.id}`}>
                      <td className="px-3 py-2 font-mono text-xs">{r.rc_number}</td>
                      <td className="px-3 py-2">{r.vendor_name}</td>
                      <td className="px-3 py-2 text-xs">{r.start_date} → {r.end_date}</td>
                      <td className="px-3 py-2 text-right">{(r.lines || []).length}</td>
                      <td className="px-3 py-2"><Badge className={STATUS_TONE[r.status] || ""}>{r.status}</Badge></td>
                      <td className="px-3 py-2 text-right space-x-1">
                        {r.status === "draft" && (
                          <Button size="sm" variant="outline" onClick={() => activate(r.id)} data-testid={`rc-activate-${r.id}`}>
                            <CheckCircle2 className="h-3.5 w-3.5 mr-1" />Activate
                          </Button>
                        )}
                        {(r.status === "draft" || r.status === "active") && (
                          <Button size="sm" variant="outline" onClick={() => cancel(r.id)} data-testid={`rc-cancel-${r.id}`}>
                            <X className="h-3.5 w-3.5 mr-1" />Cancel
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CreateRCDialog({ vendors, onClose }) {
  const [vendorId, setVendorId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("30 days credit");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ item_name: "", unit: "Nos", rate: 0, gst_percent: 18 }]);
  const [submitting, setSubmitting] = useState(false);

  const addLine = () => setLines([...lines, { item_name: "", unit: "Nos", rate: 0, gst_percent: 18 }]);
  const removeLine = (idx) => setLines(lines.filter((_, i) => i !== idx));
  const setLine = (idx, field, value) => setLines(lines.map((l, i) => i === idx ? { ...l, [field]: value } : l));

  const submit = async () => {
    if (!vendorId || !startDate || !endDate) {
      toast.error("Vendor, start date and end date are required");
      return;
    }
    if (lines.some((l) => !l.item_name || !l.rate)) {
      toast.error("Every line needs item name and rate");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/procurement-extras/rate-contracts", {
        vendor_id: vendorId, start_date: startDate, end_date: endDate,
        payment_terms: paymentTerms, notes,
        lines: lines.map(l => ({ ...l, rate: Number(l.rate), gst_percent: Number(l.gst_percent) })),
      });
      toast.success("Rate contract created (draft)");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogContent className="max-w-3xl" data-testid="rc-create-dialog">
      <DialogHeader><DialogTitle>New Rate Contract</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <Label>Vendor *</Label>
          <Select value={vendorId || undefined} onValueChange={setVendorId}>
            <SelectTrigger data-testid="rc-vendor"><SelectValue placeholder="— select vendor —" /></SelectTrigger>
            <SelectContent>
              {vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.vendor_code} · {v.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div><Label>Start date *</Label><Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} data-testid="rc-start" /></div>
        <div><Label>End date *</Label><Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} data-testid="rc-end" /></div>
        <div className="col-span-2"><Label>Payment terms</Label><Input value={paymentTerms} onChange={e => setPaymentTerms(e.target.value)} /></div>
        <div className="col-span-2"><Label>Notes</Label><Textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} /></div>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between mb-1">
          <Label className="text-sm font-semibold">Line items</Label>
          <Button size="sm" variant="outline" onClick={addLine} data-testid="rc-add-line"><Plus className="h-3.5 w-3.5 mr-1" />Add line</Button>
        </div>
        <table className="w-full text-xs">
          <thead className="bg-slate-50">
            <tr><th className="p-1 text-left">Item</th><th className="p-1 text-left">Unit</th><th className="p-1 text-right">Rate</th><th className="p-1 text-right">GST%</th><th></th></tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i} className="border-b">
                <td><Input value={l.item_name} onChange={e => setLine(i, "item_name", e.target.value)} className="h-7" data-testid={`rc-line-name-${i}`} /></td>
                <td><Input value={l.unit} onChange={e => setLine(i, "unit", e.target.value)} className="h-7 w-20" /></td>
                <td><Input type="number" value={l.rate} onChange={e => setLine(i, "rate", e.target.value)} className="h-7 w-24 text-right" data-testid={`rc-line-rate-${i}`} /></td>
                <td><Input type="number" value={l.gst_percent} onChange={e => setLine(i, "gst_percent", e.target.value)} className="h-7 w-16 text-right" /></td>
                <td><Button size="icon" variant="ghost" onClick={() => removeLine(i)}><Trash2 className="h-3.5 w-3.5" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={submitting} data-testid="rc-submit">{submitting ? "Saving…" : "Save Draft"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}
