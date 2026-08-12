import { useState } from "react";
import { Download, FileText, RefreshCw, AlertTriangle, ClipboardList, Landmark, Receipt, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ProjectSelect } from "@/components/MasterSelect";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (v) => `₹ ${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

function SummaryTile({ label, value, icon: Icon, warn, testid }) {
  return (
    <div className={`border rounded-sm p-3 flex items-start gap-3 ${warn && value > 0 ? "border-rose-300 bg-rose-50" : "bg-white"}`} data-testid={testid}>
      <div className="p-2 rounded-sm bg-slate-100"><Icon className="h-4 w-4 text-slate-600" /></div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className={`text-lg font-semibold ${warn && value > 0 ? "text-rose-700" : ""}`}>{value}</div>
      </div>
    </div>
  );
}

function Section({ title, cols, rows, render, testid }) {
  return (
    <div data-testid={testid}>
      <h3 className="text-sm font-semibold mb-2">{title} ({rows.length})</h3>
      <div className="border rounded-sm bg-white overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>{cols.map((c) => <TableHead key={c} className="text-[11px] uppercase tracking-wider whitespace-nowrap">{c}</TableHead>)}</TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={cols.length} className="text-center text-sm text-slate-500 py-6">None — nothing pending here</TableCell></TableRow>
            )}
            {rows.map(render)}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export default function PmHandover() {
  const [projectId, setProjectId] = useState("");
  const [pack, setPack] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async (pid) => {
    if (!pid) return;
    setLoading(true);
    try {
      const r = await api.get(`/projects/${pid}/handover-pack`);
      setPack(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to build handover pack");
    } finally { setLoading(false); }
  };

  const downloadPdf = async () => {
    try {
      const r = await api.get(`/projects/${projectId}/handover-pack.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url; a.download = `HANDOVER_${pack?.project?.code || projectId}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("PDF download failed"); }
  };

  const p = pack?.project;
  const s = pack?.summary;

  return (
    <div className="p-4 md:p-6 space-y-4" data-testid="pm-handover-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2"><FileText className="h-5 w-5" /> PM Handover Pack</h1>
          <p className="text-xs text-slate-500">One-click snapshot of open requests, pending approvals and delayed items for an incoming Project Manager</p>
        </div>
        <div className="flex items-end gap-2">
          <div className="w-72">
            <ProjectSelect value={projectId} valueKey="id" testid="handover-project-select"
              onChange={(v) => { setProjectId(v); load(v); }} includeBlank />
          </div>
          <Button variant="outline" size="sm" className="rounded-sm h-9" disabled={!projectId || loading}
            onClick={() => load(projectId)} data-testid="handover-refresh">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" className="rounded-sm h-9" disabled={!pack} onClick={downloadPdf} data-testid="handover-download-pdf">
            <Download className="h-3.5 w-3.5 mr-1" /> Download PDF
          </Button>
        </div>
      </div>

      {!pack && <div className="border rounded-sm bg-white p-10 text-center text-sm text-slate-500" data-testid="handover-empty">Select a project to generate its handover pack.</div>}

      {pack && (
        <>
          <div className="border rounded-sm bg-white p-3 text-sm flex flex-wrap gap-x-6 gap-y-1" data-testid="handover-project-header">
            <span className="font-semibold">{p.code} — {p.name}</span>
            <span className="text-slate-500">Client: {p.client || "—"}</span>
            <span className="text-slate-500">Current PM: <b className="text-slate-800">{p.project_manager || "—"}</b></span>
            <span className="text-slate-500">Contract: {p.start_date || "—"} → {p.end_date || "—"}</span>
            <span className="text-slate-500">Generated: {(pack.generated_at || "").slice(0, 16).replace("T", " ")} by {pack.generated_by}</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <SummaryTile label="Open Requests" value={s.open_requests} icon={ClipboardList} testid="handover-kpi-open" />
            <SummaryTile label="Pending Approvals" value={s.pending_approvals} icon={Clock} testid="handover-kpi-approvals" />
            <SummaryTile label="With Accounts" value={s.accounts_queue} icon={Landmark} testid="handover-kpi-accounts" />
            <SummaryTile label="Pending Bills" value={s.pending_bills} icon={Receipt} testid="handover-kpi-bills" />
            <SummaryTile label="Delayed Items" value={s.delayed_items} icon={AlertTriangle} warn testid="handover-kpi-delayed" />
            <SummaryTile label="Open Value" value={inr(s.open_value)} icon={ClipboardList} testid="handover-kpi-value" />
          </div>

          <Section title="1 · Open Requests" testid="handover-open-requests"
            cols={["Request #", "Type", "Description", "Value", "Status", "Need By", "Raised By", "Raised At", "Age"]}
            rows={pack.open_requests}
            render={(r) => (
              <TableRow key={r.request_no}>
                <TableCell className="font-mono text-xs">{r.request_no}</TableCell>
                <TableCell className="text-xs">{r.type}</TableCell>
                <TableCell className="text-xs max-w-[260px] truncate" title={r.description}>{r.description || "—"}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(r.est_value)}</TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{r.status}</Badge></TableCell>
                <TableCell className="text-xs">{r.need_by || "—"}</TableCell>
                <TableCell className="text-xs">{r.raised_by}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{r.raised_at}</TableCell>
                <TableCell className="text-xs">{r.age_days}d</TableCell>
              </TableRow>
            )} />

          <Section title="2 · Pending Approvals" testid="handover-approvals"
            cols={["Request #", "Type", "Value", "Pending With", "Raised By", "Age"]}
            rows={pack.pending_approvals}
            render={(r) => (
              <TableRow key={r.request_no}>
                <TableCell className="font-mono text-xs">{r.request_no}</TableCell>
                <TableCell className="text-xs">{r.type}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(r.est_value)}</TableCell>
                <TableCell><Badge className="rounded-sm bg-amber-100 text-amber-900 border-amber-300 text-[10px]">{r.pending_with}</Badge></TableCell>
                <TableCell className="text-xs">{r.raised_by}</TableCell>
                <TableCell className="text-xs">{r.age_days}d</TableCell>
              </TableRow>
            )} />

          <Section title="3 · Payments with Accounts" testid="handover-accounts"
            cols={["Request #", "Type", "Paid To", "Value", "Verified Amt", "Accounts Stage", "Bank File"]}
            rows={pack.accounts_queue}
            render={(r) => (
              <TableRow key={r.request_no}>
                <TableCell className="font-mono text-xs">{r.request_no}</TableCell>
                <TableCell className="text-xs">{r.type}</TableCell>
                <TableCell className="text-xs">{r.vendor || r.employee_name || "—"}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(r.est_value)}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{r.verified_amount ? inr(r.verified_amount) : "—"}</TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{r.pay_stage}</Badge></TableCell>
                <TableCell className="text-xs font-mono">{r.bank_file_no || "—"}</TableCell>
              </TableRow>
            )} />

          <Section title="4 · Pending Bill Requests" testid="handover-bills"
            cols={["Request #", "Bill Type", "Expected Amt", "Period", "Requested By", "Age"]}
            rows={pack.pending_bills}
            render={(b) => (
              <TableRow key={b.request_no}>
                <TableCell className="font-mono text-xs">{b.request_no}</TableCell>
                <TableCell className="text-xs">{b.bill_type}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(b.expected_amount)}</TableCell>
                <TableCell className="text-xs">{b.period}</TableCell>
                <TableCell className="text-xs">{b.requested_by}</TableCell>
                <TableCell className="text-xs">{b.age_days}d</TableCell>
              </TableRow>
            )} />

          <Section title="5 · Delayed Items — action needed" testid="handover-delayed"
            cols={["Request #", "Item", "Value", "Why delayed"]}
            rows={pack.delayed}
            render={(d, i) => (
              <TableRow key={`${d.request_no}-${i}`} className="bg-rose-50/40">
                <TableCell className="font-mono text-xs">{d.request_no}</TableCell>
                <TableCell className="text-xs">{d.type}</TableCell>
                <TableCell className="text-xs whitespace-nowrap">{inr(d.est_value)}</TableCell>
                <TableCell className="text-xs text-rose-700">{d.reason}</TableCell>
              </TableRow>
            )} />
        </>
      )}
    </div>
  );
}
