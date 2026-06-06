import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { FileText, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { DepartmentSelect } from "@/components/DepartmentSelect";

const REPORT_KINDS = [
  { id: "resources", title: "Project-wise Resource Report", cols: ["project_name","client_name","open","approved"] },
  { id: "material_requests", title: "Project-wise Material Request", cols: ["project_name","material_transactions"] },
  { id: "purchase_requests", title: "Project-wise Purchase Requests", cols: ["project_name","pr_total","pr_pending","pr_approved"] },
  { id: "purchase_cost", title: "Project-wise Purchase Cost", cols: ["project_name","grn_count","purchase_cost"] },
  { id: "manpower", title: "Project-wise Manpower", cols: ["project_name","manpower_total","manpower_cost"] },
  { id: "assets", title: "Project-wise Asset Allocation", cols: ["project_name","asset_requests"] },
  { id: "pl", title: "Project-wise Profit & Loss", cols: ["project_name","client_name","contract_value","billing_done","total_project_cost","net_profit","profit_percentage"] },
  { id: "by_department", title: "Department-wise Project Rollup", cols: ["department","projects","billing_done","total_project_cost","net_profit","outstanding"] },
  { id: "by_pm", title: "Project Manager-wise Rollup", cols: ["project_manager_label","projects","billing_done","total_project_cost","net_profit","outstanding"] },
  { id: "pending_approvals", title: "Pending Approvals", cols: ["type","title","requested_by","current_step","created_at"] },
  { id: "store_pending", title: "Store Pending Material Requests", cols: ["rr_no","resource_type","item_name","quantity","project_name","status"] },
  { id: "loss_making", title: "Loss-Making Projects", cols: ["project_name","client_name","billing_done","total_project_cost","net_profit","profit_percentage"] },
  { id: "outstanding_payments", title: "Outstanding Payments", cols: ["project_name","client_name","billing_done","payment_received","outstanding"] },
];

function fmt(v) { if (typeof v !== "number") return v ?? "—"; if (v > 1000) return v.toLocaleString("en-IN", { maximumFractionDigits: 2 }); return Number.isInteger(v) ? v : v.toFixed(2); }

export default function OpsReports() {
  const [kind, setKind] = useState("pl");
  const [filters, setFilters] = useState({ client: "", department: "", status: "", start: "", end: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const meta = useMemo(() => REPORT_KINDS.find((r) => r.id === kind), [kind]);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ kind, ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v)) }).toString();
      const r = await api.get(`/ops/reports?${qs}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchReport(); /* eslint-disable-next-line */ }, [kind]);

  const exportCsv = () => {
    if (!data?.rows?.length) return;
    const cols = meta.cols;
    const lines = [cols.join(",")];
    for (const r of data.rows) {
      lines.push(cols.map((c) => {
        const v = r[c];
        if (v == null) return "";
        const s = String(v).replaceAll('"', '""');
        return s.includes(",") || s.includes('"') ? `"${s}"` : s;
      }).join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${kind}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 space-y-4" data-testid="ops-reports-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project & Operations Reports</h1>
        <p className="text-sm text-slate-600 mt-1">13 cross-project reports with filtering and CSV export.</p>
      </div>

      <div className="bg-white border rounded-lg p-3 flex gap-3 items-end flex-wrap">
        <div className="min-w-[260px]">
          <Label className="text-[10px] uppercase tracking-wider">Report</Label>
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="mt-1" data-testid="report-kind"><SelectValue /></SelectTrigger>
            <SelectContent>
              {REPORT_KINDS.map((r) => <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-[180px]">
          <Label className="text-[10px] uppercase tracking-wider">Client (search)</Label>
          <Input className="h-9 mt-1" value={filters.client} onChange={(e) => setFilters({ ...filters, client: e.target.value })} />
        </div>
        <div className="min-w-[180px]"><DepartmentSelect label="Department" value={filters.department} onChange={(v) => setFilters({ ...filters, department: v })} /></div>
        <div className="min-w-[150px]"><Label className="text-[10px] uppercase tracking-wider">Status</Label><Input className="h-9 mt-1" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} /></div>
        <Button onClick={fetchReport} disabled={loading} data-testid="report-run"><FileText className="h-4 w-4 mr-1" /> Run</Button>
        <Button variant="outline" onClick={exportCsv} disabled={!data?.rows?.length} data-testid="report-csv"><Download className="h-4 w-4 mr-1" /> Export CSV</Button>
      </div>

      <div className="bg-white border rounded-lg overflow-hidden">
        <div className="px-3 py-2 border-b bg-slate-50 text-xs flex items-center justify-between">
          <div className="font-medium text-slate-700">{meta?.title} · {data?.count || 0} rows</div>
        </div>
        <div className="overflow-x-auto max-h-[60vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-600 sticky top-0">
              <tr>
                {meta?.cols.map((c) => <th key={c} className="text-left px-3 py-2">{c.replaceAll("_", " ")}</th>)}
              </tr>
            </thead>
            <tbody>
              {!data?.rows?.length && <tr><td colSpan={meta?.cols.length || 1} className="text-center py-8 text-slate-500 text-sm">No data.</td></tr>}
              {data?.rows?.map((r, i) => (
                <tr key={i} className="border-t hover:bg-slate-50">
                  {meta?.cols.map((c) => <td key={c} className="px-3 py-2 text-xs">{fmt(r[c])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
