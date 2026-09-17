import { useEffect, useState } from "react";
import { Plus, Truck, CheckCircle2, XCircle, FileText, PackageCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { fmtD } from "@/lib/datetime";

const T_STATUS = {
  pending_approval: ["Pending Approval", "border-amber-300 text-amber-900 bg-amber-50"],
  approved: ["Approved", "border-blue-300 text-blue-900 bg-blue-50"],
  partially_dispatched: ["Partially Dispatched", "border-violet-300 text-violet-900 bg-violet-50"],
  dispatched: ["Dispatched", "border-violet-300 text-violet-900 bg-violet-50"],
  partially_received: ["Partially Received", "border-cyan-300 text-cyan-900 bg-cyan-50"],
  completed: ["Completed", "border-emerald-300 text-emerald-900 bg-emerald-50"],
  rejected: ["Rejected", "border-rose-300 text-rose-900 bg-rose-50"],
};
const C_STATUS = {
  dispatched: ["In Transit", "border-amber-300 text-amber-900 bg-amber-50"],
  received: ["Received", "border-emerald-300 text-emerald-900 bg-emerald-50"],
};
const StatusBadge = ({ map, value }) => (
  <Badge variant="outline" className={`rounded-sm ${(map[value] || [])[1] || ""}`}>{(map[value] || [value])[0]}</Badge>
);
const blankLine = () => ({ item_id: "", quantity: "" });

export function TransfersTab({ bump, locations, items, canWrite, canApprove, onChanged, stockMap = {}, prefill, onPrefillConsumed }) {
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ from_location_id: "", to_location_id: "", need_by: "", remarks: "", lines: [blankLine()] });
  const [challanFor, setChallanFor] = useState(null);

  useEffect(() => {
    if (!prefill?.lines?.length) return;
    setForm({ from_location_id: "", to_location_id: "", need_by: "", remarks: "", lines: prefill.lines.map((l) => ({ ...l })) });
    setCreating(true);
    onPrefillConsumed?.();
  }, [prefill]); // eslint-disable-line

  const load = () => {
    const params = statusFilter ? { status: statusFilter } : {};
    api.get("/scaffolding/transfers", { params }).then((r) => setRows(r.data || [])).catch(() => {});
  };
  useEffect(() => { load(); }, [bump, statusFilter]); // eslint-disable-line

  const setLine = (i, patch) => setForm((f) => ({ ...f, lines: f.lines.map((x, ix) => ix === i ? { ...x, ...patch } : x) }));

  const create = async () => {
    const lines = form.lines.filter((l) => l.item_id && Number(l.quantity) > 0).map((l) => ({ item_id: l.item_id, quantity: Number(l.quantity) }));
    if (!form.from_location_id || !form.to_location_id) { toast.error("Pick From and To locations"); return; }
    if (!lines.length) { toast.error("Enter a quantity for at least one item (lines with 0 are ignored)"); return; }
    try {
      const r = await api.post("/scaffolding/transfers", { ...form, lines });
      toast.success(`Transfer ${r.data.transfer_no} raised — pending Store Manager approval (${lines.length} item line(s))`);
      setCreating(false); setForm({ from_location_id: "", to_location_id: "", need_by: "", remarks: "", lines: [blankLine()] }); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const act = async (t, action) => {
    let remarks = null;
    if (action === "reject") { remarks = window.prompt("Rejection reason?"); if (remarks === null) return; }
    try { await api.post(`/scaffolding/transfers/${t.id}/${action}`, { remarks }); toast.success(action === "approve" ? "Approved — challans can now be created" : "Rejected"); onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Action failed"); }
  };

  const canChallan = (t) => ["approved", "partially_dispatched", "partially_received"].includes(t.status) && canWrite;

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center justify-between p-3 border-b border-border gap-2 flex-wrap">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="scaf-transfer-filter">
          <option value="">All statuses</option>
          {Object.entries(T_STATUS).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}
        </select>
        {canWrite && (
          <Button size="sm" className="h-8 rounded-sm" onClick={() => setCreating(true)} data-testid="scaf-new-transfer">
            <Plus className="h-3.5 w-3.5 mr-1" /> New Transfer Request
          </Button>
        )}
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="text-[10px] uppercase tracking-wider">Transfer # / Date</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">From → To</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Items</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Challans</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
          <TableHead className="text-right"></TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && (
            <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No transfer requests yet.</TableCell></TableRow>
          )}
          {rows.map((t) => (
            <TableRow key={t.id} data-testid={`scaf-transfer-row-${t.id}`}>
              <TableCell>
                <div className="font-mono-data text-xs font-bold">{t.transfer_no}</div>
                <div className="text-[10px] text-muted-foreground">{fmtD(t.created_at)} · {t.created_by}</div>
              </TableCell>
              <TableCell className="text-xs">
                <div className="font-semibold">{t.from_location}</div>
                <div className="text-muted-foreground">→ {t.to_location}</div>
              </TableCell>
              <TableCell className="text-[11px]">
                {(t.lines || []).map((l) => (
                  <div key={l.item_id} className="whitespace-nowrap">
                    {l.item_name} <span className="font-mono-data tabular">×{l.quantity}</span>
                    <span className="text-muted-foreground"> (disp {l.dispatched || 0} · recv {l.received || 0})</span>
                  </div>
                ))}
              </TableCell>
              <TableCell className="text-center font-mono-data tabular text-sm">{t.challan_count || 0}</TableCell>
              <TableCell><StatusBadge map={T_STATUS} value={t.status} /></TableCell>
              <TableCell className="text-right space-x-1 whitespace-nowrap">
                {t.status === "pending_approval" && canApprove && (
                  <>
                    <Button size="sm" className="h-7 rounded-sm" onClick={() => act(t, "approve")} data-testid={`scaf-approve-${t.id}`}>
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive" onClick={() => act(t, "reject")} data-testid={`scaf-reject-${t.id}`}>
                      <XCircle className="h-3.5 w-3.5" />
                    </Button>
                  </>
                )}
                {canChallan(t) && (
                  <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setChallanFor(t)} data-testid={`scaf-challan-btn-${t.id}`}>
                    <Truck className="h-3.5 w-3.5 mr-1" /> Challan
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* New transfer dialog */}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-2xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">New Transfer Request</DialogTitle>
            <DialogDescription>Requires Store Manager / management approval before any dispatch challan can be created.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">From Location *</Label>
              <select value={form.from_location_id} onChange={(e) => setForm({ ...form, from_location_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="scaf-transfer-from">
                <option value="">— select —</option>
                {locations.map((l) => <option key={l.id} value={l.id}>{l.type === "store" ? "🏬" : "🏗"} {l.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">To Location *</Label>
              <select value={form.to_location_id} onChange={(e) => setForm({ ...form, to_location_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="scaf-transfer-to">
                <option value="">— select —</option>
                {locations.filter((l) => l.id !== form.from_location_id).map((l) => <option key={l.id} value={l.id}>{l.type === "store" ? "🏬" : "🏗"} {l.name}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Need By</Label>
              <Input type="date" value={form.need_by} onChange={(e) => setForm({ ...form, need_by: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="scaf-transfer-needby" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
              <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="h-9 rounded-sm mt-1" />
            </div>
            <div className="col-span-2 border border-border rounded-sm">
              <div className="flex items-center justify-between p-2 border-b border-border">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Material Lines</div>
                <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setForm({ ...form, lines: [...form.lines, blankLine()] })} data-testid="scaf-add-line">
                  <Plus className="h-3 w-3 mr-1" /> Add
                </Button>
              </div>
              <div className="p-2 space-y-1.5">
                {form.lines.map((l, i) => {
                  const avl = form.from_location_id && l.item_id ? Number(stockMap[l.item_id]?.[form.from_location_id] || 0) : null;
                  return (
                    <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
                      <select value={l.item_id} onChange={(e) => setLine(i, { item_id: e.target.value })}
                        className="h-8 rounded-sm border border-input bg-background px-2 text-xs col-span-5" data-testid={`scaf-line-item-${i}`}>
                        <option value="">— select item —</option>
                        {items.map((it) => <option key={it.id} value={it.id}>{it.name}{it.size ? ` (${it.size})` : ""} · {it.code}</option>)}
                      </select>
                      <div className="col-span-2 text-[10px] text-right" data-testid={`scaf-line-avl-${i}`}>
                        {avl === null ? <span className="text-muted-foreground">avl —</span>
                          : avl > 0 ? <span className="text-emerald-700 font-bold">avl {avl}</span>
                          : <span className="text-rose-700 font-bold">avl 0</span>}
                      </div>
                      <Input type="number" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} placeholder="Qty (0 = skip)"
                        className="h-8 rounded-sm col-span-3 text-xs tabular" data-testid={`scaf-line-qty-${i}`} />
                      <Button size="sm" variant="ghost" className="h-8 col-span-2 text-destructive"
                        onClick={() => setForm({ ...form, lines: form.lines.filter((_, ix) => ix !== i) })} disabled={form.lines.length === 1}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  );
                })}
                <div className="text-[10px] text-muted-foreground pt-1">Lines with quantity 0 or blank are ignored on submit. "avl" = available at the selected From location.</div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="scaf-transfer-submit">Raise Transfer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ChallanCreateDialog transfer={challanFor} items={items} onClose={() => setChallanFor(null)} onChanged={onChanged} />
    </div>
  );
}

function ChallanCreateDialog({ transfer, items = [], onClose, onChanged }) {
  const [form, setForm] = useState({ vehicle_no: "", driver_name: "", driver_phone: "", transporter: "", eway_bill_no: "", remarks: "",
    customer_wo_no: "", purpose: "returnable_service", origin_address: "", origin_gstin: "", destination_address: "", destination_gstin: "" });
  const [qty, setQty] = useState({});
  const [rates, setRates] = useState({});

  const itemMap = {};
  items.forEach((i) => { itemMap[i.id] = i; });

  useEffect(() => {
    if (!transfer) return;
    const q = {}; const r = {};
    (transfer.lines || []).forEach((l) => {
      q[l.item_id] = Math.max(0, Number(l.quantity) - Number(l.dispatched || 0));
      r[l.item_id] = itemMap[l.item_id]?.rate ?? "";
    });
    setQty(q); setRates(r);
    setForm({ vehicle_no: "", driver_name: "", driver_phone: "", transporter: "", eway_bill_no: "", remarks: "",
      customer_wo_no: "", purpose: "returnable_service", origin_address: "", origin_gstin: "", destination_address: "", destination_gstin: "" });
    Promise.all([
      api.get(`/scaffolding/location-details/${transfer.from_location_id}`),
      api.get(`/scaffolding/location-details/${transfer.to_location_id}`),
    ]).then(([o, d]) => setForm((f) => ({ ...f,
      origin_address: o.data.address || "", origin_gstin: o.data.gstin || "",
      destination_address: d.data.address || "", destination_gstin: d.data.gstin || "" }))).catch(() => {});
  }, [transfer]); // eslint-disable-line

  const totals = (transfer?.lines || []).reduce((acc, l) => {
    const q = Number(qty[l.item_id]) || 0;
    if (q <= 0) return acc;
    const w = Number(itemMap[l.item_id]?.unit_weight_kg || 0);
    const r = Number(rates[l.item_id]) || 0;
    return { qty: acc.qty + q, wkg: acc.wkg + q * w, val: acc.val + q * r };
  }, { qty: 0, wkg: 0, val: 0 });

  const create = async () => {
    if (!form.vehicle_no.trim()) { toast.error("Vehicle number required"); return; }
    const lines = Object.entries(qty).filter(([, v]) => Number(v) > 0)
      .map(([item_id, quantity]) => ({ item_id, quantity: Number(quantity),
        unit_rate: rates[item_id] === "" || rates[item_id] === undefined ? null : Number(rates[item_id]) }));
    if (!lines.length) { toast.error("Enter quantity for at least one item"); return; }
    try {
      const r = await api.post(`/scaffolding/transfers/${transfer.id}/challans`, { ...form, lines });
      toast.success(`Challan ${r.data.challan_no} dispatched — ${r.data.total_qty} pcs · ${r.data.total_weight_kg} kg`);
      onClose(); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <Dialog open={!!transfer} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm max-h-[88vh] overflow-y-auto">
        {transfer && (
          <>
            <DialogHeader>
              <DialogTitle className="font-display">Delivery Challan — {transfer.transfer_no}</DialogTitle>
              <DialogDescription>{transfer.from_location} → {transfer.to_location}. Each challan = one vehicle trip; dispatch deducts source stock. 3 copies printable.</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-3">
              <div className="border border-border rounded-sm p-2 space-y-1.5">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Consignor (Origin)</div>
                <Textarea value={form.origin_address} onChange={(e) => setForm({ ...form, origin_address: e.target.value })}
                  placeholder="Origin full address" className="rounded-sm min-h-[48px] text-xs" data-testid="scaf-challan-origin-addr" />
                <Input value={form.origin_gstin} onChange={(e) => setForm({ ...form, origin_gstin: e.target.value })}
                  placeholder="Origin GSTIN" className="h-8 rounded-sm text-xs" data-testid="scaf-challan-origin-gstin" />
              </div>
              <div className="border border-border rounded-sm p-2 space-y-1.5">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Consignee (Destination)</div>
                <Textarea value={form.destination_address} onChange={(e) => setForm({ ...form, destination_address: e.target.value })}
                  placeholder="Destination full address" className="rounded-sm min-h-[48px] text-xs" data-testid="scaf-challan-dest-addr" />
                <Input value={form.destination_gstin} onChange={(e) => setForm({ ...form, destination_gstin: e.target.value })}
                  placeholder="Destination GSTIN" className="h-8 rounded-sm text-xs" data-testid="scaf-challan-dest-gstin" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Purpose *</Label>
                <select value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="scaf-challan-purpose">
                  <option value="returnable_service">Not for Sale — to render services, on returnable basis</option>
                  <option value="sale">For Sale</option>
                </select>
              </div>
              <div><Label className="text-[10px] uppercase tracking-wider">Customer Work Order No</Label>
                <Input value={form.customer_wo_no} onChange={(e) => setForm({ ...form, customer_wo_no: e.target.value })} placeholder="WO/2026/…" className="h-9 rounded-sm mt-1" data-testid="scaf-challan-wo" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Vehicle No *</Label>
                <Input value={form.vehicle_no} onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} placeholder="MH-04-AB-1234" className="h-9 rounded-sm mt-1" data-testid="scaf-challan-vehicle" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Transporter</Label>
                <Input value={form.transporter} onChange={(e) => setForm({ ...form, transporter: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="scaf-challan-transporter" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Driver Name</Label>
                <Input value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="scaf-challan-driver" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Driver Phone</Label>
                <Input value={form.driver_phone} onChange={(e) => setForm({ ...form, driver_phone: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">E-Way Bill No</Label>
                <Input value={form.eway_bill_no} onChange={(e) => setForm({ ...form, eway_bill_no: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="scaf-challan-eway" /></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Remarks</Label>
                <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
              <div className="col-span-2 border border-border rounded-sm">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary p-2 border-b border-border">Load on this vehicle</div>
                <div className="p-2 space-y-1.5">
                  <div className="grid grid-cols-12 gap-1.5 text-[9px] uppercase tracking-wider text-muted-foreground">
                    <div className="col-span-5">Item</div><div className="col-span-2 text-right">Qty</div>
                    <div className="col-span-2 text-right">Unit Price ₹</div><div className="col-span-3 text-right">Wt (kg) / Value</div>
                  </div>
                  {(transfer.lines || []).map((l) => {
                    const remaining = Math.max(0, Number(l.quantity) - Number(l.dispatched || 0));
                    const q = Number(qty[l.item_id]) || 0;
                    const w = Number(itemMap[l.item_id]?.unit_weight_kg || 0);
                    const r = Number(rates[l.item_id]) || 0;
                    return (
                      <div key={l.item_id} className="grid grid-cols-12 gap-1.5 items-center">
                        <div className="col-span-5 text-xs">{l.item_name} <span className="text-muted-foreground">(rem {remaining} {l.unit}{w ? ` · ${w} kg/u` : ""})</span></div>
                        <Input type="number" value={qty[l.item_id] ?? ""} max={remaining} min={0}
                          onChange={(e) => setQty({ ...qty, [l.item_id]: e.target.value })}
                          className="h-8 rounded-sm col-span-2 text-xs tabular" disabled={remaining <= 0}
                          data-testid={`scaf-challan-qty-${l.item_id}`} />
                        <Input type="number" value={rates[l.item_id] ?? ""} min={0}
                          onChange={(e) => setRates({ ...rates, [l.item_id]: e.target.value })}
                          className="h-8 rounded-sm col-span-2 text-xs tabular" placeholder="Rate"
                          data-testid={`scaf-challan-rate-${l.item_id}`} />
                        <div className="col-span-3 text-right text-[11px] font-mono-data tabular">
                          {q > 0 ? `${(q * w).toFixed(1)} kg · ₹${(q * r).toLocaleString("en-IN")}` : "—"}
                        </div>
                      </div>
                    );
                  })}
                  <div className="flex justify-end gap-4 text-xs font-bold border-t border-border pt-1.5" data-testid="scaf-challan-totals">
                    <span>Total Qty: <span className="font-mono-data tabular">{totals.qty}</span></span>
                    <span>Total Wt: <span className="font-mono-data tabular">{totals.wkg.toFixed(1)} kg ({(totals.wkg / 1000).toFixed(3)} MT)</span></span>
                    <span>Total Value: <span className="font-mono-data tabular">₹ {totals.val.toLocaleString("en-IN")}</span></span>
                  </div>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
              <Button className="rounded-sm" onClick={create} data-testid="scaf-challan-submit"><Truck className="h-4 w-4 mr-1.5" /> Dispatch Challan</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ChallansTab({ bump, canWrite, onChanged, locations = [] }) {
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [locFilter, setLocFilter] = useState("");
  const [receiving, setReceiving] = useState(null);
  const [receiverName, setReceiverName] = useState("");

  useEffect(() => {
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (locFilter) params.location_id = locFilter;
    api.get("/scaffolding/challans", { params }).then((r) => setRows(r.data || [])).catch(() => {});
  }, [bump, statusFilter, locFilter]);

  const openPdf = async (c) => {
    try {
      const { data } = await api.get(`/scaffolding/challans/${c.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch { toast.error("PDF failed"); }
  };

  const receive = async () => {
    try {
      await api.post(`/scaffolding/challans/${receiving.id}/receive`, { receiver_name: receiverName || null });
      toast.success(`Material received at ${receiving.to_location} — stock updated`);
      setReceiving(null); setReceiverName(""); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="scaf-challan-filter">
          <option value="">All statuses</option>
          <option value="dispatched">In Transit</option>
          <option value="received">Received</option>
        </select>
        <select value={locFilter} onChange={(e) => setLocFilter(e.target.value)}
          className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="scaf-challan-loc-filter">
          <option value="">All projects / locations</option>
          {locations.filter((l) => l.type === "project").map((l) => <option key={l.id} value={l.id}>🏗 {l.name}</option>)}
          {locations.filter((l) => l.type === "store").map((l) => <option key={l.id} value={l.id}>🏬 {l.name}</option>)}
        </select>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="text-[10px] uppercase tracking-wider">Challan # / Date</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Route</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Vehicle / Driver</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Items</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
          <TableHead className="text-right"></TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && (
            <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">No challans yet. Approve a transfer, then create a challan against it.</TableCell></TableRow>
          )}
          {rows.map((c) => (
            <TableRow key={c.id} data-testid={`scaf-challan-row-${c.id}`}>
              <TableCell>
                <div className="font-mono-data text-xs font-bold">{c.challan_no}</div>
                {c.in_challan_no && <div className="text-[10px] font-mono-data text-emerald-700">IN: {c.in_challan_no}</div>}
                <div className="text-[10px] text-muted-foreground">{fmtD(c.dispatched_at)} · vs {c.transfer_no}</div>
              </TableCell>
              <TableCell className="text-xs">
                <div className="font-semibold">{c.from_location}</div>
                <div className="text-muted-foreground">→ {c.to_location}</div>
              </TableCell>
              <TableCell className="text-xs">
                <div className="font-mono-data font-bold">{c.vehicle_no}</div>
                <div className="text-muted-foreground">{c.driver_name || "—"}{c.driver_phone ? ` · ${c.driver_phone}` : ""}</div>
              </TableCell>
              <TableCell className="text-[11px]">
                {(c.lines || []).map((l) => <div key={l.item_id} className="whitespace-nowrap">{l.item_name} <span className="font-mono-data tabular">×{l.quantity}</span></div>)}
                {(c.total_weight_kg || c.total_value) ? (
                  <div className="text-[10px] text-muted-foreground font-mono-data mt-0.5">
                    {c.total_qty} pcs{c.total_weight_kg ? ` · ${c.total_weight_kg} kg` : ""}{c.total_value ? ` · ₹${Number(c.total_value).toLocaleString("en-IN")}` : ""}
                  </div>
                ) : null}
              </TableCell>
              <TableCell>
                <StatusBadge map={C_STATUS} value={c.status} />
                {c.status === "received" && <div className="text-[10px] text-muted-foreground mt-0.5">by {c.receiver_name || c.received_by}</div>}
              </TableCell>
              <TableCell className="text-right space-x-1 whitespace-nowrap">
                <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openPdf(c)} data-testid={`scaf-pdf-${c.id}`}>
                  <FileText className="h-3.5 w-3.5 mr-1" /> PDF
                </Button>
                {c.status === "dispatched" && canWrite && (
                  <Button size="sm" className="h-7 rounded-sm" onClick={() => setReceiving(c)} data-testid={`scaf-receive-${c.id}`}>
                    <PackageCheck className="h-3.5 w-3.5 mr-1" /> Receive
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={!!receiving} onOpenChange={(o) => !o && setReceiving(null)}>
        <DialogContent className="max-w-sm rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Receive {receiving?.challan_no}</DialogTitle>
            <DialogDescription>Lands the material at {receiving?.to_location} and credits stock there.</DialogDescription>
          </DialogHeader>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Receiver Name</Label>
            <Input value={receiverName} onChange={(e) => setReceiverName(e.target.value)} placeholder="Site supervisor name" className="h-9 rounded-sm mt-1" data-testid="scaf-receive-name" />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setReceiving(null)}>Cancel</Button>
            <Button className="rounded-sm" onClick={receive} data-testid="scaf-receive-submit"><PackageCheck className="h-4 w-4 mr-1.5" /> Confirm Receipt</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
