import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Briefcase, Building2, MapPin, Calendar, Users, Package, Truck, DollarSign, AlertTriangle, TrendingUp, TrendingDown, CircleDot, Activity, FileText, Wallet, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const ALERT_TONE = {
  danger: "bg-red-50 border-red-300 text-red-800",
  warning: "bg-amber-50 border-amber-300 text-amber-800",
  info: "bg-blue-50 border-blue-300 text-blue-800",
};

function fmt(n) { return (n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

export default function ProjectOpsDashboard() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const projectId = sp.get("project_id");
  const [d, setD] = useState(null);
  const [projects, setProjects] = useState([]);
  const [pickerId, setPickerId] = useState(projectId || "");

  useEffect(() => { api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {}); }, []);

  useEffect(() => {
    if (!pickerId) { setD(null); return; }
    api.get(`/ops/projects/${pickerId}/dashboard`)
      .then((r) => setD(r.data))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load dashboard"));
  }, [pickerId]);

  return (
    <div className="p-6 space-y-4" data-testid="ops-dashboard-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
          <h1 className="font-display font-black text-3xl tracking-tight">Project Dashboard</h1>
          <p className="text-sm text-slate-600 mt-1">Single-pane view of progress, resources, costs and P&L.</p>
        </div>
        <select value={pickerId} onChange={(e) => { setPickerId(e.target.value); navigate(`/app/ops/project-dashboard?project_id=${e.target.value}`); }}
                 className="h-10 rounded-sm border border-input bg-background px-3 text-sm w-80" data-testid="ops-dashboard-picker">
          <option value="">— select a project —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code || ""} · {p.name}</option>)}
        </select>
      </div>

      {!pickerId && <div className="border border-dashed rounded-lg p-12 text-center text-slate-500 text-sm">Pick a project to see its dashboard.</div>}
      {pickerId && !d && <div className="text-sm text-slate-500 py-6">Loading…</div>}
      {d && (
        <>
          {/* Overview */}
          <div className="bg-white border rounded-lg p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <Cell icon={Briefcase} label="Project" value={d.project.name} sub={d.project.code} />
            <Cell icon={Building2} label="Client" value={d.project.client_name} />
            <Cell icon={MapPin} label="Site" value={d.project.site_location || "—"} />
            <Cell icon={Calendar} label="Duration" value={`${d.project.contract_start_date || "—"} → ${d.project.contract_end_date || "—"}`} />
            <Cell icon={DollarSign} label="Contract Value" value={`₹ ${fmt(d.project.contract_value)}`} />
            <Cell icon={CircleDot} label="Status" value={(d.project.status || "—").toUpperCase()} sub={d.project.priority || ""} />
            <Cell icon={Users} label="Manpower Deployed" value={d.resources.manpower_deployed} />
            <Cell icon={Activity} label="Pending Approvals" value={d.operations.pending_approvals} />
          </div>

          {/* Alerts */}
          {d.alerts.length > 0 && (
            <div className="space-y-2">
              {d.alerts.map((a, i) => (
                <div key={i} className={`px-3 py-2 rounded border text-sm ${ALERT_TONE[a.level]}`} data-testid={`alert-${a.type}`}>
                  <AlertTriangle className="inline h-4 w-4 mr-1.5" /> {a.message}
                </div>
              ))}
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-4">
            <Section title="Resources" icon={Package}>
              <KV k="Open Resource Requests" v={d.resources.open_resource_requests} />
              <KV k="Approved Resource Requests" v={d.resources.approved_resource_requests} />
              <KV k="Assets Deployed" v={d.resources.assets_deployed} />
              <KV k="Vehicles Deployed" v={d.resources.vehicles_deployed} />
              <KV k="Accommodation Units" v={d.resources.accommodation_units} />
              <div className="text-xs text-slate-500 mt-2 grid grid-cols-5 gap-1">
                {Object.entries(d.resources.by_type).map(([k, v]) => (
                  <div key={k} className="text-center px-1 py-1 bg-slate-50 rounded">{k}: <b className="text-slate-900">{v}</b></div>
                ))}
              </div>
            </Section>

            <Section title="Material" icon={Truck}>
              <KV k="Material Requests" v={d.material.material_requested} />
              <KV k="Material Issued" v={d.material.material_issued} />
              <KV k="Material Pending" v={d.material.material_pending} />
            </Section>

            <Section title="Purchase" icon={FileText}>
              <KV k="PR Raised" v={d.purchase.pr_raised} />
              <KV k="PR Pending" v={d.purchase.pr_pending} />
              <KV k="PR Approved" v={d.purchase.pr_approved} />
              <KV k="PO Created" v={d.purchase.po_created} />
              <KV k="PO Value" v={`₹ ${fmt(d.purchase.po_value)}`} />
              <KV k="Material Received Value" v={`₹ ${fmt(d.purchase.material_received_value)}`} />
            </Section>

            <Section title="Operations" icon={ShieldCheck}>
              <KV k="Open Tasks" v={d.operations.open_tasks} />
              <KV k="Pending Approvals" v={d.operations.pending_approvals} />
              <KV k="Manpower Active" v={d.resources.manpower_active} />
            </Section>
          </div>

          {/* Financial section */}
          <div className="bg-white border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="font-display font-bold text-lg flex items-center gap-2"><Wallet className="h-4 w-4" /> Financial Summary · Profit & Loss</div>
              {d.financial.is_loss
                ? <Badge variant="destructive" className="text-xs"><TrendingDown className="h-3 w-3 mr-1" /> LOSS MAKING</Badge>
                : d.financial.gross_profit > 0
                  ? <Badge className="bg-green-600 text-xs"><TrendingUp className="h-3 w-3 mr-1" /> PROFITABLE</Badge>
                  : <Badge variant="outline" className="text-xs">N/A</Badge>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <KVCard label="Contract Value" value={`₹ ${fmt(d.financial.contract_value)}`} />
              <KVCard label="Billing Done" value={`₹ ${fmt(d.financial.billing_done)}`} />
              <KVCard label="Payment Received" value={`₹ ${fmt(d.financial.payment_received)}`} />
              <KVCard label="Outstanding" value={`₹ ${fmt(d.financial.outstanding)}`} tone={d.financial.outstanding > 0 ? "warning" : ""} />
              <KVCard label="Purchase Cost" value={`₹ ${fmt(d.financial.purchase_cost)}`} />
              <KVCard label="Material Cost" value={`₹ ${fmt(d.financial.material_cost)}`} />
              <KVCard label="Manpower Cost" value={`₹ ${fmt(d.financial.manpower_cost)}`} />
              <KVCard label="Other (Consumable+PPE+Tool)" value={`₹ ${fmt(d.financial.consumable_cost + d.financial.ppe_cost + d.financial.tool_cost)}`} />
              <KVCard label="Admin / Driver / Accommodation" value={`₹ ${fmt(d.financial.admin_cost + d.financial.driver_cost + d.financial.accommodation_cost + d.financial.vehicle_cost)}`} />
              <KVCard label="Total Project Cost" value={`₹ ${fmt(d.financial.total_project_cost)}`} tone={d.financial.over_budget ? "danger" : ""} />
              <KVCard label="Gross Profit" value={`₹ ${fmt(d.financial.gross_profit)}`} tone={d.financial.gross_profit < 0 ? "danger" : "success"} />
              <KVCard label={`Net Profit (${d.financial.profit_percentage}%)`} value={`₹ ${fmt(d.financial.net_profit)}`} tone={d.financial.net_profit < 0 ? "danger" : "success"} />
            </div>
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={() => navigate("/app/ops/resource-requests")}><Package className="h-4 w-4 mr-1" /> Resource Requests</Button>
            <Button variant="outline" onClick={() => navigate("/app/purchase-requisitions")}><FileText className="h-4 w-4 mr-1" /> Purchase Requisitions</Button>
            <Button variant="outline" onClick={() => navigate("/app/store-transactions")}><Truck className="h-4 w-4 mr-1" /> Store Transactions</Button>
            <Button variant="outline" onClick={() => navigate("/app/ops/reports")}><FileText className="h-4 w-4 mr-1" /> Reports</Button>
          </div>
        </>
      )}
    </div>
  );
}

function Cell({ icon: Icon, label, value, sub }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1"><Icon className="h-3 w-3" /> {label}</div>
      <div className="text-sm font-semibold truncate">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}
function Section({ title, icon: Icon, children }) {
  return (
    <div className="bg-white border rounded-lg p-4">
      <div className="font-display font-bold text-base mb-3 flex items-center gap-2"><Icon className="h-4 w-4" /> {title}</div>
      <div className="space-y-1.5 text-sm">{children}</div>
    </div>
  );
}
function KV({ k, v }) {
  return <div className="flex items-center justify-between"><span className="text-slate-600 text-xs">{k}</span><span className="font-semibold">{v}</span></div>;
}
function KVCard({ label, value, tone }) {
  const tones = { success: "border-green-300 bg-green-50", danger: "border-red-300 bg-red-50", warning: "border-amber-300 bg-amber-50" };
  return (
    <div className={`p-3 border rounded ${tones[tone] || "border-slate-200 bg-slate-50"}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-600">{label}</div>
      <div className="text-base font-bold tabular mt-0.5">{value}</div>
    </div>
  );
}
