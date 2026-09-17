/**
 * Dispatch Request Detail (Phase 2) — single-page cockpit for the full
 * DR lifecycle: allocate vehicle+driver → load → transit updates → deliver →
 * raise exceptions. Reads GET /api/logistics/dispatch-requests/{id}/full.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Truck, Package, MapPin, PackageCheck, AlertOctagon, ArrowLeft, ChevronRight } from "lucide-react";
import { fmtDT, fmtD } from "@/lib/datetime";

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  allocated: "bg-blue-100 text-blue-800",
  in_transit: "bg-amber-100 text-amber-800",
  delivered: "bg-emerald-100 text-emerald-800",
  closed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-red-100 text-red-800",
  rejected: "bg-red-100 text-red-800",
};

const TRANSIT_STATES = ["loaded", "dispatched", "in_transit", "reached_site", "unloading",
                        "delivered", "partially_delivered", "delayed", "shortage_reported",
                        "damage_reported", "closed"];

export default function DispatchRequestDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [dialog, setDialog] = useState(null); // 'allocate' | 'load' | 'transit' | 'deliver' | 'exception'
  const [form, setForm] = useState({});

  const load = async () => {
    try {
      const [full, veh, drv] = await Promise.all([
        api.get(`/logistics/dispatch-requests/${id}/full`),
        api.get("/logistics/vehicles?status=available"),
        api.get("/logistics/drivers?status=available"),
      ]);
      setData(full.data); setVehicles(veh.data || []); setDrivers(drv.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [id]);

  const doAction = async (endpoint, payload) => {
    try {
      await api.post(`/logistics/dispatch-requests/${id}/${endpoint}`, payload);
      toast.success(`${endpoint} recorded`);
      setDialog(null); setForm({}); load();
    } catch (e) { toast.error(e.response?.data?.detail || `${endpoint} failed`); }
  };

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  const dr = data.dr;
  const canAllocate = ["approved", "pending_approval"].includes(dr.status);
  const canLoad = dr.allocation_id && ["allocated", "loading_pending"].includes(dr.status);
  const canTransit = dr.status === "in_transit";
  const canDeliver = ["in_transit", "delivered"].includes(dr.status);
  const canException = ["in_transit", "delivered", "partially_delivered"].includes(dr.status);

  return (
    <div className="p-6 space-y-4" data-testid="dr-detail-page">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <button className="text-xs text-blue-700 flex items-center gap-1 mb-1 hover:underline" onClick={() => nav("/app/logistics/dispatch-requests")}>
            <ArrowLeft className="h-3 w-3" /> Back to Dispatch Requests
          </button>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1">Module · Logistics · Phase 2</div>
          <h1 className="font-display font-black text-2xl">
            {dr.dr_no} · {dr.dispatch_type} · {dr.project_code || "Corporate"}
          </h1>
          <div className="mt-1 flex items-center gap-2">
            <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${STATUS_TONE[dr.status] || "bg-slate-100"}`}>{dr.status}</span>
            <span className="text-xs text-slate-500">created {fmtD(dr.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!canAllocate} onClick={() => { setDialog("allocate"); setForm({ freight_basis: "fixed" }); }} data-testid="btn-allocate">
            <Truck className="h-3.5 w-3.5 mr-1" /> Allocate
          </Button>
          <Button size="sm" disabled={!canLoad} onClick={() => { setDialog("load"); setForm({ driver_acknowledged: true }); }} data-testid="btn-load">
            <Package className="h-3.5 w-3.5 mr-1" /> Load
          </Button>
          <Button size="sm" disabled={!canTransit} onClick={() => { setDialog("transit"); setForm({ status: "in_transit" }); }} data-testid="btn-transit">
            <MapPin className="h-3.5 w-3.5 mr-1" /> Transit Update
          </Button>
          <Button size="sm" disabled={!canDeliver} onClick={() => { setDialog("deliver"); setForm({ material_condition: "good", close_dispatch: true }); }} data-testid="btn-deliver">
            <PackageCheck className="h-3.5 w-3.5 mr-1" /> Deliver / POD
          </Button>
          <Button size="sm" variant="destructive" disabled={!canException} onClick={() => { setDialog("exception"); setForm({ kind: "shortage", responsible_party: "unknown" }); }} data-testid="btn-exception">
            <AlertOctagon className="h-3.5 w-3.5 mr-1" /> Report Exception
          </Button>
          <Button size="sm" variant="outline" onClick={() => nav(`/app/logistics/dispatch-requests/${id}/closure`)} data-testid="btn-closure">
            Closure
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <SummaryCard label="Project / Route" value={`${dr.project_code || "—"} · ${dr.from_point_name || "?"} → ${dr.to_point_name || "?"}`} />
        <SummaryCard label="Material Summary" value={dr.material_summary || "—"} />
        <SummaryCard label="Priority" value={dr.priority || "normal"} />
        <SummaryCard label="Required Date" value={dr.required_date || "—"} />
      </div>

      {/* Allocation */}
      <Section title="Vehicle Allocation">
        {!data.allocation ? <Empty label="No vehicle allocated yet." /> : (
          <div className="text-sm grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kv k="Allocation #" v={data.allocation.allocation_no} />
            <Kv k="Vehicle" v={`${data.allocation.vehicle_number} (${data.allocation.vehicle_type})`} />
            <Kv k="Driver" v={data.allocation.driver_name || "—"} />
            <Kv k="Freight Basis" v={data.allocation.freight_basis} />
            <Kv k="Est. Freight" v={data.allocation.estimated_freight ? `₹${data.allocation.estimated_freight}` : "—"} />
            <Kv k="Planned Dispatch" v={data.allocation.planned_dispatch_at || "—"} />
            <Kv k="Expected Delivery" v={data.allocation.expected_delivery_at || "—"} />
          </div>
        )}
      </Section>

      {/* Loadings */}
      <Section title={`Loading Events (${data.loadings.length})`}>
        {data.loadings.length === 0 ? <Empty label="Not yet loaded." /> : data.loadings.map((l) => (
          <div key={l.id} className="text-xs border rounded-sm p-2 mb-1 bg-slate-50/30 grid grid-cols-2 md:grid-cols-4 gap-2" data-testid={`load-${l.id}`}>
            <Kv k="Loading #" v={l.loading_no} />
            <Kv k="Loaded Qty" v={l.loaded_qty ?? "—"} />
            <Kv k="Challan #" v={l.delivery_challan_no || "—"} />
            <Kv k="E-way Bill" v={l.e_way_bill_no || "—"} />
          </div>
        ))}
      </Section>

      {/* Deliveries / POD */}
      <Section title={`Deliveries / POD (${data.deliveries.length})`}>
        {data.deliveries.length === 0 ? <Empty label="No delivery confirmations." /> : data.deliveries.map((d) => (
          <div key={d.id} className="text-xs border rounded-sm p-2 mb-1 bg-slate-50/30 grid grid-cols-2 md:grid-cols-4 gap-2" data-testid={`pod-${d.id}`}>
            <Kv k="POD #" v={d.delivery_no} />
            <Kv k="Delivered Qty" v={d.delivered_qty ?? "—"} />
            <Kv k="Short/Damaged" v={`${d.short_qty || 0} / ${d.damaged_qty || 0}`} />
            <Kv k="Received By" v={d.received_by || "—"} />
            <Kv k="Condition" v={d.material_condition || "—"} />
            <Kv k="Delivered At" v={fmtDT(d.delivered_at)} />
            {d.pod_url && <a className="text-blue-700 hover:underline text-xs" href={d.pod_url} target="_blank" rel="noreferrer">POD Doc ↗</a>}
          </div>
        ))}
      </Section>

      {/* Exceptions */}
      <Section title={`Transit Exceptions (${data.exceptions.length})`}>
        {data.exceptions.length === 0 ? <Empty label="No exceptions." /> : data.exceptions.map((e) => (
          <div key={e.id} className="text-xs border rounded-sm p-2 mb-1 bg-red-50/40 border-red-200 grid grid-cols-2 md:grid-cols-4 gap-2" data-testid={`exc-${e.id}`}>
            <Kv k="Exception #" v={e.exception_no} />
            <Kv k="Kind" v={e.kind} />
            <Kv k="Responsible" v={e.responsible_party} />
            <Kv k="Value" v={e.approx_value ? `₹${e.approx_value}` : "—"} />
            <Kv k="Recovery" v={e.recovery_applicable ? `₹${e.recovery_amount || 0}` : "N/A"} />
            <Kv k="Status" v={e.status} />
          </div>
        ))}
      </Section>

      {/* Timeline */}
      <Section title="Transit Timeline">
        {data.timeline.length === 0 ? <Empty label="No transit events yet." /> : (
          <ol className="relative border-l ml-3 space-y-2">
            {data.timeline.map((t) => (
              <li key={t.id} className="ml-4 text-xs" data-testid={`tl-${t.id}`}>
                <span className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full bg-blue-500 ring-4 ring-white"></span>
                <div className="font-semibold capitalize">{t.status.replace(/_/g, " ")}</div>
                <div className="text-slate-500">{(t.at || "").slice(0, 19).replace("T", " ")} · {t.by_name}</div>
                {t.current_location && <div className="text-slate-600">📍 {t.current_location}</div>}
                {t.remarks && <div className="text-slate-600">{t.remarks}</div>}
              </li>
            ))}
          </ol>
        )}
      </Section>

      {/* Dialogs */}
      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="capitalize">{dialog}</DialogTitle>
          </DialogHeader>

          {dialog === "allocate" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Vehicle *</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.vehicle_id || ""} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })} data-testid="alloc-vehicle">
                  <option value="">—</option>
                  {vehicles.map((v) => <option key={v.id} value={v.id}>{v.vehicle_number} ({v.vehicle_type})</option>)}
                </select>
              </div>
              <div>
                <Label>Driver</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.driver_id || ""} onChange={(e) => setForm({ ...form, driver_id: e.target.value })} data-testid="alloc-driver">
                  <option value="">—</option>
                  {drivers.map((d) => <option key={d.id} value={d.id}>{d.driver_name}</option>)}
                </select>
              </div>
              <div>
                <Label>Freight Basis</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.freight_basis || "fixed"} onChange={(e) => setForm({ ...form, freight_basis: e.target.value })}>
                  {["fixed", "per_km", "per_mt", "per_trip", "per_day", "vendor_bill"].map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div><Label>Estimated Freight (₹)</Label><Input type="number" value={form.estimated_freight || ""} onChange={(e) => setForm({ ...form, estimated_freight: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div><Label>Planned Dispatch</Label><Input type="datetime-local" value={form.planned_dispatch_at || ""} onChange={(e) => setForm({ ...form, planned_dispatch_at: e.target.value })} /></div>
              <div><Label>Expected Delivery</Label><Input type="datetime-local" value={form.expected_delivery_at || ""} onChange={(e) => setForm({ ...form, expected_delivery_at: e.target.value })} /></div>
              <div className="col-span-2"><Label>Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
            </div>
          )}

          {dialog === "load" && (
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Loaded Qty</Label><Input type="number" value={form.loaded_qty ?? ""} onChange={(e) => setForm({ ...form, loaded_qty: e.target.value ? Number(e.target.value) : undefined })} data-testid="load-qty" /></div>
              <div><Label>Approved Qty</Label><Input type="number" value={form.approved_qty ?? ""} onChange={(e) => setForm({ ...form, approved_qty: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div><Label>Delivery Challan #</Label><Input value={form.delivery_challan_no || ""} onChange={(e) => setForm({ ...form, delivery_challan_no: e.target.value })} data-testid="load-challan" /></div>
              <div><Label>E-way Bill #</Label><Input value={form.e_way_bill_no || ""} onChange={(e) => setForm({ ...form, e_way_bill_no: e.target.value })} /></div>
              <div><Label>Gate Pass #</Label><Input value={form.gate_pass_no || ""} onChange={(e) => setForm({ ...form, gate_pass_no: e.target.value })} /></div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form.driver_acknowledged} onChange={(e) => setForm({ ...form, driver_acknowledged: e.target.checked })} data-testid="load-ack" />
                  <span>Driver Acknowledged</span>
                </label>
              </div>
              <div className="col-span-2"><Label>Material Summary</Label><Textarea rows={2} value={form.material_summary || ""} onChange={(e) => setForm({ ...form, material_summary: e.target.value })} /></div>
              <div className="col-span-2"><Label>Excess Override Reason (if loaded &gt; approved)</Label><Input value={form.excess_override_reason || ""} onChange={(e) => setForm({ ...form, excess_override_reason: e.target.value })} /></div>
            </div>
          )}

          {dialog === "transit" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Status *</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.status || "in_transit"} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="transit-status">
                  {TRANSIT_STATES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                </select>
              </div>
              <div><Label>Current Location</Label><Input value={form.current_location || ""} onChange={(e) => setForm({ ...form, current_location: e.target.value })} data-testid="transit-loc" /></div>
              <div className="col-span-2"><Label>Delay Reason (if delayed)</Label><Input value={form.delay_reason || ""} onChange={(e) => setForm({ ...form, delay_reason: e.target.value })} /></div>
              <div className="col-span-2"><Label>Remarks</Label><Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
            </div>
          )}

          {dialog === "deliver" && (
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Delivered Qty *</Label><Input type="number" value={form.delivered_qty ?? ""} onChange={(e) => setForm({ ...form, delivered_qty: e.target.value ? Number(e.target.value) : undefined })} data-testid="deliver-qty" /></div>
              <div><Label>Short Qty</Label><Input type="number" value={form.short_qty ?? ""} onChange={(e) => setForm({ ...form, short_qty: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div><Label>Damaged Qty</Label><Input type="number" value={form.damaged_qty ?? ""} onChange={(e) => setForm({ ...form, damaged_qty: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div><Label>Rejected Qty</Label><Input type="number" value={form.rejected_qty ?? ""} onChange={(e) => setForm({ ...form, rejected_qty: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div>
                <Label>Material Condition</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.material_condition || "good"} onChange={(e) => setForm({ ...form, material_condition: e.target.value })}>
                  {["good", "partial", "damaged", "rejected"].map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div><Label>Received By *</Label><Input value={form.received_by || ""} onChange={(e) => setForm({ ...form, received_by: e.target.value })} data-testid="deliver-by" /></div>
              <div className="col-span-2"><Label>POD URL / Reference</Label><Input value={form.pod_url || ""} onChange={(e) => setForm({ ...form, pod_url: e.target.value })} placeholder="OneDrive link or ref" /></div>
              <div className="col-span-2"><Label>Site Remarks</Label><Textarea rows={2} value={form.site_remarks || ""} onChange={(e) => setForm({ ...form, site_remarks: e.target.value })} /></div>
              <div className="col-span-2">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form.close_dispatch} onChange={(e) => setForm({ ...form, close_dispatch: e.target.checked })} data-testid="deliver-close" />
                  <span>Close dispatch on save (no shortages/damages)</span>
                </label>
              </div>
            </div>
          )}

          {dialog === "exception" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Kind *</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.kind || "shortage"} onChange={(e) => setForm({ ...form, kind: e.target.value })} data-testid="exc-kind">
                  {["shortage", "damage", "rejected"].map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </div>
              <div>
                <Label>Responsible</Label>
                <select className="w-full border rounded h-10 px-2 text-sm" value={form.responsible_party || "unknown"} onChange={(e) => setForm({ ...form, responsible_party: e.target.value })}>
                  {["transporter", "driver", "store_loading", "site_unloading", "unknown"].map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
                </select>
              </div>
              <div><Label>Item</Label><Input value={form.item || ""} onChange={(e) => setForm({ ...form, item: e.target.value })} /></div>
              <div><Label>Short/Damaged Qty</Label><Input type="number" value={form.short_qty ?? ""} onChange={(e) => setForm({ ...form, short_qty: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div><Label>Approx Value (₹)</Label><Input type="number" value={form.approx_value ?? ""} onChange={(e) => setForm({ ...form, approx_value: e.target.value ? Number(e.target.value) : undefined })} /></div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form.recovery_applicable} onChange={(e) => setForm({ ...form, recovery_applicable: e.target.checked })} />
                  <span>Recovery Applicable</span>
                </label>
              </div>
              {form.recovery_applicable && <div><Label>Recovery Amount (₹)</Label><Input type="number" value={form.recovery_amount ?? ""} onChange={(e) => setForm({ ...form, recovery_amount: e.target.value ? Number(e.target.value) : undefined })} /></div>}
              <div className="col-span-2"><Label>Reason</Label><Textarea rows={2} value={form.reason || ""} onChange={(e) => setForm({ ...form, reason: e.target.value })} data-testid="exc-reason" /></div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button onClick={() => doAction(dialog === "deliver" ? "deliver" : dialog === "exception" ? "exception" : dialog === "load" ? "load" : dialog === "allocate" ? "allocate" : "transit", form)} data-testid="dr-action-save">
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const SummaryCard = ({ label, value }) => (
  <div className="border rounded-sm p-3 bg-card">
    <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider">{label}</div>
    <div className="mt-1 text-sm">{value}</div>
  </div>
);
const Section = ({ title, children }) => (
  <section className="border rounded-sm bg-card overflow-hidden">
    <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1">
      <ChevronRight className="h-3 w-3" /> {title}
    </div>
    <div className="p-3">{children}</div>
  </section>
);
const Empty = ({ label }) => <div className="text-xs text-slate-400 py-2 text-center">{label}</div>;
const Kv = ({ k, v }) => (
  <div>
    <div className="text-[10px] uppercase text-slate-500">{k}</div>
    <div className="text-sm font-medium">{v ?? "—"}</div>
  </div>
);
