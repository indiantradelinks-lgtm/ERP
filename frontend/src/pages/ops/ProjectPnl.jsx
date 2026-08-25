import { useEffect, useState, Fragment } from "react";
import { RefreshCw, TrendingUp, FileSpreadsheet, FileText, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;

export default function ProjectPnl() {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);

  const load = async () => {
    try { const r = await api.get("/project-pnl"); setData(r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed to load P&L"); }
  };
  useEffect(() => { load(); }, []);

  const download = async (fmt) => {
    try {
      const { data: blob } = await api.get(`/project-pnl/export.${fmt}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `project_pnl.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const t = data?.totals;

  return (
    <div className="space-y-5" data-testid="project-pnl-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <TrendingUp className="h-3 w-3" /> Profitability
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Project Profit & Loss</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Sales = RA bills raised (billed value, ex-GST) with receipts shown separately.
            Expenses = Vendor bills (incl. transport &amp; direct bookings) + unbilled GRN material + approved expense bookings
            (fooding, travelling…) + site petty cash + salary/employee advances + paid service &amp; payment requests. Updates live as records are approved/paid.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="pnl-reload"><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="pnl-export-xlsx"><FileSpreadsheet className="h-4 w-4 mr-1.5" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="pnl-export-pdf"><FileText className="h-4 w-4 mr-1.5" /> PDF</Button>
        </div>
      </div>

      {t && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[["Total Sales (Billed)", inr(t.income_billed), ""], ["Receipts", inr(t.receipts), ""],
            ["Total Expenses", inr(t.total_expense), "text-amber-700"],
            ["Gross Profit", inr(t.gross_profit), t.gross_profit >= 0 ? "text-emerald-700" : "text-rose-700"]].map(([label, v, tone]) => (
            <div key={label} className="bg-card border border-border rounded-sm p-3" data-testid={`pnl-kpi-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
              <div className={`text-xl font-black tabular ${tone}`}>{v}</div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-card border border-border rounded-sm">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-8"></TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Client</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Sales (Billed)</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Receipts</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Expenses</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Gross Profit</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Margin</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.projects || []).length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                No projects with sales or expenses yet.
              </TableCell></TableRow>
            )}
            {(data?.projects || []).map((r) => (
              <Fragment key={r.project_code}>
                <TableRow className="cursor-pointer" onClick={() => setOpen(open === r.project_code ? null : r.project_code)} data-testid={`pnl-row-${r.project_code}`}>
                  <TableCell>{open === r.project_code ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</TableCell>
                  <TableCell>
                    <div className="font-mono-data text-xs font-bold">{r.project_code}</div>
                    <div className="text-[11px] text-muted-foreground">{r.project_name}</div>
                  </TableCell>
                  <TableCell className="text-xs">{r.client || "—"}</TableCell>
                  <TableCell className="text-right font-mono-data tabular text-xs">{inr(r.income_billed)}
                    <div className="text-[9px] text-muted-foreground font-sans">{r.bills_count} bill(s)</div>
                  </TableCell>
                  <TableCell className="text-right font-mono-data tabular text-xs">{inr(r.receipts)}</TableCell>
                  <TableCell className="text-right font-mono-data tabular text-xs text-amber-800">{inr(r.total_expense)}</TableCell>
                  <TableCell className={`text-right font-mono-data tabular text-xs font-bold ${r.gross_profit >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{inr(r.gross_profit)}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant="outline" className={`rounded-sm tabular ${r.margin_pct >= 0 ? "border-emerald-300 text-emerald-800 bg-emerald-50" : "border-rose-300 text-rose-800 bg-rose-50"}`}>{r.margin_pct}%</Badge>
                  </TableCell>
                </TableRow>
                {open === r.project_code && (
                  <TableRow className="bg-muted/20 hover:bg-muted/20">
                    <TableCell></TableCell>
                    <TableCell colSpan={7}>
                      <div className="py-2" data-testid={`pnl-detail-${r.project_code}`}>
                        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Expense Breakdown</div>
                        {Object.keys(r.expenses_by_category || {}).length === 0 && (
                          <div className="text-xs text-muted-foreground">No expenses booked yet.</div>
                        )}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                          {Object.entries(r.expenses_by_category || {}).map(([k, v]) => (
                            <div key={k} className="border border-border rounded-sm p-2 bg-card">
                              <div className="text-[10px] text-muted-foreground">{k}</div>
                              <div className="font-mono-data tabular text-xs font-bold">{inr(v)}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
