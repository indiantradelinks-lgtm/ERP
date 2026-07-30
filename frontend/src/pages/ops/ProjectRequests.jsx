import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, PackageSearch, CheckCircle2, XCircle, Clock, FileSpreadsheet, FileText, Boxes, ShoppingCart, Truck, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect } from "@/components/MasterSelect";
import FileUploader from "@/components/FileUploader";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const RAISE_ROLES = new Set(["project_coordinator", "project_manager", "super_admin"]);
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
const STOCKABLE = new Set(["material", "ppe", "it_material"]);
const blankItem = () => ({ name: "", quantity: 1, unit: "Nos", rate: 0, specs: "" });
const blank = () => ({ id: newId(), project_code: "", project_id: "", request_type: "", need_by: "",
  priority: "medium", description: "", items: [blankItem()], vendor: "", vehicle_ref: "",
  period_from: "", period_to: "", monthly_rate: "", months: "", from_location: "", to_location: "", amount: "", remarks: "" });

const STATUS = {
  pending_approval: ["Pending Approval", "border-amber-300 text-amber-900 bg-amber-50"],
  with_dept: ["With Department", "border-blue-300 text-blue-900 bg-blue-50"],
  pr_raised: ["PR Raised", "border-violet-300 text-violet-900 bg-violet-50"],
  fulfilled: ["Fulfilled", "border-emerald-300 text-emerald-900 bg-emerald-50"],
  closed: ["Closed", "border-slate-300 text-slate-700 bg-slate-50"],
  rejected: ["Rejected", "border-rose-300 text-rose-900 bg-rose-50"],
};
const DEPT_ICON = { stores: Boxes, logistics: Truck, admin: Home };

export default function ProjectRequests() {
  const { user } = useAuth();
  const canRaise = RAISE_ROLES.has(user?.role);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [types, setTypes] = useState([]);
  const [filters, setFilters] = useState({ project_code: "", status: "", request_type: "", dept: "" });
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blank());
  const [attFiles, setAttFiles] = useState([]);
  const [stock, setStock] = useState(null);
  const [detail, setDetail] = useState(null);

  const meta = useMemo(() => types.find((t) => t.key === form.request_type), [types, form.request_type]);
  const isStockable = form.request_type && STOCKABLE.has(form.request_type);
  const isVehicle = form.request_type?.startsWith("vehicle") || form.request_type === "one_time_vehicle";
  const isPayment = meta?.payment;

  const load = async () => {
    try {
      const params = {};
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const [r, s] = await Promise.all([
        api.get("/project-requests", { params }),
        api.get("/project-requests/summary", { params: filters.project_code ? { project_code: filters.project_code } : {} }),
      ]);
      setRows(r.data || []); setSummary(s.data);
    } catch { toast.error("Failed to load requests"); }
  };
  useEffect(() => { api.get("/project-requests/types").then((r) => setTypes(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [filters]); // eslint-disable-line

  const estValue = useMemo(() => {
    if (form.amount) return Number(form.amount);
    if (form.monthly_rate) return Number(form.monthly_rate) * Number(form.months || 1);
    return (form.items || []).reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0);
  }, [form]);

  const setItem = (i, patch) => setForm((f) => ({ ...f, items: f.items.map((x, ix) => ix === i ? { ...x, ...patch } : x) }));

  const runStockCheck = async () => {
    try {
      const r = await api.post("/project-requests/stock-check", { ...form, items: form.items });
      setStock(r.data);
      if (r.data.all_in_stock) toast.success("All items in stock — will route to Stores");
      else if (r.data.any_short) toast.warning("Some items short — you can raise a Purchase Request after approval");
    } catch { toast.error("Stock check failed"); }
  };

  const create = async () => {
    if (!form.project_code) { toast.error("Select a project"); return; }
    if (!form.request_type) { toast.error("Select request type"); return; }
    if (estValue <= 0 && !isStockable) { toast.error("Enter amount / rate"); return; }
    try {
      const payload = { ...form,
        amount: form.amount ? Number(form.amount) : null,
        monthly_rate: form.monthly_rate ? Number(form.monthly_rate) : null,
        months: form.months ? Number(form.months) : null,
        items: form.items.map((i) => ({ ...i, quantity: Number(i.quantity) || 0, rate: Number(i.rate) || 0 })) };
      const r = await api.post("/project-requests", payload);
      toast.success(`${r.data.request_no} raised → routes to ${r.data.owning_dept} after Project Head approval`);
      setCreating(false); setForm(blank()); setAttFiles([]); setStock(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const act = async (r, action, needReason) => {
    let remarks = null;
    if (needReason) { remarks = window.prompt(action === "reject" ? "Rejection reason?" : "Note (optional)"); if (action === "reject" && remarks === null) return; }
    try { await api.post(`/project-requests/${r.id}/${action}`, { remarks }); toast.success("Done"); load(); setDetail(null); }
    catch (e) { toast.error(e?.response?.data?.detail || "Action failed"); }
  };

  const raisePR = async (r) => {
    try { const res = await api.post(`/project-requests/${r.id}/raise-pr`); toast.success(`Purchase Request ${res.data.pr_number} created (${res.data.items} item(s))`); load(); setDetail(null); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const download = async (fmt) => {
    try {
      const params = {};
      Object.entries(filters).forEach(([k, v]) => { if (v && k !== "dept") params[k] = v; });
      const { data } = await api.get(`/project-requests/export.${fmt}`, { responseType: "blob", params });
      const url = URL.createObjectURL(data); const a = document.createElement("a");
      a.href = url; a.download = `project_requests.${fmt}`; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const kpis = summary ? [["Total", summary.total], ["Pending Approval", summary.pending_approval],
    ["With Dept", summary.with_dept], ["PR Raised", summary.pr_raised],
    ["Fulfilled", summary.fulfilled], ["Est. Value", inr(summary.est_value)]] : [];

  return (
    <div className="space-y-5" data-testid="project-requests-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <PackageSearch className="h-3 w-3" /> Project Request Center
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Project Requests</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            One place for every site request — Material, PPE, IT, Accommodation, Fuel, Insurance & Vehicles.
            Stock is auto-checked; shortfalls become Purchase Requests. Payment types flow into Daily Expense & Accounts.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="req-reload"><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="req-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="req-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> PDF</Button>
          {canRaise && (
            <Button className="h-9 rounded-sm" onClick={() => { setForm(blank()); setAttFiles([]); setStock(null); setCreating(true); }} data-testid="req-new">
              <Plus className="h-4 w-4 mr-1.5" /> Raise Request
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {kpis.map(([label, v]) => (
          <div key={label} className="bg-card border border-border rounded-sm p-3" data-testid={`req-kpi-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <div className="text-xl font-black tabular">{v}</div>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex items-center gap-2 p-3 border-b border-border flex-wrap">
          <ProjectSelect label="" value={filters.project_code} onChange={(v) => setFilters({ ...filters, project_code: v })}
            className="w-52" testid="req-filter-project" placeholder="— all projects —" />
          <select value={filters.request_type} onChange={(e) => setFilters({ ...filters, request_type: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="req-filter-type">
            <option value="">All types</option>
            {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          <select value={filters.dept} onChange={(e) => setFilters({ ...filters, dept: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="req-filter-dept">
            <option value="">All departments</option>
            <option value="stores">Stores</option><option value="logistics">Logistics</option><option value="admin">Admin/Accounts</option>
          </select>
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="h-8 rounded-sm border border-input bg-background px-2 text-xs" data-testid="req-filter-status">
            <option value="">All statuses</option>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}
          </select>
        </div>
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Request # / Date</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Type / Dept</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Est. Value</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Progress</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
            <TableHead className="text-right"></TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                No requests yet. {canRaise ? "Use Raise Request to submit a site requirement." : ""}
              </TableCell></TableRow>
            )}
            {rows.map((r) => {
              const DIcon = DEPT_ICON[r.owning_dept] || Boxes;
              return (
                <TableRow key={r.id} data-testid={`req-row-${r.id}`} className="cursor-pointer" onClick={() => setDetail(r)}>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{r.request_no}</div>
                    <div className="text-[10px] text-muted-foreground">{(r.created_at || "").slice(0, 10)} · {r.created_by}</div>
                  </TableCell>
                  <TableCell><div className="font-semibold text-sm">{r.project_code}</div>
                    <div className="text-[11px] text-muted-foreground truncate max-w-[160px]">{r.project_name}</div></TableCell>
                  <TableCell>
                    <Badge variant="outline" className="rounded-sm text-[10px]">{r.request_type_label}</Badge>
                    <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1"><DIcon className="h-3 w-3" /> {r.owning_dept}</div>
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-sm font-bold">{inr(r.est_value)}
                    {r.is_large_value && <div className="text-[9px] text-amber-700 font-sans font-bold uppercase">Large</div>}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 flex-wrap">
                      {(r.chain || []).map((s, i) => (
                        <span key={i} title={`${s.label}: ${s.status}`}
                          className={`inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-sm border
                            ${s.status === "approved" ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                              : s.status === "rejected" ? "bg-rose-50 border-rose-300 text-rose-800"
                              : i === r.current_step && r.status === "pending_approval" ? "bg-amber-50 border-amber-300 text-amber-900"
                              : "bg-secondary border-border text-muted-foreground"}`}>
                          {s.status === "approved" ? <CheckCircle2 className="h-2.5 w-2.5" /> : s.status === "rejected" ? <XCircle className="h-2.5 w-2.5" /> : <Clock className="h-2.5 w-2.5" />}
                          {s.label}
                        </span>
                      ))}
                    </div>
                    {r.pr_number && <div className="text-[10px] text-violet-700 font-mono-data mt-0.5">PR: {r.pr_number}</div>}
                  </TableCell>
                  <TableCell><Badge variant="outline" className={`rounded-sm ${(STATUS[r.status] || [])[1]}`}>{(STATUS[r.status] || [r.status])[0]}</Badge></TableCell>
                  <TableCell className="text-right"><Button size="sm" variant="ghost" className="h-7" onClick={(e) => { e.stopPropagation(); setDetail(r); }} data-testid={`req-open-${r.id}`}>Open</Button></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Raise dialog */}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Raise Project Request</DialogTitle>
            <DialogDescription>Approved by Project Head (+ GM → Director for large value), then routed to the owning department.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-1">
            <ProjectSelect label="Project *" value={form.project_code} onChange={(code, row) => setForm({ ...form, project_code: code, project_id: row?.id || "" })} testid="req-form-project" />
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Request Type *</Label>
              <select value={form.request_type} onChange={(e) => { setForm({ ...form, request_type: e.target.value }); setStock(null); }}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-type">
                <option value="">— select —</option>
                {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Need By</Label>
              <Input type="date" value={form.need_by} onChange={(e) => setForm({ ...form, need_by: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-form-needby" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Priority</Label>
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1">
                <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
              </select>
            </div>

            {/* Items (stockable / material types) */}
            {(isStockable || form.request_type === "") && form.request_type !== "" && (
              <div className="col-span-2 border border-border rounded-sm">
                <div className="flex items-center justify-between p-2 border-b border-border">
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Items</div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={runStockCheck} data-testid="req-stock-check"><PackageSearch className="h-3 w-3 mr-1" /> Check Stock</Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: [...form.items, blankItem()] })} data-testid="req-add-item"><Plus className="h-3 w-3 mr-1" /> Add</Button>
                  </div>
                </div>
                <div className="p-2 space-y-1.5">
                  {form.items.map((it, i) => {
                    const sl = stock?.lines?.[i];
                    return (
                      <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
                        <Input value={it.name} onChange={(e) => setItem(i, { name: e.target.value })} placeholder="Item name" className="h-8 rounded-sm col-span-4 text-xs" data-testid={`req-item-name-${i}`} />
                        <Input type="number" value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} placeholder="Qty" className="h-8 rounded-sm col-span-2 text-xs tabular" data-testid={`req-item-qty-${i}`} />
                        <Input value={it.unit} onChange={(e) => setItem(i, { unit: e.target.value })} placeholder="Unit" className="h-8 rounded-sm col-span-2 text-xs" />
                        <Input type="number" value={it.rate} onChange={(e) => setItem(i, { rate: e.target.value })} placeholder="Rate" className="h-8 rounded-sm col-span-2 text-xs tabular" />
                        <div className="col-span-2 text-[10px]">
                          {sl ? (sl.in_stock ? <span className="text-emerald-700 font-bold">In stock ({sl.on_hand})</span> : <span className="text-amber-700 font-bold">Short {sl.shortfall}</span>) : <span className="text-muted-foreground">—</span>}
                        </div>
                      </div>
                    );
                  })}
                  {stock && (
                    <div className={`text-[11px] mt-1 p-1.5 rounded-sm ${stock.all_in_stock ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`} data-testid="req-stock-result">
                      {stock.all_in_stock ? "✓ All items available in Store — will route to Stores for issue." : "⚠ Some items short — after approval you can raise a Purchase Request for the shortfall."}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Vehicle / accommodation / payment fields */}
            {isVehicle && (
              <>
                <div><Label className="text-[10px] uppercase tracking-wider">Vehicle Type / Ref</Label>
                  <Input value={form.vehicle_ref} onChange={(e) => setForm({ ...form, vehicle_ref: e.target.value })} placeholder={form.request_type === "vehicle_material" ? "Big Truck / Small Truck" : "Car / Bus / Winger / Magic"} className="h-9 rounded-sm mt-1" data-testid="req-form-vehicle" /></div>
                <div><Label className="text-[10px] uppercase tracking-wider">Vendor</Label>
                  <Input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-form-vendor" /></div>
              </>
            )}
            {form.request_type === "one_time_vehicle" && (
              <>
                <div><Label className="text-[10px] uppercase tracking-wider">From Location</Label>
                  <Input value={form.from_location} onChange={(e) => setForm({ ...form, from_location: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-form-from" /></div>
                <div><Label className="text-[10px] uppercase tracking-wider">To Location / Godown</Label>
                  <Input value={form.to_location} onChange={(e) => setForm({ ...form, to_location: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-form-to" /></div>
              </>
            )}
            {(form.request_type === "vehicle_manpower" || form.request_type === "vehicle_material" || form.request_type === "accommodation") && (
              <>
                <div><Label className="text-[10px] uppercase tracking-wider">Monthly Rate (₹)</Label>
                  <Input type="number" value={form.monthly_rate} onChange={(e) => setForm({ ...form, monthly_rate: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="req-form-monthly" /></div>
                <div><Label className="text-[10px] uppercase tracking-wider">No. of Months</Label>
                  <Input type="number" value={form.months} onChange={(e) => setForm({ ...form, months: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="req-form-months" /></div>
              </>
            )}
            {(form.request_type === "fuel" || form.request_type === "insurance" || form.request_type === "one_time_vehicle" || form.request_type === "accommodation") && (
              <div><Label className="text-[10px] uppercase tracking-wider">{form.request_type === "accommodation" ? "One-time / Deposit Amount (₹)" : "Amount (₹)"}</Label>
                <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="req-form-amount" /></div>
            )}
            {isPayment && form.request_type !== "one_time_vehicle" && !isVehicle && form.request_type !== "accommodation" && (
              <div><Label className="text-[10px] uppercase tracking-wider">Vendor / Paid To</Label>
                <Input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-form-vendor2" /></div>
            )}

            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Description / Justification *</Label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-sm mt-1 min-h-[56px]" data-testid="req-form-desc" /></div>

            <div className="col-span-2 flex items-center justify-between bg-muted/30 border border-border rounded-sm p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Estimated Value</div>
              <div className="font-mono-data tabular text-lg font-black text-emerald-700" data-testid="req-form-est">{inr(estValue)}</div>
            </div>

            <div className="col-span-2"><Label className="text-[10px] uppercase tracking-wider">Attachments (quotes, specs, photos)</Label>
              <div className="mt-1"><FileUploader folder="documents" parent_type="project_requests" parent_id={form.id} category="request_support" compact
                files={attFiles} onUploaded={(f) => setAttFiles((p) => [...p, f])} onDeleted={(fid) => setAttFiles((p) => p.filter((x) => x.id !== fid))} testidPrefix="req-uploader" /></div></div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setCreating(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={create} data-testid="req-form-submit">Raise Request</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail / action dialog */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl rounded-sm max-h-[88vh] overflow-y-auto">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="font-display flex items-center gap-2">{detail.request_no} · {detail.request_type_label}</DialogTitle>
                <DialogDescription>{detail.project_code} — {detail.project_name} · routed to <b>{detail.owning_dept}</b></DialogDescription>
              </DialogHeader>
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-3 gap-2">
                  {[["Status", (STATUS[detail.status] || [detail.status])[0]], ["Est. Value", inr(detail.est_value)],
                    ["Priority", detail.priority], ["Need By", detail.need_by || "—"], ["Vendor", detail.vendor || "—"],
                    ["Raised By", detail.created_by]].map(([k, v]) => (
                    <div key={k} className="border border-border rounded-sm p-2"><div className="text-[10px] uppercase text-muted-foreground">{k}</div><div className="font-semibold text-xs">{v}</div></div>
                  ))}
                </div>
                {detail.description && <div className="text-xs bg-muted/30 rounded-sm p-2">{detail.description}</div>}
                {(detail.items || []).length > 0 && (
                  <div className="border border-border rounded-sm">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-primary p-2 border-b">Items {detail.is_stockable ? "(stock checked)" : ""}</div>
                    <table className="w-full text-xs">
                      <tbody>
                        {detail.items.map((it, i) => {
                          const sl = (detail.stock_lines || [])[i];
                          return <tr key={i} className="border-b border-border/50"><td className="p-1.5">{it.name}</td><td className="p-1.5 tabular">{it.quantity} {it.unit}</td>
                            <td className="p-1.5 text-right">{sl ? (sl.in_stock ? <span className="text-emerald-700">In stock ({sl.on_hand})</span> : <span className="text-amber-700">Short {sl.shortfall}</span>) : ""}</td></tr>;
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="flex items-center gap-1 flex-wrap">
                  {(detail.chain || []).map((s, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-sm border ${s.status === "approved" ? "bg-emerald-50 border-emerald-300 text-emerald-800" : s.status === "rejected" ? "bg-rose-50 border-rose-300 text-rose-800" : "bg-secondary border-border text-muted-foreground"}`}>
                      {s.label}{s.by ? ` · ${s.by}` : ""}</span>
                  ))}
                </div>
                {detail.pr_number && <div className="text-xs text-violet-700">Purchase Request raised: <b>{detail.pr_number}</b></div>}
                {detail.expense_id && <div className="text-xs text-blue-700">Payment booked to Daily Expenses — Accounts will process with proof.</div>}
              </div>
              <DialogFooter className="flex-wrap gap-2">
                {detail.status === "pending_approval" && (user?.role === (detail.chain || [])[detail.current_step]?.role || user?.role === "super_admin") && (
                  <>
                    <Button className="rounded-sm" onClick={() => act(detail, "approve", false)} data-testid="req-approve">Approve</Button>
                    <Button variant="outline" className="rounded-sm text-destructive" onClick={() => act(detail, "reject", true)} data-testid="req-reject">Reject</Button>
                  </>
                )}
                {detail.status === "with_dept" && detail.is_stockable && (detail.stock_lines || []).some((l) => l.shortfall > 0) && (
                  <Button variant="outline" className="rounded-sm" onClick={() => raisePR(detail)} data-testid="req-raise-pr"><ShoppingCart className="h-4 w-4 mr-1.5" /> Raise Purchase Request</Button>
                )}
                {(detail.status === "with_dept" || detail.status === "pr_raised") && (
                  <Button className="rounded-sm" onClick={() => act(detail, "fulfil", true)} data-testid="req-fulfil"><CheckCircle2 className="h-4 w-4 mr-1.5" /> Mark Fulfilled</Button>
                )}
                {detail.status === "fulfilled" && (
                  <Button variant="outline" className="rounded-sm" onClick={() => act(detail, "close", false)} data-testid="req-close">Close Request</Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
