import { useEffect, useState } from "react";
import { Store, FileText, Upload, Star, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { toneFor } from "@/lib/statusTone";

const VP_STATUS_TONE = { approved: "success", rejected: "danger" };

export default function VendorPortal() {
  const [me, setMe] = useState(null);
  const [rfqs, setRfqs] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [evals, setEvals] = useState([]);
  const [invOpen, setInvOpen] = useState(false);
  const [form, setForm] = useState({ po_no: "", invoice_no: "", date: new Date().toISOString().slice(0, 10), amount: 0, description: "" });

  const load = async () => {
    try {
      const m = await api.get("/vendor-portal/me");
      setMe(m.data);
      const [r, i, e] = await Promise.all([
        api.get("/vendor-portal/rfqs"),
        api.get("/vendor-portal/invoices"),
        api.get(`/vendor-portal/evaluations/${m.data.id}`),
      ]);
      setRfqs(r.data);
      setInvoices(i.data);
      setEvals(e.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load vendor portal");
    }
  };
  useEffect(() => { load(); }, []);

  const submitInvoice = async () => {
    try {
      const { data } = await api.post("/vendor-portal/invoices", { ...form, amount: Number(form.amount) || 0 });
      toast.success(`Invoice ${data.submission_no} submitted`);
      setInvOpen(false);
      setForm({ po_no: "", invoice_no: "", date: new Date().toISOString().slice(0, 10), amount: 0, description: "" });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Submit failed");
    }
  };

  if (!me) {
    return <div className="text-sm text-muted-foreground" data-testid="vendor-portal-loading">Loading vendor portal…</div>;
  }

  const avgRating = me.rating || 0;
  return (
    <div className="space-y-8" data-testid="vendor-portal">
      <div className="flex flex-col lg:flex-row lg:items-end gap-4 justify-between">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Store className="h-3 w-3" /> Vendor Portal
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">{me.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">GST: <span className="font-mono-data">{me.gst || "—"}</span> · PAN: <span className="font-mono-data">{me.pan || "—"}</span></p>
        </div>
        <div className="flex items-center gap-2">
          <div className="bg-card border border-border rounded-sm px-4 py-2 text-center">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Avg Rating</div>
            <div className="font-display font-black text-2xl tabular flex items-center gap-1 justify-center"><Star className="h-4 w-4 text-warning fill-warning" />{avgRating.toFixed(2)}</div>
          </div>
          <div className="bg-card border border-border rounded-sm px-4 py-2 text-center">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Reviews</div>
            <div className="font-display font-black text-2xl tabular">{me.rating_count || 0}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <KPI label="Open RFQs / POs" value={rfqs.length} icon={ShoppingCart} />
        <KPI label="Submitted Invoices" value={invoices.length} icon={Upload} />
        <KPI label="Evaluations Received" value={evals.length} icon={Star} />
      </div>

      {/* RFQ list */}
      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <h2 className="font-display font-bold text-lg flex items-center gap-2"><ShoppingCart className="h-4 w-4 text-primary" /> Purchase Orders / RFQs</h2>
            <p className="text-xs text-muted-foreground">Orders the buyer has addressed to you.</p>
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">PO #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Total</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rfqs.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-8">No orders found.</TableCell></TableRow>}
            {rfqs.map((po) => (
              <TableRow key={po.id} className="hover:bg-muted/30" data-testid={`vp-rfq-${po.id}`}>
                <TableCell className="font-mono-data text-sm">{po.po_no || po.id?.slice(0, 8)}</TableCell>
                <TableCell className="text-sm">{po.date || ""}</TableCell>
                <TableCell className="text-sm">{po.project || "—"}</TableCell>
                <TableCell className="text-sm tabular">₹ {Number(po.total || 0).toLocaleString("en-IN")}</TableCell>
                <TableCell><StatusBadge text={po.status || "issued"} tone={toneFor(VP_STATUS_TONE, po.status, "info")} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Invoices */}
      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <h2 className="font-display font-bold text-lg flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> My Invoices</h2>
            <p className="text-xs text-muted-foreground">Submit invoices against your purchase orders.</p>
          </div>
          <Dialog open={invOpen} onOpenChange={setInvOpen}>
            <DialogTrigger asChild>
              <Button className="h-9 rounded-sm" data-testid="vp-invoice-add"><Upload className="h-4 w-4 mr-1.5" /> Submit Invoice</Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg rounded-sm">
              <DialogHeader>
                <DialogTitle className="font-display">Submit Invoice</DialogTitle>
                <DialogDescription className="sr-only">Send a new invoice against one of your purchase orders.</DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">PO Number</Label><Input value={form.po_no} onChange={(e) => setForm({ ...form, po_no: e.target.value })} className="h-9 rounded-sm mt-1.5 font-mono-data" data-testid="vp-field-po_no" /></div>
                <div><Label className="text-xs uppercase tracking-wider">Invoice #</Label><Input value={form.invoice_no} onChange={(e) => setForm({ ...form, invoice_no: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="vp-field-invoice_no" /></div>
                <div><Label className="text-xs uppercase tracking-wider">Date</Label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="vp-field-date" /></div>
                <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Amount (INR)</Label><Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="vp-field-amount" /></div>
                <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Description</Label><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm mt-1.5" data-testid="vp-field-description" /></div>
              </div>
              <DialogFooter>
                <Button variant="outline" className="rounded-sm" onClick={() => setInvOpen(false)}>Cancel</Button>
                <Button className="rounded-sm" onClick={submitInvoice} data-testid="vp-invoice-submit">Submit</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Submission #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">PO #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Invoice #</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Amount</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {invoices.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">No invoices submitted.</TableCell></TableRow>}
            {invoices.map((inv) => (
              <TableRow key={inv.id} className="hover:bg-muted/30" data-testid={`vp-invoice-${inv.id}`}>
                <TableCell className="font-mono-data text-sm">{inv.submission_no}</TableCell>
                <TableCell className="font-mono-data text-xs">{inv.po_no || "—"}</TableCell>
                <TableCell className="text-sm">{inv.invoice_no}</TableCell>
                <TableCell className="text-sm">{inv.date}</TableCell>
                <TableCell className="text-sm tabular">₹ {Number(inv.amount || 0).toLocaleString("en-IN")}</TableCell>
                <TableCell><StatusBadge text={inv.status} tone={toneFor(VP_STATUS_TONE, inv.status, "info")} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Evaluations */}
      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border">
          <h2 className="font-display font-bold text-lg flex items-center gap-2"><Star className="h-4 w-4 text-warning" /> Recent Evaluations</h2>
          <p className="text-xs text-muted-foreground">Buyer-issued performance ratings.</p>
        </div>
        <ul className="divide-y divide-border">
          {evals.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted-foreground">No evaluations yet.</li>}
          {evals.map((e) => (
            <li key={e.id} className="p-3 flex items-center gap-3 text-sm" data-testid={`vp-eval-${e.id}`}>
              <div className="font-display font-black text-xl tabular w-12 text-center">{Number(e.rating || 0).toFixed(1)}</div>
              <div className="flex-1">
                <div className="font-semibold">{e.period}</div>
                <div className="text-[11px] text-muted-foreground">{e.rated_by} · {(e.created_at || "").slice(0, 10)}</div>
                {e.note && <div className="text-xs mt-1">"{e.note}"</div>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function KPI({ label, value, icon: Icon }) {
  return (
    <div className="bg-card border border-border rounded-sm p-4 flex items-center gap-3">
      <div className="h-10 w-10 grid place-items-center rounded-sm bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div>
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className="font-display font-black text-3xl tabular">{value}</div>
      </div>
    </div>
  );
}
