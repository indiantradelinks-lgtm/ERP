import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FileSpreadsheet, FileText, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";
import { downloadExport } from "@/lib/exports";

// Each catalogue entry binds the report card to an export slug.
const REPORTS = [
  { key: "profit-loss", label: "Profit & Loss", desc: "Revenue, expense and margin by month.", resource: "journal-entries" },
  { key: "cost-centre", label: "Cost Centre Expense", desc: "Expense booked by project, site and cost centre.", resource: "journal-entries" },
  { key: "project-profitability", label: "Project Profitability", desc: "Revenue vs cost for active projects.", resource: "projects" },
  { key: "vendor-outstanding", label: "Vendor Outstanding", desc: "Aging buckets of unpaid POs.", resource: "purchase-orders" },
  { key: "client-outstanding", label: "Client Outstanding", desc: "Receivables aging by client.", resource: "quotations" },
  { key: "attendance", label: "Attendance Report", desc: "Daily & monthly attendance summary.", resource: "attendance" },
  { key: "payroll", label: "Payroll Report", desc: "Net pay, deductions, statutory.", resource: "payroll" },
  { key: "inventory", label: "Inventory Valuation", desc: "Current stock value and low-stock alerts.", resource: "inventory" },
  { key: "safety", label: "Safety Statistics", desc: "Observations, near miss, incident rate.", resource: "safety-reports" },
  { key: "asset", label: "Asset Utilization", desc: "Allocation, idle and maintenance hours.", resource: "assets" },
];

export default function Reports() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/dashboard/summary").then((r) => setData(r.data)); }, []);

  const inr = (v) => "₹ " + Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });

  return (
    <div className="space-y-8">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Analytics</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Reports & Analytics</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate and export operational reports as Excel or PDF.</p>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Revenue (6M)" value={inr(data.kpis?.revenue || 0)} tone="success" />
          <Tile label="Expenses (6M)" value={inr(data.kpis?.expenses || 0)} tone="warning" />
          <Tile label="Net Profit" value={inr(data.kpis?.profit || 0)} tone="primary" />
          <Tile label="Open Receivables" value={inr(data.kpis?.receivables || 0)} tone="info" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {REPORTS.map((r) => (
          <div key={r.key} className="bg-card border border-border rounded-sm p-5 hover:border-primary/50 transition-colors" data-testid={`report-${r.key}`}>
            <div className="flex items-start justify-between">
              <div>
                <div className="font-display font-bold text-base">{r.label}</div>
                <div className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{r.desc}</div>
              </div>
              <StatusBadge text="Live" tone="success" />
            </div>
            <div className="mt-5 flex gap-2">
              <Button size="sm" variant="outline" className="rounded-sm h-8" onClick={() => downloadExport(r.resource, "pdf")} data-testid={`report-${r.key}-pdf`}>
                <FileText className="h-3.5 w-3.5 mr-1.5" /> PDF
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm h-8" onClick={() => downloadExport(r.resource, "xlsx")} data-testid={`report-${r.key}-xlsx`}>
                <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Excel
              </Button>
              <Button size="sm" className="rounded-sm h-8 ml-auto" onClick={() => downloadExport(r.resource, "xlsx")} data-testid={`report-${r.key}-run`}>
                <Download className="h-3.5 w-3.5 mr-1.5" /> Run
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Tile({ label, value, tone }) {
  const map = { success: "border-success/40 text-success", warning: "border-warning/40 text-warning", primary: "border-primary/40 text-primary", info: "border-chart-3/40 text-chart-3" };
  return (
    <div className={`bg-card border rounded-sm p-4 ${map[tone] || "border-border"}`}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="font-display font-black text-2xl tabular mt-1 text-foreground">{value}</div>
    </div>
  );
}
