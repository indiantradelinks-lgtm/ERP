/**
 * Phase 3 & 4 Logistics — Mobilization / Travel / Accommodation / Site Reporting /
 * Demobilization / Fuel / Vehicle Expense / Maintenance / Vendor Bill / Cost Summary.
 * All lightweight CRUD/list pages exported individually.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Users, Plane, Hotel, MapPin, LogOut, Fuel, Wrench, DollarSign, FileText, Plus, RefreshCcw, Pencil, Paperclip } from "lucide-react";
import RowAttachments from "@/components/RowAttachments";
import FileUploader from "@/components/FileUploader";
import useAutoSync from "@/hooks/useAutoSync";

// ------------------------------------------------------------
// Generic list + dialog shell
// ------------------------------------------------------------
function ListPage({ testId, title, subtitle, icon, endpoint, columns, formFields, empty,
                    tone = "blue", extraLoads = [], onEnrich, attachments }) {
  const [rows, setRows] = useState([]);
  const [preloads, setPreloads] = useState({});
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [attachFor, setAttachFor] = useState(null);

  const load = async (silent = false) => {
    try {
      const results = await Promise.allSettled([
        api.get(endpoint),
        ...extraLoads.map((l) => api.get(l.path)),
      ]);
      const [main, ...rest] = results;
      if (main.status === "rejected") throw main.reason;
      let data = main.value.data || [];
      if (onEnrich) data = await onEnrich(data);
      setRows(data);
      const pmap = {};
      extraLoads.forEach((l, i) => {
        pmap[l.key] = rest[i].status === "fulfilled" ? (rest[i].value.data || []) : [];
      });
      setPreloads(pmap);
    } catch (e) { if (!silent) toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  // Perf: background sync refreshes ONLY the main list (preloads rarely change)
  const refreshMain = async () => {
    const r = await api.get(endpoint);
    let data = r.data || [];
    if (onEnrich) data = await onEnrich(data);
    setRows(data);
  };
  useAutoSync(refreshMain, { interval: 5000 });

  const save = async () => {
    try {
      const payload = { ...form };
      // numeric coercion
      Object.entries(payload).forEach(([k, v]) => {
        if (typeof v === "string" && k.match(/(amount|cost|qty|rate|km|ltrs|volume|weight)/i) && v !== "") {
          payload[k] = Number(v);
        }
        if (v === "") delete payload[k];
      });
      if (editing?.id) await api.put(`${endpoint}/${editing.id}`, payload);
      else await api.post(endpoint, payload);
      toast.success("Saved");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const editRow = (r) => { setEditing(r); setForm({ ...empty, ...r, _files: [] }); };

  return (
    <div className="p-6 space-y-4" data-testid={testId}>
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className={`text-[10px] font-bold uppercase tracking-[0.18em] text-${tone}-700 mb-1.5`}>Module · Logistics</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">{icon} {title}</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm({ ...empty, id: (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`), _files: [] }); }} data-testid={`${testId}-new`}>
            <Plus className="h-4 w-4 mr-1" /> New
          </Button>
        </div>
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right" : "text-left"}`}>{c.label}</th>
                ))}
                <th className="text-right px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={columns.length + 1} className="text-center py-8 text-slate-400">No entries.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`${testId}-row-${r.id}`}>
                  {columns.map((c) => (
                    <td key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right" : ""} ${c.className || ""}`}>
                      {c.render ? c.render(r) : (r[c.key] ?? "—")}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {attachments && (
                      <Button size="sm" variant="ghost" onClick={() => setAttachFor(r)} data-testid={`${testId}-attach-${r.id}`}>
                        <Paperclip className="h-3 w-3" />
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => editRow(r)} data-testid={`${testId}-edit-${r.id}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.id ? "Edit" : "New"} · {title}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            {formFields.map((f) => (
              <div key={f.key} className={f.full ? "col-span-2" : ""}>
                <Label>{f.label}</Label>
                {f.type === "textarea" ? (
                  <Textarea rows={f.rows || 2} value={form[f.key] || ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                ) : f.type === "select" ? (
                  <select className="w-full border rounded h-10 px-2 text-sm" value={form[f.key] || ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                    {(f.options || []).map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                  </select>
                ) : f.type === "preload" ? (
                  <select className="w-full border rounded h-10 px-2 text-sm" value={form[f.key] || ""} data-testid={`${testId}-f-${f.key}`} onChange={(e) => {
                    const sel = (preloads[f.preloadKey] || []).find((x) => x.id === e.target.value);
                    const patch = { [f.key]: e.target.value };
                    if (f.mirrorTo && sel) patch[f.mirrorTo] = sel[f.mirrorField] || sel.name || sel.driver_name || sel.code || "";
                    if (f.afterChange) Object.assign(patch, f.afterChange(sel, preloads) || {});
                    setForm({ ...form, ...patch });
                  }}>
                    <option value="">—</option>
                    {(preloads[f.preloadKey] || []).filter((o) => !f.filterBy || f.filterBy(o, form)).map((o) => <option key={o.id} value={o.id}>{f.labelRender ? f.labelRender(o) : (o[f.labelField] || o.name || o.driver_name || o.code || o.id)}</option>)}
                  </select>
                ) : f.type === "attachments" ? (
                  <FileUploader folder={f.parentType} parent_type={f.parentType} parent_id={form.id}
                    files={form._files || []}
                    onUploaded={(fl) => setForm((prev) => ({ ...prev, _files: [...(prev._files || []), fl] }))}
                    onDeleted={(fid) => setForm((prev) => ({ ...prev, _files: (prev._files || []).filter((x) => x.id !== fid) }))}
                    compact testidPrefix={`${testId}-attach-uploader`} />
                ) : f.type === "checkbox" ? (
                  <label className="flex items-center gap-2 text-sm h-10"><input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} /><span>{f.hint || f.label}</span></label>
                ) : (
                  <Input type={f.type || "text"} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid={`${testId}-save`}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {attachments && (
        <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
          parentType={attachments} parentId={attachFor?.id}
          recordTitle={`Documents — ${attachFor?.vb_no || attachFor?.id || ""}`} />
      )}
    </div>
  );
}

// Compact approval-chain cell with a "view full chain" dialog (per row, self-contained)
const CHAIN_TONE = {
  approved: "bg-emerald-100 text-emerald-700 border-emerald-200",
  pending: "bg-amber-100 text-amber-700 border-amber-200",
  rejected: "bg-rose-100 text-rose-700 border-rose-200",
  skipped: "bg-slate-100 text-slate-500 border-slate-200",
};

function ApprovalChainCell({ row }) {
  const [open, setOpen] = useState(false);
  const chain = row.approval_chain || [];
  if (!chain.length) return <span className="text-slate-400 text-xs">—</span>;
  return (
    <>
      <button className="flex items-center gap-1 cursor-pointer" onClick={() => setOpen(true)}
        title="View complete approval chain" data-testid={`vb-chain-${row.vb_no || row.id}`}>
        {chain.map((s, i) => (
          <span key={i} className={`inline-block px-1.5 py-0.5 rounded border text-[9px] font-semibold whitespace-nowrap ${CHAIN_TONE[s.status] || CHAIN_TONE.pending}`}>
            {s.status === "approved" ? "✓" : s.status === "rejected" ? "✗" : "⏳"} {s.label || s.role}
          </span>
        ))}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="vb-chain-dialog">
          <DialogHeader><DialogTitle>Approval Chain — {row.vb_no || row.bill_no}</DialogTitle></DialogHeader>
          <div className="space-y-2">
            {chain.map((s, i) => (
              <div key={i} className={`border rounded-md p-3 ${CHAIN_TONE[s.status] || CHAIN_TONE.pending}`}>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Level {i + 1} · {s.label || s.role}</div>
                  <span className="text-[10px] font-bold uppercase">{s.status || "pending"}</span>
                </div>
                <div className="text-xs mt-1">
                  <div><b>Approver:</b> {s.approver || "— awaiting action —"}</div>
                  {s.at && <div><b>On:</b> {new Date(s.at).toLocaleString()}</div>}
                  <div><b>Remarks:</b> {s.comment || "—"}</div>
                </div>
              </div>
            ))}
            {row.remarks && <div className="text-xs text-slate-600 border-t pt-2"><b>Bill Remarks:</b> {row.remarks}</div>}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 3 pages
// ═══════════════════════════════════════════════════════════════════════════

export function ManpowerMobilization() {
  return (
    <ListPage
      testId="mobilization-page"
      title="Manpower Mobilization"
      subtitle="Request → travel → accommodation → site reporting → demobilization pipeline."
      icon={<Users className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/mobilizations"
      extraLoads={[{ key: "projects", path: "/projects" }]}
      empty={{ project_id: "", project_code: "", site_location: "", client: "", reporting_date: "",
               reporting_person: "", travel_required: false, accommodation_required: false,
               conveyance_required: false, safety_ready: false, priority: "normal",
               workers: [], remarks: "", status: "draft" }}
      columns={[
        { key: "mob_no", label: "MOB #", className: "font-mono text-xs" },
        { key: "project_code", label: "Project" },
        { key: "site_location", label: "Site" },
        { key: "reporting_date", label: "Reporting" },
        { key: "priority", label: "Priority" },
        { key: "workers", label: "Workers", align: "right", render: (r) => (r.workers || []).length },
        { key: "status", label: "Status", render: (r) => <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded bg-slate-100">{r.status}</span> },
      ]}
      formFields={[
        { key: "project_id", label: "Project (ID · Name)", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code" },
        { key: "client", label: "Client" },
        { key: "site_location", label: "Site Location", full: true },
        { key: "reporting_date", label: "Reporting Date", type: "date" },
        { key: "reporting_person", label: "Reporting Person" },
        { key: "priority", label: "Priority", type: "select", options: ["low", "normal", "high", "urgent"] },
        { key: "status", label: "Status", type: "select", options: ["draft", "pending_approval", "approved", "in_progress", "reported", "completed", "cancelled"] },
        { key: "travel_required", label: "Travel Required?", type: "checkbox" },
        { key: "accommodation_required", label: "Accommodation Required?", type: "checkbox" },
        { key: "conveyance_required", label: "Conveyance Required?", type: "checkbox" },
        { key: "safety_ready", label: "Safety Ready?", type: "checkbox" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function TravelArrangement() {
  return (
    <ListPage
      testId="travel-page"
      title="Travel Arrangement"
      subtitle="Bus / train / flight / vehicle bookings for mobilized workers."
      icon={<Plane className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/travel"
      extraLoads={[{ key: "mobs", path: "/logistics/mobilizations" }, { key: "projects", path: "/projects" }]}
      empty={{ mob_id: "", employee_name: "", travel_mode: "bus", from_location: "", to_location: "",
               travel_date: "", ticket_ref: "", cost: "", paid_by: "", status: "planned",
               project_id: "", project_code: "", remarks: "" }}
      columns={[
        { key: "travel_no", label: "TRV #", className: "font-mono text-xs" },
        { key: "employee_name", label: "Employee" },
        { key: "travel_mode", label: "Mode" },
        { key: "from_location", label: "From" },
        { key: "to_location", label: "To" },
        { key: "travel_date", label: "Date" },
        { key: "cost", label: "Cost", align: "right", render: (r) => r.cost ? `₹${r.cost}` : "—" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "mob_id", label: "Mobilization", type: "preload", preloadKey: "mobs", labelField: "mob_no" },
        { key: "employee_name", label: "Employee Name" },
        { key: "travel_mode", label: "Mode", type: "select", options: ["bus", "train", "flight", "company_vehicle", "vendor_vehicle", "own"] },
        { key: "from_location", label: "From" },
        { key: "to_location", label: "To" },
        { key: "travel_date", label: "Travel Date", type: "date" },
        { key: "ticket_ref", label: "Ticket / Booking Ref" },
        { key: "cost", label: "Cost (₹)", type: "number" },
        { key: "paid_by", label: "Paid By" },
        { key: "project_id", label: "Project (ID · Name)", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code" },
        { key: "status", label: "Status", type: "select", options: ["planned", "confirmed", "cancelled", "completed"] },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function AccommodationArrangement() {
  return (
    <ListPage
      testId="accommodation-page"
      title="Accommodation Arrangement"
      subtitle="Company / client / vendor / hotel / labour camp bookings for site staff."
      icon={<Hotel className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/accommodations"
      extraLoads={[{ key: "mobs", path: "/logistics/mobilizations" }, { key: "projects", path: "/projects" }]}
      empty={{ mob_id: "", project_id: "", project_code: "", site_location: "", employee_name: "",
               acc_type: "hotel", check_in: "", check_out: "", vendor_name: "", cost: "",
               status: "planned", remarks: "" }}
      columns={[
        { key: "acc_no", label: "ACC #", className: "font-mono text-xs" },
        { key: "employee_name", label: "Employee" },
        { key: "acc_type", label: "Type" },
        { key: "check_in", label: "Check-in" },
        { key: "check_out", label: "Check-out" },
        { key: "cost", label: "Cost", align: "right", render: (r) => r.cost ? `₹${r.cost}` : "—" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "mob_id", label: "Mobilization", type: "preload", preloadKey: "mobs", labelField: "mob_no" },
        { key: "employee_name", label: "Employee Name" },
        { key: "acc_type", label: "Type", type: "select", options: ["company", "client", "vendor", "hotel", "labour_camp", "other"] },
        { key: "vendor_name", label: "Vendor / Hotel Name" },
        { key: "check_in", label: "Check-in", type: "date" },
        { key: "check_out", label: "Check-out", type: "date" },
        { key: "cost", label: "Cost (₹)", type: "number" },
        { key: "project_id", label: "Project (ID · Name)", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code" },
        { key: "site_location", label: "Site Location" },
        { key: "status", label: "Status", type: "select", options: ["planned", "confirmed", "active", "closed", "cancelled"] },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function SiteReporting() {
  return (
    <ListPage
      testId="site-reporting-page"
      title="Site Reporting Confirmation"
      subtitle="Workers reporting on site — safety induction & accommodation check."
      icon={<MapPin className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/site-reporting"
      extraLoads={[{ key: "mobs", path: "/logistics/mobilizations" }]}
      empty={{ mob_id: "", employee_name: "", project_code: "", site_location: "",
               reporting_at: "", reported_to: "", attendance_start: "",
               safety_induction_done: false, accommodation_confirmed: false, remarks: "" }}
      columns={[
        { key: "sr_no", label: "SR #", className: "font-mono text-xs" },
        { key: "employee_name", label: "Employee" },
        { key: "project_code", label: "Project" },
        { key: "site_location", label: "Site" },
        { key: "reporting_at", label: "Reported At", render: (r) => (r.reporting_at || "").slice(0, 16).replace("T", " ") },
        { key: "safety_induction_done", label: "Induction", render: (r) => r.safety_induction_done ? "✔" : "✗" },
        { key: "accommodation_confirmed", label: "Acc.", render: (r) => r.accommodation_confirmed ? "✔" : "✗" },
      ]}
      formFields={[
        { key: "mob_id", label: "Mobilization", type: "preload", preloadKey: "mobs", labelField: "mob_no" },
        { key: "employee_name", label: "Employee Name" },
        { key: "project_code", label: "Project Code" },
        { key: "site_location", label: "Site Location" },
        { key: "reporting_at", label: "Reporting At", type: "datetime-local" },
        { key: "reported_to", label: "Reported To" },
        { key: "attendance_start", label: "Attendance Start", type: "date" },
        { key: "safety_induction_done", label: "Safety Induction Done?", type: "checkbox" },
        { key: "accommodation_confirmed", label: "Accommodation Confirmed?", type: "checkbox" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function Demobilization() {
  return (
    <ListPage
      testId="demobilization-page"
      title="Demobilization Logistics"
      subtitle="Return travel · PPE return · store clearance · accommodation closure."
      icon={<LogOut className="h-6 w-6 text-blue-600" />}
      endpoint="/logistics/demobilizations"
      extraLoads={[{ key: "mobs", path: "/logistics/mobilizations" }, { key: "travel", path: "/logistics/travel" }]}
      empty={{ mob_id: "", employee_name: "", project_code: "", site_location: "", demob_date: "",
               return_travel_required: false, return_destination: "", ppe_return_done: false,
               store_clearance_done: false, travel_id: "", acc_closure_done: false,
               status: "in_progress", remarks: "" }}
      columns={[
        { key: "demob_no", label: "DMB #", className: "font-mono text-xs" },
        { key: "employee_name", label: "Employee" },
        { key: "project_code", label: "Project" },
        { key: "demob_date", label: "Demob Date" },
        { key: "store_clearance_done", label: "Store", render: (r) => r.store_clearance_done ? "✔" : "✗" },
        { key: "ppe_return_done", label: "PPE", render: (r) => r.ppe_return_done ? "✔" : "✗" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "mob_id", label: "Mobilization", type: "preload", preloadKey: "mobs", labelField: "mob_no" },
        { key: "employee_name", label: "Employee Name" },
        { key: "project_code", label: "Project Code" },
        { key: "site_location", label: "Site Location" },
        { key: "demob_date", label: "Demob Date", type: "date" },
        { key: "return_travel_required", label: "Return Travel Required?", type: "checkbox" },
        { key: "return_destination", label: "Return Destination" },
        { key: "travel_id", label: "Return Travel Ref", type: "preload", preloadKey: "travel", labelField: "travel_no" },
        { key: "ppe_return_done", label: "PPE Returned?", type: "checkbox" },
        { key: "store_clearance_done", label: "Store Clearance Done?", type: "checkbox" },
        { key: "acc_closure_done", label: "Accommodation Closed?", type: "checkbox" },
        { key: "status", label: "Status", type: "select", options: ["in_progress", "closed", "cancelled"] },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 4 pages
// ═══════════════════════════════════════════════════════════════════════════

export function FuelEntries() {
  return (
    <ListPage
      testId="fuel-page"
      title="Fuel / Diesel Entries"
      subtitle="Fuel bill capture with KM tracking and duplicate detection."
      icon={<Fuel className="h-6 w-6 text-amber-600" />}
      tone="amber"
      endpoint="/logistics/fuel-entries"
      extraLoads={[{ key: "vehicles", path: "/logistics/vehicles" }, { key: "drivers", path: "/logistics/drivers" }, { key: "projects", path: "/projects" }]}
      empty={{ vehicle_id: "", driver_id: "", entry_date: "", opening_km: "", closing_km: "",
               quantity_ltrs: "", rate: "", amount: "", fuel_station: "", bill_no: "",
               payment_mode: "cash", project_id: "", project_code: "", remarks: "", status: "pending" }}
      columns={[
        { key: "fuel_no", label: "FUEL #", className: "font-mono text-xs" },
        { key: "entry_date", label: "Date" },
        { key: "vehicle_id", label: "Vehicle", render: (r) => r.vehicle_id?.slice(0, 8) || "—" },
        { key: "quantity_ltrs", label: "Ltrs", align: "right" },
        { key: "rate", label: "Rate", align: "right" },
        { key: "amount", label: "Amount", align: "right", render: (r) => r.amount ? `₹${r.amount}` : "—" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "vehicle_id", label: "Vehicle *", type: "preload", preloadKey: "vehicles", labelField: "vehicle_number" },
        { key: "driver_id", label: "Driver", type: "preload", preloadKey: "drivers", labelField: "driver_name" },
        { key: "entry_date", label: "Entry Date", type: "date" },
        { key: "opening_km", label: "Opening KM", type: "number" },
        { key: "closing_km", label: "Closing KM", type: "number" },
        { key: "quantity_ltrs", label: "Quantity (Ltrs) *", type: "number" },
        { key: "rate", label: "Rate/Ltr *", type: "number" },
        { key: "amount", label: "Amount (₹) — auto if blank", type: "number" },
        { key: "fuel_station", label: "Fuel Station / Vendor" },
        { key: "bill_no", label: "Bill No." },
        { key: "payment_mode", label: "Payment Mode", type: "select", options: ["cash", "bank", "card", "credit", "advance"] },
        { key: "project_id", label: "Project (ID · Name)", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code" },
        { key: "status", label: "Status", type: "select", options: ["pending", "approved", "rejected"] },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function VehicleExpenses() {
  return (
    <ListPage
      testId="vehicle-expense-page"
      title="Vehicle Expenses"
      subtitle="Toll · parking · tyre · battery · driver allowance · permit · insurance · other."
      icon={<DollarSign className="h-6 w-6 text-amber-600" />}
      tone="amber"
      endpoint="/logistics/vehicle-expenses"
      extraLoads={[{ key: "vehicles", path: "/logistics/vehicles" }, { key: "projects", path: "/projects" }, { key: "vendors", path: "/vendors" }]}
      empty={{ vehicle_id: "", entry_date: "", category: "other", amount: "",
               project_id: "", project_code: "", vendor_id: "", bill_no: "", remarks: "", status: "pending" }}
      columns={[
        { key: "expense_no", label: "EXP #", className: "font-mono text-xs" },
        { key: "entry_date", label: "Date" },
        { key: "category", label: "Category" },
        { key: "amount", label: "Amount", align: "right", render: (r) => `₹${r.amount}` },
        { key: "vehicle_id", label: "Vehicle", render: (r) => r.vehicle_id?.slice(0, 8) || "—" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "vehicle_id", label: "Vehicle *", type: "preload", preloadKey: "vehicles", labelField: "vehicle_number" },
        { key: "entry_date", label: "Entry Date", type: "date" },
        { key: "category", label: "Category", type: "select", options: ["repair", "tyre", "battery", "toll", "parking", "permit", "insurance", "fitness", "pollution", "driver_allowance", "loading_unloading", "other"] },
        { key: "amount", label: "Amount (₹) *", type: "number" },
        { key: "vendor_id", label: "Vendor", type: "preload", preloadKey: "vendors", labelField: "name" },
        { key: "bill_no", label: "Bill No." },
        { key: "project_id", label: "Project (ID · Name)", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code" },
        { key: "status", label: "Status", type: "select", options: ["pending", "approved", "rejected"] },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function VehicleMaintenance() {
  return (
    <ListPage
      testId="maintenance-page"
      title="Vehicle Maintenance Register"
      subtitle="Preventive / breakdown / repair / inspection log with cost + next-due tracking."
      icon={<Wrench className="h-6 w-6 text-amber-600" />}
      tone="amber"
      endpoint="/logistics/maintenance"
      extraLoads={[{ key: "vehicles", path: "/logistics/vehicles" }, { key: "vendors", path: "/vendors" }]}
      empty={{ vehicle_id: "", maintenance_type: "preventive", maint_date: "", odometer_km: "",
               work_done: "", vendor_id: "", vendor_name: "", cost: "", next_due_date: "",
               status: "in_progress", remarks: "" }}
      columns={[
        { key: "maint_no", label: "MNT #", className: "font-mono text-xs" },
        { key: "maint_date", label: "Date" },
        { key: "maintenance_type", label: "Type" },
        { key: "cost", label: "Cost", align: "right", render: (r) => r.cost ? `₹${r.cost}` : "—" },
        { key: "next_due_date", label: "Next Due" },
        { key: "status", label: "Status" },
      ]}
      formFields={[
        { key: "vehicle_id", label: "Vehicle *", type: "preload", preloadKey: "vehicles", labelField: "vehicle_number" },
        { key: "maintenance_type", label: "Type", type: "select", options: ["preventive", "breakdown", "repair", "inspection"] },
        { key: "maint_date", label: "Maintenance Date", type: "date" },
        { key: "odometer_km", label: "Odometer (km)", type: "number" },
        { key: "vendor_id", label: "Workshop / Vendor", type: "preload", preloadKey: "vendors", labelField: "name", mirrorTo: "vendor_name", mirrorField: "name" },
        { key: "cost", label: "Cost (₹)", type: "number" },
        { key: "next_due_date", label: "Next Due Date", type: "date" },
        { key: "status", label: "Status", type: "select", options: ["in_progress", "completed", "approved"] },
        { key: "work_done", label: "Work Done", type: "textarea", full: true },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
      ]}
    />
  );
}

export function VendorBills() {
  return (
    <ListPage
      testId="vendor-bill-page"
      title="Transport Vendor Bills"
      subtitle="Freight bill verification · GST / TDS · approval → Accounts payable."
      icon={<FileText className="h-6 w-6 text-amber-600" />}
      tone="amber"
      endpoint="/logistics/vendor-bills"
      attachments="vendor_bills"
      extraLoads={[{ key: "vendors", path: "/logistics/transport-vendors" }, { key: "projects", path: "/projects" }, { key: "drs", path: "/logistics/dispatch-requests" }, { key: "cost_centers", path: "/procurement/master/cost-centers" }]}
      empty={{ vendor_id: "", vendor_name: "", bill_no: "", bill_date: "", dispatch_id: "",
               dispatch_no: "", project_id: "", project_code: "",
               freight_amount: "", loading_cost: "", unloading_cost: "", detention_amount: "",
               other_charges: "", gst_amount: "", tds_amount: "", net_payable: "",
               remarks: "", status: "submitted" }}
      columns={[
        { key: "vb_no", label: "VB #", className: "font-mono text-xs" },
        { key: "bill_no", label: "Bill #" },
        { key: "bill_date", label: "Date" },
        { key: "vendor_name", label: "Vendor" },
        { key: "project_code", label: "Project" },
        { key: "cost_center_label", label: "Cost Center", render: (r) => r.cost_center_label || "—" },
        { key: "freight_amount", label: "Freight", align: "right", render: (r) => r.freight_amount ? `₹${r.freight_amount}` : "—" },
        { key: "net_payable", label: "Net Payable", align: "right", render: (r) => r.net_payable ? `₹${r.net_payable}` : "—" },
        { key: "status", label: "Status" },
        { key: "approval_chain", label: "Approval Chain", render: (r) => <ApprovalChainCell row={r} /> },
      ]}
      formFields={[
        { key: "vendor_id", label: "Vendor *", type: "preload", preloadKey: "vendors", labelField: "name", mirrorTo: "vendor_name", mirrorField: "name" },
        { key: "bill_no", label: "Bill No. *" },
        { key: "bill_date", label: "Bill Date", type: "date" },
        { key: "dispatch_id", label: "Dispatch (optional)", type: "preload", preloadKey: "drs", labelField: "dr_no", mirrorTo: "dispatch_no", mirrorField: "dr_no" },
        { key: "project_id", label: "Project (ID · Name) *", type: "preload", preloadKey: "projects", labelField: "code", labelRender: (o) => `${o.code || o.project_code} · ${o.name || o.project_name || "—"}`, mirrorTo: "project_code", mirrorField: "code",
          afterChange: (sel, preloads) => {
            if (!sel) return { cost_center_id: "", cost_center_label: "" };
            const ccs = (preloads.cost_centers || []).filter((c) => c.project_id === sel.id && c.active !== false);
            const cc = ccs.find((c) => /transport|vehicle|freight/i.test(`${c.category_code || ""} ${c.name || ""}`)) || ccs[0];
            return cc ? { cost_center_id: cc.id, cost_center_label: cc.name || cc.code } : { cost_center_id: "", cost_center_label: "" };
          } },
        { key: "cost_center_id", label: "Cost Center (auto from project)", type: "preload", preloadKey: "cost_centers", labelField: "name", labelRender: (o) => `${o.name || o.code}${o.project_code ? ` · ${o.project_code}` : ""}`, mirrorTo: "cost_center_label", mirrorField: "name", filterBy: (o, fm) => !fm.project_id || o.project_id === fm.project_id },
        { key: "freight_amount", label: "Freight (₹)", type: "number" },
        { key: "loading_cost", label: "Loading (₹)", type: "number" },
        { key: "unloading_cost", label: "Unloading (₹)", type: "number" },
        { key: "detention_amount", label: "Detention (₹)", type: "number" },
        { key: "other_charges", label: "Other Charges (₹)", type: "number" },
        { key: "gst_amount", label: "GST (₹)", type: "number" },
        { key: "tds_amount", label: "TDS (₹)", type: "number" },
        { key: "net_payable", label: "Net Payable (₹) — auto if blank", type: "number" },
        { key: "remarks", label: "Remarks", type: "textarea", full: true },
        { key: "attachments", label: "Bill / Invoice / Supporting Documents", type: "attachments", parentType: "vendor_bills", full: true },
      ]}
    />
  );
}

// ------------------------------------------------------------
// Cost Summary Dashboard
// ------------------------------------------------------------
export function LogisticsCostSummary() {
  const [data, setData] = useState(null);
  const load = async () => {
    try { const r = await api.get("/logistics/cost-summary"); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  const topProjects = useMemo(() => (data?.by_project || []).slice(0, 10), [data]);
  const topCategories = useMemo(() => (data?.by_category || []).slice(0, 12), [data]);

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="p-6 space-y-5" data-testid="cost-summary-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <DollarSign className="h-6 w-6 text-amber-600" /> Logistics Cost Summary
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Approved fuel + expenses + maintenance + vendor bills, allocated by project and category.
          </p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1.5" />Refresh</Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Card label="Total Cost (all-time)" value={inr(data.total_cost)} tone="slate" />
        <Card label="This Month" value={inr(data.this_month)} tone="amber" />
        <Card label="High-Value Pending Post" value={data.high_value_pending} tone="red" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">Top Projects</div>
          <table className="w-full text-sm">
            <tbody>
              {topProjects.length === 0 && <tr><td colSpan={2} className="text-center py-6 text-slate-400">No cost data yet.</td></tr>}
              {topProjects.map((p) => (
                <tr key={p.project_code} className="border-t"><td className="px-3 py-1.5 font-mono">{p.project_code}</td><td className="px-3 py-1.5 text-right">{inr(p.amount)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border rounded-sm bg-card overflow-hidden">
          <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">By Category</div>
          <table className="w-full text-sm">
            <tbody>
              {topCategories.length === 0 && <tr><td colSpan={2} className="text-center py-6 text-slate-400">No cost data yet.</td></tr>}
              {topCategories.map((p) => (
                <tr key={p.category} className="border-t"><td className="px-3 py-1.5 capitalize">{(p.category || "").replace(/_/g, " ")}</td><td className="px-3 py-1.5 text-right">{inr(p.amount)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Card({ label, value, tone }) {
  const cls = {
    red: "border-red-200 bg-red-50/40 text-red-700",
    amber: "border-amber-200 bg-amber-50/40 text-amber-700",
    slate: "border-slate-200 bg-white text-slate-900",
  }[tone];
  return (
    <div className={`border rounded-sm p-3 ${cls}`}>
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-2xl font-black mt-1">{value}</div>
    </div>
  );
}
