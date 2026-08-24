import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, Download, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN")}`;
const dt = (iso) => (iso ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : "—");
const STATUSES = [["approved", "Approved"], ["rejected", "Rejected"], ["pending", "Pending"], ["all", "All"]];

export default function ApprovalReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState({ status: "approved", type: "", date_from: "", date_to: "", q: "", approver: "", project_manager: "" });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target?.value ?? e }));

  const qs = useCallback(() => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => v && p.set(k, v));
    return p.toString();
  }, [f]);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData((await api.get(`/approvals/report?${qs()}`)).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setLoading(false); }
  }, [qs]);
  useEffect(() => { load(); }, [load]);

  const download = async (fmt) => {
    try {
      const { data: blob } = await api.get(`/approvals/report/export?fmt=${fmt}&${qs()}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([blob]));
      const a = document.createElement("a");
      a.href = url; a.download = `approval-report.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const s = data?.summary;
  return (
    <div className="space-y-5" data-testid="approval-report-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <ClipboardCheck className="h-3 w-3" /> Management Report
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Approval Report</h1>
          <p className="text-sm text-muted-foreground mt-1">Every request with its full approval trail — who approved, when, and for which project.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("xlsx")} data-testid="report-export-xlsx"><Download className="h-4 w-4 mr-1" /> Excel</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={() => download("pdf")} data-testid="report-export-pdf"><FileText className="h-4 w-4 mr-1" /> PDF</Button>
          <Button variant="outline" className="h-9 rounded-sm" onClick={load} data-testid="report-reload"><RefreshCw className="h-4 w-4" /></Button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm p-3 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={f.status} onChange={set("status")} data-testid="report-filter-status">
          {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="h-9 border border-input rounded-sm px-2 text-sm bg-background" value={f.type} onChange={set("type")} data-testid="report-filter-type">
          <option value="">All Types</option>
          {Object.keys(s?.by_type || {}).sort().map((t) => <option key={t} value={t}>{t.replaceAll("_", " ")}</option>)}
        </select>
        <Input type="date" className="h-9" value={f.date_from} onChange={set("date_from")} data-testid="report-filter-from" />
        <Input type="date" className="h-9" value={f.date_to} onChange={set("date_to")} data-testid="report-filter-to" />
        <Input placeholder="Search name / ref…" className="h-9" value={f.q} onChange={set("q")} data-testid="report-filter-q" />
        <Input placeholder="Approver…" className="h-9" value={f.approver} onChange={set("approver")} data-testid="report-filter-approver" />
        <Input placeholder="Project Manager…" className="h-9" value={f.project_manager} onChange={set("project_manager")} data-testid="report-filter-pm" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-sm p-3"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Records</div><div className="text-xl font-black tabular" data-testid="report-kpi-total">{s?.total ?? "—"}</div></div>
        <div className="bg-card border border-border rounded-sm p-3"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Amount</div><div className="text-xl font-black tabular">{s ? inr(s.total_amount) : "—"}</div></div>
        <div className="bg-card border border-border rounded-sm p-3"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Request Types</div><div className="text-xl font-black tabular">{s ? Object.keys(s.by_type).length : "—"}</div></div>
        <div className="bg-card border border-border rounded-sm p-3"><div className="text-[10px] uppercase tracking-wider text-muted-foreground">Statuses</div><div className="text-xs font-semibold mt-1">{s ? Object.entries(s.by_status).map(([k, v]) => `${k}: ${v}`).join(" · ") : "—"}</div></div>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="text-[10px] uppercase tracking-wider">Ref / Type</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Request</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Project / PM</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Requested By</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Amount</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Final Approver</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider">Decision At</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-right">Approvals</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {loading && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">Loading…</TableCell></TableRow>}
            {!loading && (data?.rows || []).length === 0 && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">No records match the selected filters.</TableCell></TableRow>}
            {!loading && (data?.rows || []).map((r) => (
              <TableRow key={r.id} data-testid={`report-row-${r.id}`}>
                <TableCell>
                  <div className="font-mono-data text-xs font-bold">{r.reference || "—"}</div>
                  <div className="text-[10px] text-muted-foreground">{(r.type || "").replaceAll("_", " ")}</div>
                </TableCell>
                <TableCell className="max-w-[260px]"><div className="text-sm font-semibold truncate" title={r.title}>{r.title}</div></TableCell>
                <TableCell>
                  <div className="text-xs font-semibold">{r.project_code || "—"}{r.project_name ? ` · ${r.project_name}` : ""}</div>
                  {r.project_manager && <div className="text-[10px] text-muted-foreground">PM: {r.project_manager}</div>}
                </TableCell>
                <TableCell className="text-xs">{r.requested_by || "—"}</TableCell>
                <TableCell className="text-right font-mono-data tabular text-sm font-bold">{r.amount ? inr(r.amount) : "—"}</TableCell>
                <TableCell className="text-xs">{r.decided_by || "—"}</TableCell>
                <TableCell className="text-xs whitespace-nowrap" title={(r.approvers || []).map((a) => `${a.step}: ${a.by} @ ${dt(a.at)}`).join("\n")}>{dt(r.decided_at)}</TableCell>
                <TableCell className="text-right"><Badge variant="outline" className="rounded-sm text-[10px]">{r.approvals_count}/{r.chain_length}</Badge></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
