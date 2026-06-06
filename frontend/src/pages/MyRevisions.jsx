import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { RotateCcw, FileQuestion, XCircle, Inbox } from "lucide-react";
import ApprovalDetail from "@/components/ApprovalDetail";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const statusMeta = {
  rejected_revision_required: { label: "Revision Required", tone: "bg-rose-100 text-rose-700", icon: XCircle },
  additional_info_required: { label: "Info Needed", tone: "bg-amber-100 text-amber-700", icon: FileQuestion },
  rejected: { label: "Rejected", tone: "bg-rose-100 text-rose-700", icon: XCircle },
};

export default function MyRevisions() {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState(null);

  const load = async () => {
    setBusy(true);
    try {
      const { data } = await api.get("/approvals/my-revisions");
      setRows(data || []);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { load(); }, []);

  const handleUpdated = (updated) => {
    if (updated?.status === "pending" || updated?.status === "in_progress") {
      // Resubmitted — drop from this list
      setRows((rs) => rs.filter((r) => r.id !== updated.id));
    } else {
      setRows((rs) => rs.map((r) => (r.id === updated.id ? updated : r)));
    }
  };

  const counts = {
    rejected: rows.filter((r) => r.status === "rejected_revision_required" || r.status === "rejected").length,
    info: rows.filter((r) => r.status === "additional_info_required").length,
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="my-revisions-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <RotateCcw className="h-6 w-6 text-blue-600" />
            My Revisions
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Requests bounced back to you for correction or additional information. Revise and resubmit to restart the chain.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={busy} data-testid="my-revisions-refresh">Refresh</Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <KpiTile label="Awaiting My Action" value={rows.length} tone="bg-blue-50 border-blue-200 text-blue-900" />
        <KpiTile label="Rejected — Revise" value={counts.rejected} tone="bg-rose-50 border-rose-200 text-rose-900" />
        <KpiTile label="Info Requested" value={counts.info} tone="bg-amber-50 border-amber-200 text-amber-900" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Open Revisions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="border rounded-sm overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Reason / Required</TableHead>
                  <TableHead>Last Action</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                      <Inbox className="h-8 w-8 mx-auto mb-2 opacity-40" />
                      Nothing waiting for your revision. Anything you've already resubmitted will reappear here if it bounces back again.
                    </TableCell>
                  </TableRow>
                )}
                {rows.map((r) => {
                  const meta = statusMeta[r.status] || { label: r.status, tone: "bg-muted text-muted-foreground" };
                  const Icon = meta.icon || XCircle;
                  return (
                    <TableRow key={r.id} data-testid={`revision-row-${r.id}`}>
                      <TableCell className="font-medium">{r.title || r.type}</TableCell>
                      <TableCell className="text-xs">{(r.type || "").replaceAll("_", " ")}</TableCell>
                      <TableCell>
                        <Badge className={`${meta.tone} flex items-center gap-1 w-fit`}>
                          <Icon className="h-3 w-3" /> {meta.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs font-mono">v{r.version || "1.0"}</TableCell>
                      <TableCell className="text-xs max-w-xs truncate">
                        {r.last_reject_reason || r.last_info_request?.comment || "—"}
                        {r.last_info_request?.required_documents?.length > 0 && (
                          <div className="text-[10px] text-amber-700 mt-0.5">
                            Docs: {r.last_info_request.required_documents.slice(0, 3).join(", ")}
                            {r.last_info_request.required_documents.length > 3 && " …"}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {(r.last_reject_at || r.updated_at || "").slice(0, 16).replace("T", " ")}
                      </TableCell>
                      <TableCell>
                        <Button size="sm" onClick={() => setViewing(r)} data-testid={`revision-open-${r.id}`}>
                          Open & Revise
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <ApprovalDetail
        approval={viewing}
        open={!!viewing}
        onOpenChange={(o) => !o && setViewing(null)}
        onUpdated={handleUpdated}
      />
    </div>
  );
}

function KpiTile({ label, value, tone }) {
  return (
    <div className={`p-4 border rounded-sm ${tone}`}>
      <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}
