import { useEffect, useState } from "react";
import { ScanLine, ArrowDownToLine, ArrowUpFromLine, Repeat, Undo2, AlertTriangle, Search, Camera, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import BarcodeScanner from "@/components/BarcodeScanner";
import { api } from "@/lib/api";
import { downloadPdf } from "@/lib/exports";
import { toast } from "sonner";

const TYPE_META = {
  inward: { tone: "success", icon: ArrowDownToLine, label: "Inward" },
  outward: { tone: "warning", icon: ArrowUpFromLine, label: "Outward" },
  transfer: { tone: "info", icon: Repeat, label: "Transfer" },
  return: { tone: "primary", icon: Undo2, label: "Return" },
  scrap: { tone: "danger", icon: AlertTriangle, label: "Scrap" },
};

export default function StoreTransactions() {
  const [txns, setTxns] = useState([]);
  const [open, setOpen] = useState(false);
  const [scanCode, setScanCode] = useState("");
  const [item, setItem] = useState(null);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [form, setForm] = useState({ txn_type: "inward", quantity: 1, project: "", to_location: "", from_location: "", received_from: "", issued_to: "", note: "" });
  const [filter, setFilter] = useState({ q: "", type: "" });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.type) params.set("txn_type", filter.type);
      params.set("limit", "200");
      const { data } = await api.get(`/store/transactions?${params.toString()}`);
      setTxns(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load");
    }
  };
  useEffect(() => { load(); }, [filter.type]);

  const lookup = async (codeOverride) => {
    const code = (codeOverride ?? scanCode).trim();
    if (!code) return;
    try {
      const { data } = await api.get(`/store/lookup/${encodeURIComponent(code)}`);
      setItem(data);
      setScanCode(code);
      toast.success(`Found: ${data.name || data.title}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Not found");
      setItem(null);
    }
  };

  const onCameraDetected = (code) => {
    setScannerOpen(false);
    lookup(code);
  };

  const submit = async () => {
    if (!item) { toast.error("Scan or lookup an inventory item first"); return; }
    try {
      const payload = { ...form, item_id: item.id, quantity: Number(form.quantity) };
      const { data } = await api.post("/store/transactions", payload);
      toast.success(data.status === "awaiting_approval" ? `Created ${data.txn_no} — awaiting approval` : `Posted ${data.txn_no}`);
      setOpen(false);
      setItem(null);
      setScanCode("");
      setForm({ txn_type: "inward", quantity: 1, project: "", to_location: "", from_location: "", received_from: "", issued_to: "", note: "" });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const filtered = txns.filter((t) => !filter.q || [t.txn_no, t.item_name, t.item_sku, t.project, t.issued_to, t.received_from].some((v) => String(v ?? "").toLowerCase().includes(filter.q.toLowerCase())));

  return (
    <div className="space-y-6" data-testid="store-transactions-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Stores · Movement Ledger</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Inventory Transactions</h1>
        <p className="text-sm text-muted-foreground mt-1">Inward · Outward · Transfer · Return · Scrap. Outward issues above the per-item threshold auto-trigger an approval.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} data-testid="store-txns-search" />
          </div>
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm" value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })} data-testid="store-txns-filter">
            <option value="">All types</option>
            {Object.keys(TYPE_META).map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
          </select>
          <div className="ml-auto">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="h-9 rounded-sm" data-testid="store-txns-add"><ScanLine className="h-4 w-4 mr-1.5" /> New Movement</Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg rounded-sm">
                <DialogHeader>
                  <DialogTitle className="font-display flex items-center gap-2"><ScanLine className="h-4 w-4 text-primary" /> Stock Movement</DialogTitle>
                  <DialogDescription className="sr-only">Scan a barcode or enter SKU, then post the inventory transaction.</DialogDescription>
                </DialogHeader>
                <div className="space-y-3 py-2">
                  <div>
                    <Label className="text-xs uppercase tracking-wider">Barcode / SKU / Item ID</Label>
                    <div className="flex gap-2 mt-1.5">
                      <Input autoFocus value={scanCode} onChange={(e) => setScanCode(e.target.value)} onKeyDown={(e) => e.key === "Enter" && lookup()} className="h-9 rounded-sm flex-1 font-mono-data" placeholder="Scan or type…" data-testid="store-txns-scan" />
                      <Button variant="outline" className="h-9 rounded-sm" onClick={() => setScannerOpen(true)} data-testid="store-txns-camera" title="Scan with camera">
                        <Camera className="h-4 w-4" />
                      </Button>
                      <Button className="h-9 rounded-sm" onClick={() => lookup()} data-testid="store-txns-lookup">Lookup</Button>
                    </div>
                  </div>
                  {item && (
                    <div className="p-3 bg-primary/5 border border-primary/20 rounded-sm text-sm" data-testid="store-txns-resolved-item">
                      <div className="font-semibold">{item.name || item.title}</div>
                      <div className="text-xs text-muted-foreground">SKU: {item.sku || "—"} · Current stock: <span className="font-mono-data text-foreground">{item.quantity ?? 0}</span> {item.unit || ""}</div>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs uppercase tracking-wider">Type</Label>
                      <select className="h-9 mt-1.5 w-full rounded-sm border border-input bg-background px-2 text-sm" value={form.txn_type} onChange={(e) => setForm({ ...form, txn_type: e.target.value })} data-testid="store-txns-field-type">
                        {Object.keys(TYPE_META).map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
                      </select>
                    </div>
                    <div>
                      <Label className="text-xs uppercase tracking-wider">Quantity</Label>
                      <Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="h-9 rounded-sm mt-1.5" data-testid="store-txns-field-qty" />
                    </div>
                    {form.txn_type === "inward" && (
                      <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Received From (Vendor)</Label><Input value={form.received_from} onChange={(e) => setForm({ ...form, received_from: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                    )}
                    {form.txn_type === "outward" && (
                      <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Issued To</Label><Input value={form.issued_to} onChange={(e) => setForm({ ...form, issued_to: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                    )}
                    {form.txn_type === "transfer" && (
                      <>
                        <div><Label className="text-xs uppercase tracking-wider">From</Label><Input value={form.from_location} onChange={(e) => setForm({ ...form, from_location: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                        <div><Label className="text-xs uppercase tracking-wider">To</Label><Input value={form.to_location} onChange={(e) => setForm({ ...form, to_location: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                      </>
                    )}
                    <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Project / Note</Label><Input value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                    <div className="col-span-2"><Label className="text-xs uppercase tracking-wider">Note</Label><Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className="h-9 rounded-sm mt-1.5" /></div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
                  <Button className="rounded-sm" onClick={submit} disabled={!item} data-testid="store-txns-post">Post movement</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">Txn #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Type</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Balance</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Counterparty</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider text-right">PDF</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-10">No movements yet.</TableCell></TableRow>
              )}
              {filtered.map((t) => {
                const meta = TYPE_META[t.txn_type] || { tone: "neutral", label: t.txn_type };
                return (
                  <TableRow key={t.id} data-testid={`txn-row-${t.id}`} className="hover:bg-muted/30">
                    <TableCell className="font-mono-data text-xs">{t.txn_no}</TableCell>
                    <TableCell><StatusBadge text={meta.label} tone={meta.tone} /></TableCell>
                    <TableCell className="text-sm">{t.item_name}<div className="text-[11px] text-muted-foreground font-mono-data">{t.item_sku || ""}</div></TableCell>
                    <TableCell className={"text-sm tabular " + (t.delta < 0 ? "text-destructive" : "text-success")}>{t.delta > 0 ? "+" : ""}{t.delta}</TableCell>
                    <TableCell className="text-sm tabular">{t.balance_after}</TableCell>
                    <TableCell className="text-sm">{t.issued_to || t.received_from || t.to_location || t.project || "—"}</TableCell>
                    <TableCell><StatusBadge text={t.status} tone={t.status === "posted" ? "success" : "warning"} /></TableCell>
                    <TableCell className="font-mono-data text-xs">{(t.created_at || "").slice(0, 19).replace("T", " ")}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/store/transactions/${t.id}/pdf`, `${t.txn_no || t.id}.pdf`)} data-testid={`txn-pdf-${t.id}`} title="Material Issue / Receipt slip">
                        <FileDown className="h-3 w-3" />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
      <BarcodeScanner open={scannerOpen} onOpenChange={setScannerOpen} onDetected={onCameraDetected} />
    </div>
  );
}
