import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function Approvals() {
  const r = useResource("approvals");

  const approve = async (row) => {
    try {
      await api.put(`/approvals/${row.id}`, { ...row, status: "approved" });
      r.reload();
      toast.success("Approved");
    } catch (e) { toast.error("Failed"); }
  };
  const reject = async (row) => {
    try {
      await api.put(`/approvals/${row.id}`, { ...row, status: "rejected" });
      r.reload();
      toast.success("Rejected");
    } catch (e) { toast.error("Failed"); }
  };

  const columns = [
    { key: "title", label: "Request" },
    { key: "type", label: "Type" },
    { key: "reference", label: "Ref" },
    { key: "amount", label: "Amount", render: (r) => r.amount ? "₹ " + Number(r.amount).toLocaleString("en-IN") : "—" },
    { key: "requested_by", label: "Requested By" },
    { key: "current_approver", label: "Approver" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "approved" ? "success" : r.status === "rejected" ? "danger" : "warning" }) },
    {
      key: "_act",
      label: "Action",
      render: (row) => row.status === "pending" ? (
        <div className="inline-flex gap-1">
          <Button size="sm" className="h-7 rounded-sm bg-success text-success-foreground hover:opacity-90" onClick={() => approve(row)} data-testid={`approve-${row.id}`}>
            <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
          </Button>
          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => reject(row)} data-testid={`reject-${row.id}`}>
            <XCircle className="h-3.5 w-3.5 mr-1" /> Reject
          </Button>
        </div>
      ) : <span className="text-xs text-muted-foreground">—</span>,
    },
  ];
  const fields = [
    { key: "title", label: "Title", full: true },
    { key: "type", label: "Type", type: "select", options: ["purchase_order", "leave", "capex", "expense", "vendor"] },
    { key: "reference", label: "Reference ID" },
    { key: "amount", label: "Amount", type: "number" },
    { key: "requested_by", label: "Requested By" },
    { key: "current_approver", label: "Current Approver" },
    { key: "status", label: "Status", type: "select", options: ["pending", "approved", "rejected"] },
  ];
  return <DataTableShell title="Approvals Queue" description="Multi-level approvals across modules." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="approvals" />;
}
