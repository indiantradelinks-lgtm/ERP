import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FileSpreadsheet, FileText, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";

const REPORTS = [
  { key: "profit-loss", label: "Profit & Loss", desc: "Revenue, expense and margin by month." },
  { key: "cost-centre", label: "Cost Centre Expense", desc: "Expense booked by project, site and cost centre." },
  { key: "project-profitability", label: "Project Profitability", desc: "Revenue vs cost for active projects." },
  { key: "vendor-outstanding", label: "Vendor Outstanding", desc: "Aging buckets of unpaid POs." },
  { key: "client-outstanding", label: "Client Outstanding", desc: "Receivables aging by client." },
  { key: "attendance", label: "Attendance Report", desc: "Daily & monthly attendance summary." },
  { key: "payroll", label: "Payroll Report", desc: "Net pay, deductions, statutory." },
  { key: "inventory", label: "Inventory Valuation", desc: "Current stock value and low-stock alerts." },
  { key: "safety", label: "Safety Statistics", desc: "Observations, near miss, incident rate." },
  { key: "asset", label: "Asset Utilization", desc: "Allocation, idle and maintenance hours." },
];

export default function Reports() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/dashboard/summary").then((r) => setData(r.data)); }, []);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Analytics</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Reports & Analytics</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate and export operational reports. PDF/Excel export coming in next iteration.</p>
      </div>

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
              <Button size="sm" variant="outline" className="rounded-sm h-8" data-testid={`report-${r.key}-pdf`}>
                <FileText className="h-3.5 w-3.5 mr-1.5" /> PDF
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm h-8" data-testid={`report-${r.key}-xlsx`}>
                <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Excel
              </Button>
              <Button size="sm" className="rounded-sm h-8 ml-auto" data-testid={`report-${r.key}-run`}>
                <Download className="h-3.5 w-3.5 mr-1.5" /> Run
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
