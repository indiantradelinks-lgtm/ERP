/**
 * Service Orders + Service Receipt Notes · Procurement Extras
 *
 * Counterpart of PO/GRN for service vendors (labour contractors, transporters,
 * fabricators, manpower agencies). Captures rate_basis + service period; SRN
 * closes against the SO with certified value.
 *
 * Backend: /api/procurement-extras/service-orders/* + /srns
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Briefcase, Plus, RefreshCcw, CheckCircle2, FileCheck2, X, FileDown } from "lucide-react";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700",
  in_progress: "bg-blue-100 text-blue-700",
  partially_received: "bg-purple-100 text-purple-700",
  closed: "bg-emerald-100 text-emerald-700",
  cancelled: "bg-rose-100 text-rose-700",
};
const RATE_BASIS = [
  { v: "per_day", l: "Per Day" }, { v: "per_month", l: "Per Month" },
  { v: "per_qty", l: "Per Quantity" }, { v: "lump_sum", l: "Lump Sum" },
  { v: "per_manpower", l: "Per Manpower" }, { v: "per_shift", l: "Per Shift" },
];

export default function ServiceOrders() {
  const [tab, setTab] = useState("all");
  const [rows, setRows] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openCreate, setOpenCreate] = useState(false);
  const [openSRN, setOpenSRN] = useState(null);
  const [viewSRNs, setViewSRNs] = useState(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [soRes, vRes, pRes] = await Promise.all([
        api.get("/procurement-extras/service-orders"),
        api.get("/vendors?status=approved"),
        api.get("/projects"),
      ]);
      setRows(soRes.data || []);
      setVendors(vRes.data || []);
      setProjects(pRes.data || []);
    } catch (e) {
      toast.error("Failed to load service orders");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadAll(); }, []);

  const filtered = useMemo(() => tab === "all" ? rows : rows.filter(r => r.status === tab), [rows, tab]);

  const approve = async (id) => {
    try {
      await api.post(`/procurement-extras/service-orders/${id}/approve`);
      toast.success("Service order approved");
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Approve failed"); }
  };

  const cancel = async (id) => {
    const reason = window.prompt("Cancel reason (min 3 chars):");
    if (!reason || reason.trim().length < 3) return;
    try {
      await api.post(`/procurement-extras/service-orders/${id}/cancel?reason=${encodeURIComponent(reason)}`);
      toast.success("Cancelled");
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Cancel failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="page-service-orders">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Briefcase className="h-6 w-6 text-primary" /> Service Orders & Receipts</h1>
          <p className="text-sm text-muted-foreground">Service vendors / labour contractors / subcontractors — SO → SRN flow.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} data-testid="so-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button size="sm" data-testid="so-new"><Plus className="h-4 w-4 mr-1" />New Service Order</Button>
            </DialogTrigger>
            <CreateSODialog vendors={vendors} projects={projects} onClose={() => { setOpenCreate(false); loadAll(); }} />
          </Dialog>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {["all", "draft", "approved", "partially_received", "closed", "cancelled"].map((s) => (
            <TabsTrigger key={s} value={s} data-testid={`so-tab-${s}`}>
              {s.replace("_", " ").toUpperCase()} ({s === "all" ? rows.length : rows.filter(r => r.status === s).length})
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={tab}>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-left">SO #</th>
                    <th className="px-3 py-2 text-left">Vendor</th>
                    <th className="px-3 py-2 text-left">Service</th>
                    <th className="px-3 py-2 text-left">Period</th>
                    <th className="px-3 py-2 text-right">Total</th>
                    <th className="px-3 py-2 text-right">Received</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">Loading…</td></tr>}
                  {!loading && filtered.length === 0 && <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">No service orders</td></tr>}
                  {filtered.map((r) => (
                    <tr key={r.id} className="border-b" data-testid={`so-row-${r.id}`}>
                      <td className="px-3 py-2 font-mono text-xs">{r.so_number}</td>
                      <td className="px-3 py-2">{r.vendor_name}</td>
                      <td className="px-3 py-2 text-xs">{r.service_type}</td>
                      <td className="px-3 py-2 text-xs">{r.start_date} → {r.end_date}</td>
                      <td className="px-3 py-2 text-right">₹{(r.total_amount || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-right">₹{(r.received_value || 0).toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2"><Badge className={STATUS_TONE[r.status] || ""}>{r.status}</Badge></td>
                      <td className="px-3 py-2 text-right space-x-1">
                        {r.status === "draft" && (
                          <Button size="sm" variant="outline" onClick={() => approve(r.id)} data-testid={`so-approve-${r.id}`}>
                            <CheckCircle2 className="h-3.5 w-3.5 mr-1" />Approve
                          </Button>
                        )}
                        {["approved", "in_progress", "partially_received"].includes(r.status) && (
                          <Button size="sm" variant="outline" onClick={() => setOpenSRN(r)} data-testid={`so-srn-${r.id}`}>
                            <FileCheck2 className="h-3.5 w-3.5 mr-1" />Record SRN
                          </Button>
                        )}
                        {(r.received_value || 0) > 0 && (
                          <Button size="sm" variant="ghost" onClick={() => setViewSRNs(r)} data-testid={`so-view-srns-${r.id}`}>
                            <FileDown className="h-3.5 w-3.5 mr-1" />SRNs
                          </Button>
                        )}
                        {r.status !== "closed" && r.status !== "cancelled" && (
                          <Button size="sm" variant="ghost" onClick={() => cancel(r.id)} data-testid={`so-cancel-${r.id}`}>
                            <X className="h-3.5 w-3.5" />
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

      {openSRN && (
        <Dialog open={!!openSRN} onOpenChange={() => setOpenSRN(null)}>
          <CreateSRNDialog so={openSRN} onClose={() => { setOpenSRN(null); loadAll(); }} />
        </Dialog>
      )}
      {viewSRNs && (
        <Dialog open={!!viewSRNs} onOpenChange={() => setViewSRNs(null)}>
          <SRNListDialog so={viewSRNs} />
        </Dialog>
      )}
    </div>
  );
}

function CreateSODialog({ vendors, projects, onClose }) {
  const [vendorId, setVendorId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [serviceType, setServiceType] = useState("manpower");
  const [scope, setScope] = useState("");
  const [rateBasis, setRateBasis] = useState("per_day");
  const [rate, setRate] = useState(0);
  const [qty, setQty] = useState(1);
  const [unit, setUnit] = useState("Day");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [gst, setGst] = useState(18);
  const [tdsOn, setTdsOn] = useState(false);
  const [tds, setTds] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!vendorId || !scope || !startDate || !endDate) {
      toast.error("Vendor, scope of work, start/end dates required");
      return;
    }
    setSubmitting(true);
    try {
      const proj = projects.find(p => p.id === projectId);
      await api.post("/procurement-extras/service-orders", {
        vendor_id: vendorId,
        project_id: projectId || null, project_code: proj?.code || null,
        service_type: serviceType, scope_of_work: scope,
        rate_basis: rateBasis, rate: Number(rate), quantity: Number(qty), unit,
        start_date: startDate, end_date: endDate,
        gst_percent: Number(gst),
        tds_applicable: tdsOn, tds_percent: Number(tds),
      });
      toast.success("Service order created (draft)");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogContent className="max-w-3xl" data-testid="so-create-dialog">
      <DialogHeader><DialogTitle>New Service Order</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="col-span-2">
          <Label>Vendor *</Label>
          <Select value={vendorId || undefined} onValueChange={setVendorId}>
            <SelectTrigger data-testid="so-vendor"><SelectValue placeholder="— select vendor —" /></SelectTrigger>
            <SelectContent>{vendors.map(v => <SelectItem key={v.id} value={v.id}>{v.vendor_code} · {v.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="col-span-2">
          <Label>Project</Label>
          <Select value={projectId || undefined} onValueChange={setProjectId}>
            <SelectTrigger data-testid="so-project"><SelectValue placeholder="— (optional) —" /></SelectTrigger>
            <SelectContent>{projects.map(p => <SelectItem key={p.id} value={p.id}>{p.code} · {p.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div><Label>Service type</Label><Input value={serviceType} onChange={e => setServiceType(e.target.value)} data-testid="so-service-type" /></div>
        <div>
          <Label>Rate basis</Label>
          <Select value={rateBasis} onValueChange={setRateBasis}>
            <SelectTrigger data-testid="so-rate-basis"><SelectValue /></SelectTrigger>
            <SelectContent>{RATE_BASIS.map(rb => <SelectItem key={rb.v} value={rb.v}>{rb.l}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="col-span-2"><Label>Scope of work *</Label><Textarea value={scope} onChange={e => setScope(e.target.value)} rows={2} data-testid="so-scope" /></div>
        <div><Label>Start *</Label><Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} data-testid="so-start" /></div>
        <div><Label>End *</Label><Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} data-testid="so-end" /></div>
        <div><Label>Rate (₹)</Label><Input type="number" value={rate} onChange={e => setRate(e.target.value)} data-testid="so-rate" /></div>
        <div><Label>Quantity</Label><Input type="number" value={qty} onChange={e => setQty(e.target.value)} data-testid="so-qty" /></div>
        <div><Label>Unit</Label><Input value={unit} onChange={e => setUnit(e.target.value)} /></div>
        <div><Label>GST %</Label><Input type="number" value={gst} onChange={e => setGst(e.target.value)} /></div>
        <div className="col-span-2 flex items-center gap-3 pt-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={tdsOn} onChange={e => setTdsOn(e.target.checked)} /> TDS applicable
          </label>
          {tdsOn && <Input type="number" value={tds} onChange={e => setTds(e.target.value)} className="w-24" placeholder="TDS %" />}
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={submitting} data-testid="so-submit">{submitting ? "Saving…" : "Create"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}

function SRNListDialog({ so }) {
  const [srns, setSrns] = useState([]);
  useEffect(() => {
    api.get(`/procurement-extras/srns?so_id=${so.id}`).then(r => setSrns(r.data || [])).catch(() => {});
  }, [so.id]);

  const downloadPdf = async (s) => {
    try {
      const res = await api.get(`/procurement-extras/srns/${s.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${s.srn_number}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("PDF download failed"); }
  };

  return (
    <DialogContent className="max-w-2xl" data-testid="srn-list-dialog">
      <DialogHeader><DialogTitle>SRNs — {so.so_number} · {so.vendor_name}</DialogTitle></DialogHeader>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-600">
          <tr>
            <th className="px-3 py-2 text-left">SRN #</th>
            <th className="px-3 py-2 text-left">Period</th>
            <th className="px-3 py-2 text-right">Certified Qty</th>
            <th className="px-3 py-2 text-right">Certified Value</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2 text-right">PDF</th>
          </tr>
        </thead>
        <tbody>
          {srns.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">No SRNs recorded</td></tr>}
          {srns.map((s) => (
            <tr key={s.id} className="border-t" data-testid={`srn-row-${s.srn_number}`}>
              <td className="px-3 py-2 font-mono text-xs">{s.srn_number}</td>
              <td className="px-3 py-2 text-xs">{s.service_period_from} → {s.service_period_to}</td>
              <td className="px-3 py-2 text-right">{s.certified_quantity}</td>
              <td className="px-3 py-2 text-right">₹{(s.certified_value || 0).toLocaleString("en-IN")}</td>
              <td className="px-3 py-2"><Badge className={STATUS_TONE[s.status] || "bg-emerald-100 text-emerald-700"}>{s.status || "approved"}</Badge></td>
              <td className="px-3 py-2 text-right">
                <Button size="sm" variant="outline" onClick={() => downloadPdf(s)} data-testid={`srn-pdf-${s.srn_number}`}>
                  <FileDown className="h-3.5 w-3.5" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </DialogContent>
  );
}

function CreateSRNDialog({ so, onClose }) {
  const [from, setFrom] = useState(so.start_date);
  const [to, setTo] = useState(so.end_date);
  const [work, setWork] = useState("");
  const [qty, setQty] = useState(1);
  const [value, setValue] = useState(0);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!work || !value) { toast.error("Work description and certified value required"); return; }
    setSubmitting(true);
    try {
      await api.post("/procurement-extras/srns", {
        so_id: so.id, service_period_from: from, service_period_to: to,
        work_completed: work, certified_quantity: Number(qty),
        certified_value: Number(value), notes,
      });
      toast.success("Service Receipt recorded");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "SRN failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogContent className="max-w-xl" data-testid="srn-create-dialog">
      <DialogHeader><DialogTitle>Record Service Receipt — {so.so_number}</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="col-span-2 text-xs text-slate-600 bg-slate-50 p-2 rounded">
          Vendor: <strong>{so.vendor_name}</strong> · SO Total: ₹{(so.total_amount || 0).toLocaleString("en-IN")} · Received so far: ₹{(so.received_value || 0).toLocaleString("en-IN")}
        </div>
        <div><Label>Period from</Label><Input type="date" value={from} onChange={e => setFrom(e.target.value)} data-testid="srn-from" /></div>
        <div><Label>Period to</Label><Input type="date" value={to} onChange={e => setTo(e.target.value)} data-testid="srn-to" /></div>
        <div className="col-span-2"><Label>Work completed *</Label><Textarea rows={2} value={work} onChange={e => setWork(e.target.value)} data-testid="srn-work" /></div>
        <div><Label>Certified quantity</Label><Input type="number" value={qty} onChange={e => setQty(e.target.value)} data-testid="srn-qty" /></div>
        <div><Label>Certified value (₹) *</Label><Input type="number" value={value} onChange={e => setValue(e.target.value)} data-testid="srn-value" /></div>
        <div className="col-span-2"><Label>Notes</Label><Textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} /></div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={submitting} data-testid="srn-submit">{submitting ? "Saving…" : "Record SRN"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}
