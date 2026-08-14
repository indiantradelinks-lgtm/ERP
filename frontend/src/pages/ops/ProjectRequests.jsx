import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Plus, RefreshCw, PackageSearch, CheckCircle2, XCircle, Clock, FileSpreadsheet, FileText, Boxes, ShoppingCart, Truck, Home, Users, ChevronDown, ChevronRight, CalendarDays, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect, SiteLocationSelect } from "@/components/MasterSelect";
import { EmployeeSearchSelect } from "@/components/EmployeeSearchSelect";
import FileUploader from "@/components/FileUploader";
import RowAttachments from "@/components/RowAttachments";
import useAutoSync from "@/hooks/useAutoSync";
import ProjectExpenses from "./ProjectExpenses";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const RAISE_ROLES = new Set(["project_coordinator", "project_manager", "super_admin", "manager_o_p", "manager_op",
  "manager_pnv", "manager_p_n_v", "manager_log", "manager_l_o_g"]);
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
const STOCKABLE = new Set(["material", "ppe", "it_material"]);
const blankItem = () => ({ name: "", quantity: 1, unit: "Nos", rate: 0, specs: "", size: "", make: "", item_type: "", tech_details: "", designation_id: "", item_id: "", item_code: "", custom: false });
const blank = () => ({ id: newId(), project_code: "", project_id: "", request_type: "", need_by: "",
  priority: "medium", description: "", items: [blankItem()], vendor: "", vehicle_ref: "",
  period_from: "", period_to: "", monthly_rate: "", months: "", from_location: "", to_location: "", amount: "", remarks: "",
  cost_center_id: "", site_location: "", material_category_id: "", employee_id: "",
  expense_type: "", expense_date: new Date().toISOString().slice(0, 10), settlement_mode: "vendor_payable", paid_to_type: "vendor" });

const PAY_STAGE = {
  pending_verification: ["Accounts: Pending Verification", "border-amber-300 text-amber-900 bg-amber-50"],
  verified: ["Accounts: Verified", "border-blue-300 text-blue-900 bg-blue-50"],
  rejected: ["Accounts: Rejected", "border-rose-300 text-rose-900 bg-rose-50"],
  in_bank_file: ["Accounts: In Bank File", "border-violet-300 text-violet-900 bg-violet-50"],
  paid: ["Paid by Accounts", "border-emerald-300 text-emerald-900 bg-emerald-50"],
};

const STATUS = {
  pending_approval: ["Pending Approval", "border-amber-300 text-amber-900 bg-amber-50"],
  with_dept: ["With Department", "border-blue-300 text-blue-900 bg-blue-50"],
  pr_raised: ["PR Raised", "border-violet-300 text-violet-900 bg-violet-50"],
  sourcing: ["Sourcing (Recruitment)", "border-orange-300 text-orange-900 bg-orange-50"],
  fulfilled: ["Fulfilled", "border-emerald-300 text-emerald-900 bg-emerald-50"],
  closed: ["Closed", "border-slate-300 text-slate-700 bg-slate-50"],
  rejected: ["Rejected", "border-rose-300 text-rose-900 bg-rose-50"],
};
const DEPT_ICON = { stores: Boxes, logistics: Truck, admin: Home, hr: Users };

export default function ProjectRequests() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canRaise = RAISE_ROLES.has(user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "expenses" ? "expenses" : "requests";
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [types, setTypes] = useState([]);
  const [filters, setFilters] = useState({ project_code: "", status: "", request_type: "", dept: "" });
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(blank());
  const [attFiles, setAttFiles] = useState([]);
  const [stock, setStock] = useState(null);
  const [detail, setDetail] = useState(null);
  const [attachFor, setAttachFor] = useState(null);
  const [ccList, setCcList] = useState([]);
  const [employees, setEmployees] = useState([]);

  useEffect(() => {
    api.get("/advances/eligible-employees")
      .then((r) => setEmployees(r.data?.employees || []))
      .catch(() => setEmployees([]));
  }, []);

  const projectEmployees = useMemo(() => {
    if (!form.project_code) return employees;
    return employees.filter((e) => e.current_project_code === form.project_code);
  }, [employees, form.project_code]);
  const selectedEmp = employees.find((e) => e.id === form.employee_id);
  const [designations, setDesignations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [catItems, setCatItems] = useState([]);
  const [expTypes, setExpTypes] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [mode, setMode] = useState("material");
  const [parsing, setParsing] = useState(false);

  const meta = useMemo(() => types.find((t) => t.key === form.request_type), [types, form.request_type]);
  const isStockable = form.request_type && STOCKABLE.has(form.request_type);
  const isManpower = form.request_type === "manpower";
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
  useEffect(() => { api.get("/ops/resource-requests/meta/designations").then((r) => setDesignations(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { api.get("/procurement/master/categories").then((r) => setCategories(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { api.get("/project-expenses/types").then((r) => setExpTypes(r.data || [])).catch(() => {}); }, []);
  useEffect(() => {
    api.get("/vendors").then((r) => setVendors((r.data || []).filter((v) => v.status === "approved"))).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [filters]); // eslint-disable-line
  useAutoSync(load);
  useEffect(() => {
    if (searchParams.get("new") === "service" && canRaise) {
      openDialog("service");
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams]); // eslint-disable-line

  const onCategoryChange = (catId) => {
    const cat = categories.find((c) => c.id === catId);
    const cc = catId ? ccList.find((c) => c.category_id === catId || (cat && c.category_code === cat.code)) : null;
    setForm((f) => ({ ...f, material_category_id: catId, cost_center_id: f.cost_center_id || (cc ? cc.id : ""), items: [blankItem()] }));
    setStock(null);
    if (catId) {
      api.get("/procurement/master/items", { params: { category_id: catId } }).then((r) => setCatItems(r.data || [])).catch(() => setCatItems([]));
    } else setCatItems([]);
  };

  const onServiceCategoryChange = (catId) => {
    const cat = categories.find((c) => c.id === catId);
    const cc = catId ? ccList.find((c) => c.category_id === catId || (cat && c.category_code === cat.code)) : null;
    setForm((f) => ({ ...f, material_category_id: catId, cost_center_id: cc ? cc.id : f.cost_center_id }));
  };

  // Auto-populate cost center from selected category once project cost centers load
  useEffect(() => {
    if (!form.material_category_id || form.cost_center_id || !ccList.length) return;
    const cat = categories.find((c) => c.id === form.material_category_id);
    const cc = ccList.find((c) => c.category_id === form.material_category_id || (cat && c.category_code === cat.code));
    if (cc) setForm((f) => ({ ...f, cost_center_id: f.cost_center_id || cc.id }));
  }, [ccList, form.material_category_id]); // eslint-disable-line

  const loadCostCenters = (projectId) => {
    if (!projectId) { setCcList([]); return; }
    api.get("/procurement/master/cost-centers", { params: { project_id: projectId } }).then((r) => setCcList(r.data || [])).catch(() => setCcList([]));
  };

  const openDialog = (m) => {
    setMode(m);
    setForm({ ...blank(), request_type: m === "material" ? "material" : m === "manpower" ? "manpower" : "" });
    setAttFiles([]); setStock(null); setCcList([]); setCatItems([]); setCreating(true);
  };

  const downloadMatTemplate = async () => {
    try {
      const { data } = await api.get("/project-requests/material-template", { responseType: "blob" });
      const url = URL.createObjectURL(data); const a = document.createElement("a");
      a.href = url; a.download = "material_request_template.csv"; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Template download failed"); }
  };

  const importFile = async (file, aiMode) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setParsing(true);
    try {
      const { data } = await api.post(`/project-requests/import-items?mode=${aiMode ? "ai" : "template"}`, fd,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
      if (!data.items?.length) { toast.warning("No item lines found in the file"); return; }
      const parsed = data.items.map((d) => ({ ...blankItem(), ...d, custom: true }));
      setForm((f) => {
        const existing = f.items.filter((x) => (x.name || "").trim());
        return { ...f, items: [...existing, ...parsed] };
      });
      toast.success(`${data.count} item line(s) ${aiMode ? "extracted by AI" : "imported"} — review before submitting`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Import failed"); }
    finally { setParsing(false); }
  };

  const estValue = useMemo(() => {
    if (form.amount) return Number(form.amount);
    if (form.monthly_rate) return Number(form.monthly_rate) * Number(form.months || 1);
    const itemsTotal = (form.items || []).reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0);
    if (form.request_type === "manpower" && Number(form.months)) return itemsTotal * Number(form.months);
    return itemsTotal;
  }, [form]);

  const setItem = (i, patch) => setForm((f) => ({ ...f, items: f.items.map((x, ix) => ix === i ? { ...x, ...patch } : x) }));

  const runStockCheck = async () => {
    try {
      const payload = {
        request_type: form.request_type,
        items: form.items.map((i) => ({ ...i, quantity: Number(i.quantity) || 0, rate: Number(i.rate) || 0 })),
      };
      const r = await api.post("/project-requests/stock-check", payload);
      setStock(r.data);
      if (r.data.all_in_stock) toast.success("All items in stock — will route to Stores");
      else if (r.data.any_short) toast.warning("Some items short — you can raise a Purchase Request after approval");
    } catch { toast.error("Stock check failed"); }
  };

  const create = async () => {
    if (!form.project_code) { toast.error("Select a project"); return; }
    if (!form.request_type) { toast.error("Select request type"); return; }
    if (isManpower && !form.items.some((i) => i.name && Number(i.quantity) > 0)) { toast.error("Add at least one manpower line"); return; }
    if (isStockable && !form.items.some((i) => (i.name || "").trim() && Number(i.quantity) > 0)) { toast.error("Add at least one item"); return; }
    if (estValue <= 0 && !isStockable && !isManpower) { toast.error("Enter amount / rate"); return; }
    if (isPayment && mode === "service") {
      if (form.paid_to_type === "vendor" && !form.vendor) { toast.error("Select the approved vendor to be paid"); return; }
      if (form.paid_to_type === "person" && !form.employee_id) { toast.error("Select the employee (Emp ID) to be paid"); return; }
      if (!form.expense_date) { toast.error("Select expense date"); return; }
    }
    try {
      const payload = { ...form,
        amount: form.amount ? Number(form.amount) : null,
        monthly_rate: form.monthly_rate ? Number(form.monthly_rate) : null,
        months: form.months ? Number(form.months) : null,
        items: form.items.filter((i) => (i.name || "").trim())
          .map((i) => ({ ...i, quantity: Number(i.quantity) || 0, rate: Number(i.rate) || 0,
                         unit_weight_kg: Number(i.unit_weight_kg) || 0 })) };
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

  const raiseRecruitment = async (r) => {
    try { const res = await api.post(`/project-requests/${r.id}/raise-recruitment`); toast.success(`Recruitment raised: ${res.data.recruitment_nos.join(", ")}`); load(); setDetail(null); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const fulfilLine = async (r, idx) => {
    const remarks = window.prompt("Fulfilment note (optional)");
    try {
      const res = await api.post(`/project-requests/${r.id}/items/${idx}/fulfil`, { mode: "stock", remarks });
      toast.success(res.data.status === "fulfilled" ? "All lines done — request fulfilled" : "Line fulfilled");
      setDetail(res.data); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
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
          <h1 className="font-display font-black text-3xl tracking-tight">Project Request Center</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            One place for every project need — Material, PPE, IT, Manpower, Accommodation, Fuel, Insurance, Vehicles
            &amp; Expense Booking. Stock is auto-checked; shortfalls become Purchase Requests; each request routes to its
            linked department for fulfilment.
          </p>
        </div>
        {tab === "requests" && (
          <div className="flex gap-2">
            <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="req-reload"><RefreshCw className="h-4 w-4" /></Button>
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="req-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Excel</Button>
            <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="req-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> PDF</Button>
            {canRaise && (
              <>
                <Button className="h-9 rounded-sm" onClick={() => openDialog("material")} data-testid="req-new-material">
                  <Boxes className="h-4 w-4 mr-1.5" /> Material Request
                </Button>
                <Button variant="outline" className="h-9 rounded-sm" onClick={() => openDialog("manpower")} data-testid="req-new-manpower">
                  <Users className="h-4 w-4 mr-1.5" /> Manpower Request
                </Button>
                <Button variant="outline" className="h-9 rounded-sm" onClick={() => openDialog("service")} data-testid="req-new-service">
                  <Truck className="h-4 w-4 mr-1.5" /> Service / Payment
                </Button>
                <Button variant="outline" className="h-9 rounded-sm" onClick={() => navigate("/app/hr/leave")} data-testid="req-shortcut-leave">
                  <CalendarDays className="h-4 w-4 mr-1.5" /> Leave Apply
                </Button>
                <Button variant="outline" className="h-9 rounded-sm" onClick={() => navigate("/app/hr/advances")} data-testid="req-shortcut-advance">
                  <Wallet className="h-4 w-4 mr-1.5" /> Advance Request
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      <Tabs value={tab} onValueChange={(v) => setSearchParams(v === "expenses" ? { tab: "expenses" } : {})}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="requests" className="rounded-sm" data-testid="prc-tab-requests">Resource Requests</TabsTrigger>
          <TabsTrigger value="expenses" className="rounded-sm" data-testid="prc-tab-expenses">Expense Booking</TabsTrigger>
        </TabsList>
        <TabsContent value="expenses" className="mt-4">
          <ProjectExpenses embedded />
        </TabsContent>
        <TabsContent value="requests" className="mt-4 space-y-5">

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
                    <div className="text-[10px] text-muted-foreground whitespace-nowrap" data-testid={`req-created-${r.id}`}>{(r.created_at || "").slice(0, 16).replace("T", " ")}</div>
                    <div className="text-[10px] text-muted-foreground">{r.created_by}</div>
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
                  <TableCell>
                    <Badge variant="outline" className={`rounded-sm ${(STATUS[r.status] || [])[1]}`}>{(STATUS[r.status] || [r.status])[0]}</Badge>
                    {r.pay_stage && (
                      <div className="mt-1" data-testid={`req-paystage-${r.id}`}>
                        <Badge variant="outline" className={`rounded-sm text-[9px] ${(PAY_STAGE[r.pay_stage] || [])[1]}`}>{(PAY_STAGE[r.pay_stage] || [r.pay_stage])[0]}</Badge>
                        {r.pay_info?.utr_no && <div className="text-[9px] font-mono-data text-muted-foreground mt-0.5">UTR {r.pay_info.utr_no}</div>}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right"><Button size="sm" variant="ghost" className="h-7" onClick={(e) => { e.stopPropagation(); setDetail(r); }} data-testid={`req-open-${r.id}`}>Open</Button></TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

        </TabsContent>
      </Tabs>

      {/* Raise dialog */}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-3xl rounded-sm max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">
              {mode === "material" ? "Material Request" : mode === "manpower" ? "Manpower Request" : "Service / Payment Request"}
            </DialogTitle>
            <DialogDescription>
              {mode === "material" ? "Stock is checked first; shortfall converts to a Purchase Request after approval. Routed to Stores." :
               mode === "manpower" ? "Routed to HR for fulfilment after Project Head approval." :
               "Approved by Project Head (+ GM → Director for large value), then routed to the owning department."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-1">
            <ProjectSelect label="Project *" value={form.project_code} onChange={(code, row) => { setForm({ ...form, project_code: code, project_id: row?.id || "", cost_center_id: "", employee_id: "" }); loadCostCenters(row?.id); }} testid="req-form-project" />
            {mode === "service" && (
              <>
                <div>
                  <Label className="text-[10px] uppercase tracking-wider">Category (Item Master) *</Label>
                  <select value={form.material_category_id} onChange={(e) => onServiceCategoryChange(e.target.value)}
                    className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-service-category">
                    <option value="">— select category —</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
                  </select>
                </div>
                <div>
                  <Label className="text-[10px] uppercase tracking-wider">Request Type (Routing) *</Label>
                  <select value={form.request_type} onChange={(e) => { setForm({ ...form, request_type: e.target.value, items: [blankItem()] }); setStock(null); }}
                    className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-type">
                    <option value="">— select —</option>
                    {types.filter((t) => !STOCKABLE.has(t.key) && t.key !== "manpower").map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                  </select>
                </div>
                <div>
                  <Label className="text-[10px] uppercase tracking-wider">Paid To *</Label>
                  <select value={form.paid_to_type} onChange={(e) => setForm({ ...form, paid_to_type: e.target.value, vendor: "", employee_id: "" })}
                    className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-paidto-type">
                    <option value="vendor">Vendor (from Vendor Master)</option>
                    <option value="person">Person (Employee / Worker)</option>
                  </select>
                </div>
                {form.paid_to_type === "vendor" ? (
                  <div>
                    <Label className="text-[10px] uppercase tracking-wider">Vendor (approved) *</Label>
                    <select value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })}
                      className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-vendor-select">
                      <option value="">— select approved vendor —</option>
                      {vendors.map((v) => <option key={v.id} value={v.name}>{v.name}</option>)}
                    </select>
                    {vendors.length === 0 && <p className="text-[10px] text-amber-700 mt-0.5">No approved vendors in Vendor Master.</p>}
                  </div>
                ) : (
                  <div className="text-[10px] text-muted-foreground self-end pb-2">Select the person via Emp ID below — name auto-fills from HR master.</div>
                )}
                <EmployeeSearchSelect
                  label={`Emp ID${form.paid_to_type === "person" ? " *" : ""}${form.project_code ? ` (${projectEmployees.length} in project)` : ""}`}
                  employees={projectEmployees}
                  value={form.employee_id}
                  onChange={(id) => setForm({ ...form, employee_id: id })}
                  placeholder={form.project_code ? "Search by ID / name…" : "Select project first…"}
                  testid="req-form-employee"
                />
                <div>
                  <Label className="text-[10px] uppercase tracking-wider">Employee Name</Label>
                  <Input value={selectedEmp?.name || ""} readOnly disabled placeholder="Auto-filled from Emp ID"
                    className="h-9 rounded-sm mt-1 bg-muted/40" data-testid="req-form-employee-name" />
                </div>
                {isPayment && (
                  <>
                    <div>
                      <Label className="text-[10px] uppercase tracking-wider">Expense Type *</Label>
                      <select value={form.expense_type} onChange={(e) => setForm({ ...form, expense_type: e.target.value })}
                        className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-expense-type">
                        <option value="">— auto (from routing) —</option>
                        {expTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                      </select>
                    </div>
                    <div>
                      <Label className="text-[10px] uppercase tracking-wider">Expense Date *</Label>
                      <Input type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })}
                        className="h-9 rounded-sm mt-1" data-testid="req-form-expense-date" />
                    </div>
                    <div>
                      <Label className="text-[10px] uppercase tracking-wider">Settlement *</Label>
                      <select value={form.settlement_mode} onChange={(e) => setForm({ ...form, settlement_mode: e.target.value })}
                        className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-settlement">
                        <option value="vendor_payable">Vendor Payable</option>
                        <option value="petty_cash">Petty Cash</option>
                        <option value="employee_reimbursement">Employee Reimbursement</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                  </>
                )}
              </>
            )}
            {mode === "material" && (
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Category (Item Master) *</Label>
                <select value={form.material_category_id} onChange={(e) => onCategoryChange(e.target.value)}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-material-category">
                  <option value="">— select category —</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}{c.item_count ? ` (${c.item_count} items)` : ""}</option>)}
                </select>
              </div>
            )}
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Cost Center</Label>
              <select value={form.cost_center_id} onChange={(e) => setForm({ ...form, cost_center_id: e.target.value })}
                className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="req-form-costcenter">
                <option value="">— auto (project default) —</option>
                {ccList.map((cc) => <option key={cc.id} value={cc.id}>{cc.category_code} · {cc.category_name}{cc.budget ? ` (budget ${inr(cc.budget)})` : ""}</option>)}
              </select>
            </div>
            <SiteLocationSelect label="Site Location" value={form.site_location}
              onChange={(v) => setForm({ ...form, site_location: v })} testid="req-form-location" />
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

            {/* Items (material requests) */}
            {isStockable && (
              <div className="col-span-2 border border-border rounded-sm">
                <div className="flex items-center justify-between p-2 border-b border-border flex-wrap gap-1.5">
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Items</div>
                  <div className="flex gap-1.5 flex-wrap">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={downloadMatTemplate} data-testid="req-mat-template"><FileSpreadsheet className="h-3 w-3 mr-1" /> Template</Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" disabled={parsing}
                      onClick={() => document.getElementById("req-bulk-file").click()} data-testid="req-bulk-upload">
                      {parsing ? "Reading…" : "Bulk Upload"}
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm border-primary/40 text-primary" disabled={parsing}
                      onClick={() => document.getElementById("req-ai-file").click()} data-testid="req-ai-upload">
                      {parsing ? "AI reading…" : "✨ AI Read Excel"}
                    </Button>
                    <input id="req-bulk-file" type="file" accept=".csv,.xlsx,.xlsm" className="hidden"
                      onChange={(e) => { importFile(e.target.files?.[0], false); e.target.value = ""; }} data-testid="req-bulk-file-input" />
                    <input id="req-ai-file" type="file" accept=".csv,.xlsx,.xlsm" className="hidden"
                      onChange={(e) => { importFile(e.target.files?.[0], true); e.target.value = ""; }} data-testid="req-ai-file-input" />
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={runStockCheck} data-testid="req-stock-check"><PackageSearch className="h-3 w-3 mr-1" /> Check Stock</Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: [...form.items, blankItem()] })} data-testid="req-add-item"><Plus className="h-3 w-3 mr-1" /> Add</Button>
                  </div>
                </div>
                <div className="p-2 space-y-1.5">
                  {form.items.map((it, i) => {
                    const sl = stock?.lines?.[i];
                    const totalW = (Number(it.quantity) || 0) * (Number(it.unit_weight_kg) || 0);
                    return (
                      <div key={i} className="space-y-1 pb-1.5 border-b border-border/40 last:border-0">
                        <div className="grid grid-cols-12 gap-1.5 items-center">
                          {catItems.length > 0 && !it.custom ? (
                            <select value={it.item_id || ""} onChange={(e) => {
                              const v = e.target.value;
                              if (v === "__custom") { setItem(i, { item_id: "", item_code: "", name: "", custom: true }); return; }
                              const m = catItems.find((x) => x.id === v);
                              setItem(i, m ? { item_id: m.id, item_code: m.code, name: m.name, unit: m.unit || "Nos", rate: m.last_rate || 0, unit_weight_kg: m.unit_weight_kg || it.unit_weight_kg, custom: false } : { item_id: "", item_code: "", name: "" });
                            }} className="h-8 rounded-sm border border-input bg-background px-2 text-xs col-span-4" data-testid={`req-item-select-${i}`}>
                              <option value="">— item from master —</option>
                              {catItems.map((m) => <option key={m.id} value={m.id}>{m.name} · {m.code}{m.stock_qty ? ` (stock ${m.stock_qty})` : ""}</option>)}
                              <option value="__custom">Other / type manually…</option>
                            </select>
                          ) : (
                            <Input value={it.name} onChange={(e) => setItem(i, { name: e.target.value })} placeholder="Item name" className="h-8 rounded-sm col-span-4 text-xs" data-testid={`req-item-name-${i}`} />
                          )}
                          <Input type="number" value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} placeholder="Qty" className="h-8 rounded-sm col-span-2 text-xs tabular" data-testid={`req-item-qty-${i}`} />
                          <Input value={it.unit} onChange={(e) => setItem(i, { unit: e.target.value })} placeholder="Unit" className="h-8 rounded-sm col-span-2 text-xs" />
                          <Input type="number" value={it.rate} onChange={(e) => setItem(i, { rate: e.target.value })} placeholder="Rate ₹" className="h-8 rounded-sm col-span-2 text-xs tabular" />
                          <div className="col-span-2 text-[10px]">
                            {sl ? (sl.in_stock ? <span className="text-emerald-700 font-bold">In stock ({sl.on_hand})</span> : <span className="text-amber-700 font-bold">Short {sl.shortfall}</span>) : <span className="text-muted-foreground">—</span>}
                          </div>
                        </div>
                        <div className="grid grid-cols-12 gap-1.5 items-center">
                          <Input value={it.size || ""} onChange={(e) => setItem(i, { size: e.target.value })} placeholder="Size" className="h-8 rounded-sm col-span-2 text-xs" data-testid={`req-item-size-${i}`} />
                          <Input value={it.material || ""} onChange={(e) => setItem(i, { material: e.target.value })} placeholder="Material (MS/GI…)" className="h-8 rounded-sm col-span-2 text-xs" data-testid={`req-item-material-${i}`} />
                          <Input value={it.make || ""} onChange={(e) => setItem(i, { make: e.target.value })} placeholder="Make" className="h-8 rounded-sm col-span-2 text-xs" data-testid={`req-item-make-${i}`} />
                          <Input value={it.coating || ""} onChange={(e) => setItem(i, { coating: e.target.value })} placeholder="Coating" className="h-8 rounded-sm col-span-2 text-xs" data-testid={`req-item-coating-${i}`} />
                          <Input value={it.item_type || ""} onChange={(e) => setItem(i, { item_type: e.target.value })} placeholder="Type" className="h-8 rounded-sm col-span-2 text-xs" data-testid={`req-item-type-${i}`} />
                          <Input type="number" value={it.unit_weight_kg || ""} onChange={(e) => setItem(i, { unit_weight_kg: e.target.value })} placeholder="Unit wt kg" className="h-8 rounded-sm col-span-1 text-xs tabular" data-testid={`req-item-uwt-${i}`} />
                          <div className="col-span-1 text-[10px] text-right font-mono-data tabular" data-testid={`req-item-twt-${i}`}>{totalW ? `${totalW.toFixed(1)}kg` : "—"}</div>
                        </div>
                      </div>
                    );
                  })}
                  <div className="flex justify-end gap-4 text-[11px] font-bold border-t border-border pt-1.5" data-testid="req-items-totals">
                    <span>Total Qty: <span className="font-mono-data tabular">{form.items.reduce((a, i) => a + (Number(i.quantity) || 0), 0)}</span></span>
                    <span>Total Weight: <span className="font-mono-data tabular">{form.items.reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.unit_weight_kg) || 0), 0).toFixed(1)} kg</span></span>
                    <span>Est. Value: <span className="font-mono-data tabular">{inr(estValue)}</span></span>
                  </div>
                  {stock && (
                    <div className={`text-[11px] mt-1 p-1.5 rounded-sm ${stock.all_in_stock ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`} data-testid="req-stock-result">
                      {stock.all_in_stock ? "✓ All items available in Store — will route to Stores for issue." : "⚠ Some items short — after approval you can raise a Purchase Request for the shortfall."}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Manpower lines */}
            {isManpower && (
              <>
                <div className="col-span-2 border border-border rounded-sm">
                  <div className="flex items-center justify-between p-2 border-b border-border">
                    <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Manpower Lines (routed to HR)</div>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setForm({ ...form, items: [...form.items, blankItem()] })} data-testid="req-add-manpower"><Plus className="h-3 w-3 mr-1" /> Add</Button>
                  </div>
                  <div className="p-2 space-y-1.5">
                    {form.items.map((it, i) => (
                      <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
                        <select value={it.designation_id || ""} onChange={(e) => {
                          const d = designations.find((x) => x.id === e.target.value);
                          setItem(i, { designation_id: e.target.value, name: d ? d.name : it.name });
                        }} className="h-8 rounded-sm border border-input bg-background px-2 text-xs col-span-3" data-testid={`req-mp-desig-${i}`}>
                          <option value="">— designation —</option>
                          {designations.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                        </select>
                        <Input value={it.name} onChange={(e) => setItem(i, { name: e.target.value })} placeholder="or type designation" className="h-8 rounded-sm col-span-3 text-xs" data-testid={`req-mp-name-${i}`} />
                        <Input type="number" value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} placeholder="Count" className="h-8 rounded-sm col-span-1 text-xs tabular" data-testid={`req-mp-count-${i}`} />
                        <Input type="number" value={it.rate || ""} onChange={(e) => setItem(i, { rate: e.target.value })} placeholder="₹/month/head" className="h-8 rounded-sm col-span-2 text-xs tabular" data-testid={`req-mp-rate-${i}`} />
                        <Input value={it.specs} onChange={(e) => setItem(i, { specs: e.target.value })} placeholder="Skills / certificates" className="h-8 rounded-sm col-span-3 text-xs" data-testid={`req-mp-skills-${i}`} />
                      </div>
                    ))}
                    <div className="flex justify-end gap-4 text-[11px] font-bold border-t border-border pt-1.5" data-testid="req-mp-budget">
                      <span>Headcount: <span className="font-mono-data tabular">{form.items.reduce((a, i) => a + (Number(i.quantity) || 0), 0)}</span></span>
                      <span>Monthly Budget: <span className="font-mono-data tabular">{inr(form.items.reduce((a, i) => a + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0))}</span></span>
                      <span>Total Budget ({form.months || 1} mo): <span className="font-mono-data tabular">{inr(estValue)}</span></span>
                    </div>
                  </div>
                </div>
                <div><Label className="text-[10px] uppercase tracking-wider">Required From</Label>
                  <Input type="date" value={form.period_from} onChange={(e) => setForm({ ...form, period_from: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-mp-from" /></div>
                <div><Label className="text-[10px] uppercase tracking-wider">Required Till</Label>
                  <Input type="date" value={form.period_to} onChange={(e) => setForm({ ...form, period_to: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="req-mp-to" /></div>
                <div><Label className="text-[10px] uppercase tracking-wider">Duration (months)</Label>
                  <Input type="number" value={form.months} onChange={(e) => setForm({ ...form, months: e.target.value })} placeholder="for budget calc" className="h-9 rounded-sm mt-1 tabular" data-testid="req-mp-months" /></div>
              </>
            )}

            {/* Vehicle / accommodation / payment fields */}
            {isVehicle && (
              <div><Label className="text-[10px] uppercase tracking-wider">Vehicle Type / Ref</Label>
                <Input value={form.vehicle_ref} onChange={(e) => setForm({ ...form, vehicle_ref: e.target.value })} placeholder={form.request_type === "vehicle_material" ? "Big Truck / Small Truck" : "Car / Bus / Winger / Magic"} className="h-9 rounded-sm mt-1" data-testid="req-form-vehicle" /></div>
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
            {(form.request_type === "fuel" || form.request_type === "insurance" || form.request_type === "one_time_vehicle" || form.request_type === "accommodation" || form.request_type === "other") && (
              <div><Label className="text-[10px] uppercase tracking-wider">{form.request_type === "accommodation" ? "One-time / Deposit Amount (₹)" : "Amount (₹)"}</Label>
                <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="h-9 rounded-sm mt-1 tabular" data-testid="req-form-amount" /></div>
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
              <div className="flex justify-end -mt-2">
                <Button size="sm" variant="outline" className="rounded-sm h-7" onClick={() => setAttachFor(detail)} data-testid="req-detail-attachments">
                  Attachments{detail.attachment_count ? ` (${detail.attachment_count})` : ""}
                </Button>
              </div>
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-3 gap-2">
                  {[["Status", (STATUS[detail.status] || [detail.status])[0]], ["Est. Value", inr(detail.est_value)],
                    ["Priority", detail.priority], ["Need By", detail.need_by || "—"],
                    ["Cost Center", detail.cost_center_label || "Auto (project default)"],
                    ["Site Location", detail.site_location || "—"],
                    ["Paid To", detail.paid_to_type === "person" ? `Person${detail.employee_name ? ` — ${detail.employee_name}` : ""}` : (detail.vendor ? `Vendor — ${detail.vendor}` : detail.vendor || "—")],
                    ...(detail.is_payment ? [
                      ["Expense Type", (expTypes.find((t) => t.key === detail.expense_type) || {}).label || detail.expense_type || "—"],
                      ["Expense Date", detail.expense_date || "—"],
                      ["Settlement", (detail.settlement_mode || "—").replace(/_/g, " ")]] : []),
                    ...(detail.employee_id ? [["Emp ID", detail.employee_code || "—"], ["Employee Name", detail.employee_name || "—"]] : []),
                    ["Raised By", detail.created_by],
                    ["Raised At", (detail.created_at || "").slice(0, 16).replace("T", " ")]].map(([k, v]) => (
                    <div key={k} className="border border-border rounded-sm p-2"><div className="text-[10px] uppercase text-muted-foreground">{k}</div><div className="font-semibold text-xs">{v}</div></div>
                  ))}
                </div>
                {detail.description && <div className="text-xs bg-muted/30 rounded-sm p-2">{detail.description}</div>}
                {(detail.items || []).length > 0 && (
                  <div className="border border-border rounded-sm">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-primary p-2 border-b">
                      Items {detail.is_stockable ? "(stock checked)" : detail.request_type === "manpower" ? "(pool availability checked)" : ""}
                    </div>
                    <table className="w-full text-xs">
                      <tbody>
                        {detail.items.map((it, i) => {
                          const sl = (detail.stock_lines || [])[i];
                          const al = (detail.availability_lines || [])[i];
                          const canFulfilLine = ["with_dept", "pr_raised", "sourcing"].includes(detail.status) && it.fulfil_status !== "fulfilled";
                          const extras = [it.size && `Size: ${it.size}`, it.material && `Material: ${it.material}`, it.make && `Make: ${it.make}`,
                            it.coating && `Coating: ${it.coating}`, it.item_type && `Type: ${it.item_type}`,
                            it.rate && detail.request_type === "manpower" && `Budget: ₹${Number(it.rate).toLocaleString("en-IN")}/mo/head`,
                            it.unit_weight_kg && `Unit wt: ${it.unit_weight_kg} kg`, it.total_weight_kg && `Total wt: ${it.total_weight_kg} kg`,
                            it.tech_details && `Tech: ${it.tech_details}`, it.specs && `Specs: ${it.specs}`].filter(Boolean).join(" · ");
                          return <tr key={i} className="border-b border-border/50">
                            <td className="p-1.5">{it.name}{extras && <div className="text-[10px] text-muted-foreground">{extras}</div>}
                              {it.vacancy_count > 0 && it.fulfil_status !== "fulfilled" && (
                                <div className="text-[10px] mt-0.5" data-testid={`req-line-hire-${i}`}>
                                  <span className={`px-1.5 py-0.5 rounded-sm border ${(it.hired_count || 0) >= it.vacancy_count ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-orange-50 border-orange-300 text-orange-800"}`}>
                                    {it.hired_count || 0} of {it.vacancy_count} hired
                                  </span>
                                  {it.recruitment_no && <span className="ml-1 text-muted-foreground">· {it.recruitment_no}</span>}
                                </div>
                              )}
                            </td>
                            <td className="p-1.5 tabular">{it.quantity} {it.unit}</td>
                            <td className="p-1.5 text-right">
                              {sl ? (sl.in_stock ? <span className="text-emerald-700">In stock ({sl.on_hand})</span> : <span className="text-amber-700">Short {sl.shortfall}</span>) : ""}
                              {al ? (al.in_pool
                                ? <span className="text-emerald-700">Pool OK ({al.available_workers}w + {al.matching_employees}e)</span>
                                : <span className="text-amber-700">Pool short {al.shortfall} ({al.available} avail)</span>) : ""}
                            </td>
                            <td className="p-1.5 text-right whitespace-nowrap">
                              {it.fulfil_status === "fulfilled"
                                ? <span className="text-[10px] px-1.5 py-0.5 rounded-sm border bg-emerald-50 border-emerald-300 text-emerald-800" data-testid={`req-line-done-${i}`}>✓ Done{it.fulfilled_by ? ` · ${it.fulfilled_by}` : ""}</span>
                                : canFulfilLine
                                  ? <Button size="sm" variant="outline" className="h-6 rounded-sm text-[10px] px-2" onClick={() => fulfilLine(detail, i)} data-testid={`req-line-fulfil-${i}`}>Mark Done</Button>
                                  : <span className="text-[10px] text-muted-foreground">pending</span>}
                            </td></tr>;
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
                {(detail.recruitment_nos || []).length > 0 && <div className="text-xs text-orange-700">Recruitment raised: <b>{detail.recruitment_nos.join(", ")}</b> — HR is sourcing.</div>}
                {detail.request_type === "manpower" && (detail.period_from || detail.period_to) && (
                  <div className="text-xs text-muted-foreground">Deployment timeline: <b>{detail.period_from || "—"} → {detail.period_to || "—"}</b>{detail.months ? ` · ${detail.months} month(s)` : ""} · Budget: <b>{inr(detail.est_value)}</b></div>
                )}
                {detail.expense_id && <div className="text-xs text-blue-700">Payment booked to Daily Expenses — Accounts will process with proof.</div>}
                {detail.pay_stage && (
                  <div className="border border-border rounded-sm p-2 text-xs" data-testid="req-detail-paystage">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-2">Accounts Workflow</span>
                    <Badge variant="outline" className={`rounded-sm ${(PAY_STAGE[detail.pay_stage] || [])[1]}`}>{(PAY_STAGE[detail.pay_stage] || [detail.pay_stage])[0]}</Badge>
                    {detail.pay_info?.verified_by && <span className="ml-2 text-muted-foreground">verified by {detail.pay_info.verified_by} · {(detail.pay_info.verified_at || "").slice(0, 16).replace("T", " ")}</span>}
                    {detail.pay_info?.bank_file_no && <span className="ml-2 font-mono-data">{detail.pay_info.bank_file_no}</span>}
                    {detail.pay_info?.utr_no && <span className="ml-2 font-mono-data">UTR {detail.pay_info.utr_no} · {detail.pay_info.paid_date}</span>}
                  </div>
                )}
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
                {["with_dept", "sourcing"].includes(detail.status) && detail.request_type === "manpower"
                  && (detail.items || []).some((it) => !it.recruitment_no && it.fulfil_status !== "fulfilled")
                  && ((detail.availability_lines || []).length === 0 || (detail.availability_lines || []).some((l) => l.shortfall > 0)) && (
                  <Button variant="outline" className="rounded-sm text-orange-700 border-orange-300" onClick={() => raiseRecruitment(detail)} data-testid="req-raise-recruitment"><Users className="h-4 w-4 mr-1.5" /> Raise Recruitment (HR Sourcing)</Button>
                )}
                {(detail.status === "with_dept" || detail.status === "pr_raised" || detail.status === "sourcing") && (
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

      <RowAttachments open={!!attachFor} onOpenChange={() => setAttachFor(null)}
        parentType="project_requests" parentId={attachFor?.id}
        recordTitle={`Attachments — ${attachFor?.request_no || ""}`} />
    </div>
  );
}


