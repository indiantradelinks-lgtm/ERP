import { useEffect, useMemo, useState } from "react";
import { Plus, Search, PackageCheck, Trash2, AlertTriangle, Network, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import LineageTrail from "@/components/LineageTrail";
import { api } from "@/lib/api";
import { downloadPdf } from "@/lib/exports";
import { toast } from "sonner";

const STATUS_TONE = { pending_inspection: "warning", approved: "success", rejected: "danger", partial_accepted: "info" };

export default function Grn() {
  const [rows, setRows] = useState([]);
  const [pos, setPos] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [lineageFor, setLineageFor] = useState(null);

  const load = async () => {
    try {
      const [g, p] = await Promise.all([
        api.get("/procurement/grns"),
        api.get("/purchase-orders"),
      ]);
      setRows(g.data || []);
      // Open POs only — exclude received & cancelled
      setPos((p.data || []).filter((po) => !["received", "cancelled"].includes(po.status)));
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  const remove = async (g) => {
    if (!window.confirm(`Delete ${g.grn_number}? This reverses the inventory inward.`)) return;
    try { await api.delete(`/procurement/grns/${g.id}`); toast.success("Reversed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.grn_number, r.po_number, r.vendor_name, r.store_location, r.status].some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="grn-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <PackageCheck className="h-3 w-3" /> Procurement · Inward
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Goods Receipt Notes</h1>
        <p className="text-sm text-muted-foreground mt-1">Record material inward against a Purchase Order. Accepted lines automatically inward into inventory.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search GRN #, PO #, vendor…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="grn-search" />
          </div>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => setOpen(true)} data-testid="grn-add">
              <Plus className="h-4 w-4 mr-1" /> New GRN
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">GRN #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">PO #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Store</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Accepted / Rej</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10 text-sm">No GRNs yet.</TableCell></TableRow>}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`grn-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm font-bold">{r.grn_number}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.po_number}</TableCell>
                  <TableCell className="text-sm">{r.vendor_name}</TableCell>
                  <TableCell className="text-xs">{r.store_location || "—"}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.received_at}</TableCell>
                  <TableCell className="text-xs">
                    <span className="text-success font-bold">{r.total_accepted ?? 0}</span> / <span className="text-destructive">{r.total_rejected ?? 0}</span>
                  </TableCell>
                  <TableCell><StatusBadge text={(r.status || "").replaceAll("_", " ")} tone={STATUS_TONE[r.status] || "neutral"} /></TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1 items-center">
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(r)} data-testid={`grn-lineage-${r.id}`} title="View end-to-end procurement lineage">
                        <Network className="h-3 w-3 mr-1" /> Lineage
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/grns/${r.id}/pdf`, `${r.grn_number || r.id}.pdf`)} data-testid={`grn-pdf-${r.id}`} title="Download GRN PDF">
                        <FileDown className="h-3 w-3 mr-1" /> PDF
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => remove(r)} data-testid={`grn-delete-${r.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {open && <GrnDialog pos={pos} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); load(); }} />}

      <Dialog open={!!lineageFor} onOpenChange={(o) => !o && setLineageFor(null)}>
        <DialogContent className="max-w-5xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Procurement Lineage — {lineageFor?.grn_number}</DialogTitle>
            <DialogDescription>The originating PR → RFQ → PO chain that resulted in this receipt.</DialogDescription>
          </DialogHeader>
          {lineageFor && <LineageTrail kind="grn" recordId={lineageFor.id} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GrnDialog({ pos, onClose, onSaved }) {
  const [poId, setPoId] = useState("");
  const [store, setStore] = useState("Main Store");
  const [receivedAt, setReceivedAt] = useState(new Date().toISOString().slice(0, 10));
  const [remarks, setRemarks] = useState("");
  const [lines, setLines] = useState([]);

  useEffect(() => {
    if (!poId) { setLines([]); return; }
    const po = pos.find((p) => p.id === poId);
    if (!po) { setLines([]); return; }
    const items = po.items || [];
    setLines(items.map((it, idx) => ({
      po_item_index: idx,
      item_id: it.item_id || it.id || null,
      item_name: it.name || it.item_name || `Item ${idx + 1}`,
      ordered_qty: Number(it.quantity || 0),
      received_qty: Number(it.quantity || 0),
      accepted_qty: Number(it.quantity || 0),
      rejected_qty: 0,
      unit: it.unit || "Nos",
      inspection_status: "approved",
      damage_notes: "",
      batch: "",
    })));
  }, [poId, pos]);

  const update = (i, k, v) => setLines((ls) => ls.map((l, ix) => ix === i ? { ...l, [k]: v } : l));

  const save = async () => {
    if (!poId) { toast.error("Pick a PO"); return; }
    if (!lines.length) { toast.error("Selected PO has no items"); return; }
    try {
      const payload = {
        po_id: poId, store_location: store, received_at: receivedAt, remarks,
        items: lines.map((l) => ({
          po_item_index: l.po_item_index,
          item_id: l.item_id || undefined,
          item_name: l.item_name,
          ordered_qty: Number(l.ordered_qty) || 0,
          received_qty: Number(l.received_qty) || 0,
          accepted_qty: Number(l.accepted_qty) || 0,
          rejected_qty: Number(l.rejected_qty) || 0,
          unit: l.unit || "Nos",
          inspection_status: l.inspection_status || "approved",
          damage_notes: l.damage_notes || undefined,
          batch: l.batch || undefined,
        })),
      };
      const { data } = await api.post("/procurement/grns", payload);
      toast.success(`${data.grn_number} created · ${data.status.replaceAll("_", " ")}`);
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">New GRN</DialogTitle>
          <DialogDescription className="sr-only">Record material received against a PO line by line.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 py-2">
          <div className="md:col-span-2">
            <Label className="text-xs uppercase tracking-wider">PO</Label>
            <select value={poId} onChange={(e) => setPoId(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="grn-po-select">
              <option value="">— pick a PO —</option>
              {pos.map((p) => <option key={p.id} value={p.id}>{p.po_number} · {p.vendor || p.vendor_name} · ₹ {Number(p.amount || 0).toLocaleString("en-IN")}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Store</Label>
            <Input value={store} onChange={(e) => setStore(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="grn-store" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Received On</Label>
            <Input type="date" value={receivedAt} onChange={(e) => setReceivedAt(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="grn-date" />
          </div>
        </div>

        {lines.length > 0 && (
          <div className="border border-border rounded-sm overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Ordered</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Received</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Accepted</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Rejected</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Inspection</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Batch</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.map((l, i) => (
                  <TableRow key={i} data-testid={`grn-line-${i}`}>
                    <TableCell className="text-sm font-semibold">{l.item_name}<div className="text-[10px] text-muted-foreground">{l.unit}</div></TableCell>
                    <TableCell className="text-sm tabular">{l.ordered_qty}</TableCell>
                    <TableCell><Input type="number" value={l.received_qty} onChange={(e) => update(i, "received_qty", e.target.value)} className="h-8 w-20 rounded-sm" /></TableCell>
                    <TableCell><Input type="number" value={l.accepted_qty} onChange={(e) => update(i, "accepted_qty", e.target.value)} className="h-8 w-20 rounded-sm" /></TableCell>
                    <TableCell><Input type="number" value={l.rejected_qty} onChange={(e) => update(i, "rejected_qty", e.target.value)} className="h-8 w-20 rounded-sm" /></TableCell>
                    <TableCell>
                      <select value={l.inspection_status} onChange={(e) => update(i, "inspection_status", e.target.value)} className="h-8 rounded-sm border border-input bg-background px-2 text-xs">
                        <option value="approved">approved</option>
                        <option value="partial_accepted">partial</option>
                        <option value="rejected">rejected</option>
                      </select>
                    </TableCell>
                    <TableCell><Input value={l.batch} onChange={(e) => update(i, "batch", e.target.value)} className="h-8 w-24 rounded-sm" placeholder="optional" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {lines.length === 0 && poId && (
          <div className="text-sm text-warning flex items-center gap-2 p-3 border border-warning/30 bg-warning/10 rounded-sm">
            <AlertTriangle className="h-4 w-4" /> Selected PO has no line items.
          </div>
        )}

        <div className="mt-3">
          <Label className="text-xs uppercase tracking-wider">Remarks</Label>
          <textarea className="w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm mt-1" value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="grn-remarks" />
        </div>

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={save} data-testid="grn-save">Save GRN</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
