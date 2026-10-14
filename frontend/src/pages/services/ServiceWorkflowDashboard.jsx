import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RefreshCw, Workflow } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Tile, StatusChip, inr, dt, useSvcMeta } from "./shared";

export default function ServiceWorkflowDashboard() {
  const nav = useNavigate();
  const meta = useSvcMeta();
  const [data, setData] = useState(null);
  const [f, setF] = useState({ date_from: "", date_to: "", department: "", category: "", requester: "", project: "" });

  const load = useCallback(async () => {
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      const r = await api.get(`/service-workflow/dashboard?${qs}`);
      setData(r.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const c = data?.cards || {};
  const tiles = [
    ["Total Service Requests", c.total_requests, "", "/app/services/requests"],
    ["Draft Requests", c.draft_requests, "text-blue-700", "/app/services/requests?status=draft"],
    ["Approved Requests", c.approved_requests, "text-emerald-700", "/app/services/requests?status=approved"],
    ["Rejected", c.rejected_requests, "text-red-700", "/app/services/requests?status=rejected"],
    ["RFQs Pending", c.rfqs_pending, "text-indigo-700", "/app/services/rfqs"],
    ["Quotations Pending", c.quotations_pending, "text-violet-700", "/app/services/rfqs"],
    ["POs Pending", c.pos_pending, "text-indigo-700", "/app/services/pos"],
    ["Services In Progress", c.services_in_progress, "text-cyan-700", "/app/services/pos"],
    ["SRN Pending", c.srn_pending, "text-teal-700", "/app/services/srns"],
    ["Invoices Pending", c.invoices_pending, "text-fuchsia-700", "/app/services/invoices"],
    ["Exception Review", c.exceptions, "text-red-700", "/app/services/invoices?status=exception_review"],
    ["Payment Pending", c.payment_pending, "text-orange-700", "/app/services/invoices?tab=payments"],
    ["Overdue Payments", c.overdue_payments, "text-red-700", "/app/services/invoices?tab=payments"],
    ["Completed / Paid", c.completed, "text-emerald-700", "/app/services/requests?status=closed"],
  ];

  return (
    <div className="p-4 space-y-4" data-testid="svc-dashboard-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Workflow className="h-5 w-5" /> Service Procurement Dashboard</h1>
          <p className="text-xs text-muted-foreground">Service Request → Approval → RFQ → Quotation → PO → SRN → Invoice → Payment → Closed</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="svc-dash-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
          <Button size="sm" onClick={() => nav("/app/services/requests?new=1")} data-testid="svc-dash-new-request">New Service Request</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 border rounded-md bg-white p-3">
        <div><Label className="text-[10px] uppercase">From</Label><Input type="date" className="h-8" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="svc-dash-from" /></div>
        <div><Label className="text-[10px] uppercase">To</Label><Input type="date" className="h-8" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="svc-dash-to" /></div>
        <div>
          <Label className="text-[10px] uppercase">Department</Label>
          <select className="h-8 w-full rounded-sm border border-input bg-background px-2 text-sm" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} data-testid="svc-dash-dept">
            <option value="">All</option>
            {(meta?.departments || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-[10px] uppercase">Category</Label>
          <select className="h-8 w-full rounded-sm border border-input bg-background px-2 text-sm" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="svc-dash-category">
            <option value="">All</option>
            {(meta?.service_categories || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div><Label className="text-[10px] uppercase">Requester</Label><Input className="h-8" placeholder="name" value={f.requester} onChange={(e) => setF({ ...f, requester: e.target.value })} data-testid="svc-dash-requester" /></div>
        <div><Label className="text-[10px] uppercase">Project</Label><Input className="h-8" placeholder="code" value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })} data-testid="svc-dash-project" /></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {tiles.map(([l, v, cls, to]) => (
          <Tile key={l} label={l} value={v} cls={cls} onClick={() => nav(to)} testid={`svc-tile-${l.toLowerCase().replace(/[^a-z]+/g, "-")}`} />
        ))}
      </div>

      <div className="border rounded-md bg-white">
        <div className="px-3 py-2 border-b text-sm font-semibold">Recent Service Requests</div>
        <Table>
          <TableHeader><TableRow>
            <TableHead>SR No</TableHead><TableHead>Date</TableHead><TableHead>Requester</TableHead>
            <TableHead>Department</TableHead><TableHead>Category</TableHead><TableHead>Budget</TableHead>
            <TableHead>Status</TableHead><TableHead>Owner</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.recent || []).map((r) => (
              <TableRow key={r.id} className="cursor-pointer hover:bg-muted/40" onClick={() => nav(`/app/services/requests/${r.id}`)} data-testid={`svc-dash-row-${r.sr_no}`}>
                <TableCell className="font-medium text-primary">{r.sr_no}</TableCell>
                <TableCell>{dt(r.request_date)}</TableCell>
                <TableCell>{r.requester_name}</TableCell>
                <TableCell>{r.department || "—"}</TableCell>
                <TableCell>{r.service_category || "—"}</TableCell>
                <TableCell>{inr(r.estimated_budget)}</TableCell>
                <TableCell><StatusChip status={r.status} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.current_owner || "—"}</TableCell>
              </TableRow>
            ))}
            {!(data?.recent || []).length && <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-6">No service requests yet</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
