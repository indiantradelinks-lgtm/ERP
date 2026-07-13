import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Truck, QrCode, Trash2, CheckSquare, Eye, X } from "lucide-react";
import { QRCodeCanvas } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const TYPE_LABEL = { delivery: "Delivery", return: "Return", inter_site_transfer: "Inter-site", vendor_return: "Vendor Return" };
const TYPE_TONE = { delivery: "primary", return: "warning", inter_site_transfer: "info", vendor_return: "danger" };
const STATUS_TONE = { draft: "neutral", dispatched: "info", in_transit: "warning", received: "success", cancelled: "danger" };

const blankForm = () => ({
  type: "delivery", from_location: "", to_location: "", vehicle_no: "", driver_name: "", driver_phone: "",
  transporter: "", eway_bill_no: "", dispatch_at: new Date().toISOString().slice(0, 10),
  items: [{ name: "", quantity: 1, unit: "Nos", serial_no: "", batch: "" }],
  remarks: "",
});

export default function Challans() {
  const [rows, setRows] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [view, setView] = useState(null);
  const [receive, setReceive] = useState(null);

  const load = async () => {
    try {
      const url = typeFilter ? `/challans?type=${typeFilter}` : "/challans";
      const { data } = await api.get(url);
      setRows(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [typeFilter]);

  const save = async () => {
    if (!form.items.length || !form.items[0].name) { toast.error("Add at least one item"); return; }
    try {
      const payload = { ...form, items: form.items.map((i) => ({ ...i, quantity: Number(i.quantity) || 0 })) };
      const { data } = await api.post("/challans", payload);
      toast.success(`${data.challan_no} created`);
      setOpen(false);
      setForm(blankForm());
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.challan_no}?`)) return;
    try { await api.delete(`/challans/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.challan_no, r.from_location, r.to_location, r.vehicle_no, r.driver_name, r.status]
      .some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  const addItem = () => setForm({ ...form, items: [...form.items, { name: "", quantity: 1, unit: "Nos", serial_no: "", batch: "" }] });
  const updItem = (idx, k, v) => setForm({ ...form, items: form.items.map((it, i) => i === idx ? { ...it, [k]: v } : it) });
  const rmItem = (idx) => setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });

  return (
    <div className="space-y-6" data-testid="challans-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Truck className="h-3 w-3" /> Procurement · Challans
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Delivery & Transfer Challans</h1>
        <p className="text-sm text-muted-foreground mt-1">Delivery, Return, Inter-site Transfer and Vendor Return challans with QR code + receiver e-signature.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search Challan #, vehicle, driver…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="challans-search" />
          </div>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-xs" data-testid="challans-type-filter">
            <option value="">All types</option>
            <option value="delivery">Delivery</option>
            <option value="return">Return</option>
            <option value="inter_site_transfer">Inter-site Transfer</option>
            <option value="vendor_return">Vendor Return</option>
          </select>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => setOpen(true)} data-testid="challans-add">
              <Plus className="h-4 w-4 mr-1" /> New Challan
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">Challan #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Type</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">From → To</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Vehicle · Driver</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Items</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-right w-44">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-10 text-sm">No challans yet.</TableCell></TableRow>}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`challan-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm font-bold">{r.challan_no}</TableCell>
                  <TableCell><StatusBadge text={TYPE_LABEL[r.type] || r.type} tone={TYPE_TONE[r.type] || "neutral"} /></TableCell>
                  <TableCell className="text-xs">{r.from_location || "—"} → <span className="text-primary font-semibold">{r.to_location || "—"}</span></TableCell>
                  <TableCell className="text-xs">{r.vehicle_no || "—"}<div className="text-[10px] text-muted-foreground">{r.driver_name || ""}</div></TableCell>
                  <TableCell className="text-xs">{(r.items || []).length}</TableCell>
                  <TableCell><StatusBadge text={(r.status || "").replaceAll("_", " ")} tone={STATUS_TONE[r.status] || "neutral"} />{r.e_signature && <div className="text-[10px] text-success">✓ signed</div>}</TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setView(r)} data-testid={`challan-view-${r.id}`}><Eye className="h-3 w-3" /></Button>
                      {r.status !== "received" && r.status !== "cancelled" && (
                        <Button size="sm" className="h-7 rounded-sm" onClick={() => setReceive(r)} data-testid={`challan-receive-${r.id}`}>
                          <CheckSquare className="h-3 w-3 mr-1" /> Receive
                        </Button>
                      )}
                      {r.status !== "received" && (
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => remove(r)} data-testid={`challan-delete-${r.id}`}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Create dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl rounded-sm max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">New Challan</DialogTitle>
            <DialogDescription className="sr-only">Create a delivery, return, inter-site transfer or vendor return challan.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 py-2">
            <div>
              <Label className="text-xs uppercase tracking-wider">Type</Label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="ch-type">
                <option value="delivery">Delivery</option>
                <option value="return">Return</option>
                <option value="inter_site_transfer">Inter-site Transfer</option>
                <option value="vendor_return">Vendor Return</option>
              </select>
            </div>
            <div><Label className="text-xs uppercase tracking-wider">From Location</Label><Input value={form.from_location} onChange={(e) => setForm({ ...form, from_location: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-from" /></div>
            <div><Label className="text-xs uppercase tracking-wider">To Location</Label><Input value={form.to_location} onChange={(e) => setForm({ ...form, to_location: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-to" /></div>
            <div><Label className="text-xs uppercase tracking-wider">Vehicle #</Label><Input value={form.vehicle_no} onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-vehicle" /></div>
            <div><Label className="text-xs uppercase tracking-wider">Driver</Label><Input value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-driver" /></div>
            <div><Label className="text-xs uppercase tracking-wider">Driver Phone</Label><Input value={form.driver_phone} onChange={(e) => setForm({ ...form, driver_phone: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-phone" /></div>
            <div><Label className="text-xs uppercase tracking-wider">Transporter</Label><Input value={form.transporter} onChange={(e) => setForm({ ...form, transporter: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
            <div><Label className="text-xs uppercase tracking-wider">E-way Bill #</Label><Input value={form.eway_bill_no} onChange={(e) => setForm({ ...form, eway_bill_no: e.target.value })} className="h-9 rounded-sm mt-1" /></div>
            <div><Label className="text-xs uppercase tracking-wider">Dispatch Date</Label><Input type="date" value={form.dispatch_at} onChange={(e) => setForm({ ...form, dispatch_at: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="ch-dispatch" /></div>
          </div>

          <div className="border-t border-border pt-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Line Items</div>
              <Button type="button" size="sm" variant="outline" className="h-7 rounded-sm" onClick={addItem} data-testid="ch-add-item"><Plus className="h-3 w-3 mr-1" /> Add</Button>
            </div>
            <div className="space-y-2">
              {form.items.map((it, idx) => (
                <div key={idx} className="border border-border rounded-sm p-2 grid grid-cols-1 md:grid-cols-6 gap-2 bg-muted/20" data-testid={`ch-item-${idx}`}>
                  <div className="md:col-span-2"><Label className="text-[10px] uppercase tracking-wider">Item</Label><Input value={it.name} onChange={(e) => updItem(idx, "name", e.target.value)} className="h-8 rounded-sm" data-testid={`ch-item-${idx}-name`} /></div>
                  <div><Label className="text-[10px] uppercase tracking-wider">Qty</Label><Input type="number" value={it.quantity} onChange={(e) => updItem(idx, "quantity", e.target.value)} className="h-8 rounded-sm" data-testid={`ch-item-${idx}-qty`} /></div>
                  <div><Label className="text-[10px] uppercase tracking-wider">Unit</Label><Input value={it.unit} onChange={(e) => updItem(idx, "unit", e.target.value)} className="h-8 rounded-sm" /></div>
                  <div><Label className="text-[10px] uppercase tracking-wider">Serial</Label><Input value={it.serial_no} onChange={(e) => updItem(idx, "serial_no", e.target.value)} className="h-8 rounded-sm" /></div>
                  <div className="flex items-end justify-end">{form.items.length > 1 && <Button size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => rmItem(idx)} data-testid={`ch-item-remove-${idx}`}><X className="h-3 w-3" /></Button>}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3"><Label className="text-xs uppercase tracking-wider">Remarks</Label><textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="w-full min-h-[50px] rounded-sm border border-input bg-background p-2 text-sm mt-1" /></div>

          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="ch-save">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* View dialog with QR */}
      {view && (
        <Dialog open onOpenChange={() => setView(null)}>
          <DialogContent className="max-w-2xl rounded-sm" data-testid="challan-view-dialog">
            <DialogHeader>
              <DialogTitle className="font-display flex items-center gap-2"><QrCode className="h-4 w-4 text-primary" /> {view.challan_no}</DialogTitle>
              <DialogDescription className="sr-only">Challan QR + items + e-signature.</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-2">
              <div className="md:col-span-1 flex flex-col items-center justify-start gap-2 p-3 bg-muted/30 rounded-sm" data-testid="challan-qr-block">
                <QRCodeCanvas value={view.qr_payload || view.challan_no} size={160} level="M" />
                <div className="font-mono-data text-[10px] text-muted-foreground text-center break-all">{view.qr_payload}</div>
                <StatusBadge text={(view.status || "").replaceAll("_", " ")} tone={STATUS_TONE[view.status] || "neutral"} />
              </div>
              <div className="md:col-span-2 space-y-2">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <Info label="Type" value={TYPE_LABEL[view.type]} />
                  <Info label="Dispatch" value={view.dispatched_at?.slice(0, 10) || "—"} />
                  <Info label="From" value={view.from_location || "—"} />
                  <Info label="To" value={view.to_location || "—"} />
                  <Info label="Vehicle" value={view.vehicle_no || "—"} />
                  <Info label="Driver" value={view.driver_name || "—"} />
                  <Info label="E-way Bill" value={view.eway_bill_no || "—"} />
                  <Info label="Transporter" value={view.transporter || "—"} />
                </div>
                <div className="border-t border-border pt-2">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Items ({(view.items || []).length})</div>
                  <ul className="space-y-1 text-xs">
                    {(view.items || []).map((it, i) => (
                      <li key={i} className="flex justify-between border-b border-border py-1">
                        <span className="font-semibold">{it.name}</span>
                        <span className="font-mono-data">{it.quantity} {it.unit}{it.serial_no ? ` · ${it.serial_no}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                {view.e_signature && (
                  <div className="border-t border-border pt-2 text-xs" data-testid="challan-esign-block">
                    <div className="text-[10px] uppercase tracking-wider text-success font-bold mb-1">✓ Received & Signed</div>
                    <div><span className="text-muted-foreground">By:</span> {view.e_signature.name}</div>
                    <div className="text-[10px] text-muted-foreground">User: {view.e_signature.user_name} · {view.e_signature.signed_at?.slice(0, 19).replace("T", " ")} · IP: {view.e_signature.ip}</div>
                  </div>
                )}
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" className="rounded-sm" onClick={() => setView(null)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Receive dialog */}
      {receive && <ReceiveDialog ch={receive} onClose={() => { setReceive(null); load(); }} />}
    </div>
  );
}

function Info({ label, value }) {
  return (<div><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-semibold">{value}</div></div>);
}

function ReceiveDialog({ ch, onClose }) {
  const [name, setName] = useState("");
  const [remarks, setRemarks] = useState("");

  const submit = async () => {
    if (!name.trim()) { toast.error("Receiver name is required"); return; }
    try {
      await api.post(`/challans/${ch.id}/receive`, { receiver_name: name.trim(), received_remarks: remarks });
      toast.success("Received & signed");
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">Receive · {ch.challan_no}</DialogTitle>
          <DialogDescription className="sr-only">Record receiver e-signature.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="text-[10px] uppercase tracking-wider bg-warning/10 text-warning border border-warning/30 px-2 py-1.5 rounded-sm">
            Your name, user-id, IP and timestamp will be captured as an e-signature stamp.
          </div>
          <div><Label className="text-xs uppercase tracking-wider">Receiver Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} className="h-9 rounded-sm mt-1" placeholder="Print receiver's name" data-testid="receive-name" /></div>
          <div><Label className="text-xs uppercase tracking-wider">Remarks</Label><Input value={remarks} onChange={(e) => setRemarks(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="receive-remarks" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={submit} data-testid="receive-confirm"><CheckSquare className="h-3.5 w-3.5 mr-1" /> Sign & Receive</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
