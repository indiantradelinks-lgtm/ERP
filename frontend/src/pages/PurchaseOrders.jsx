import { useState } from "react";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { Mail, Network, FileDown } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import SendEmailDialog from "@/components/SendEmailDialog";
import LineageTrail from "@/components/LineageTrail";
import { downloadPdf } from "@/lib/exports";

const PO_STATUS_TONE = { approved: "success", rejected: "danger", received: "info", partially_received: "warning" };

export default function PurchaseOrders() {
  const r = useResource("purchase-orders");
  const [emailFor, setEmailFor] = useState(null);
  const [lineageFor, setLineageFor] = useState(null);
  const columns = [
    { key: "po_number", label: "PO #" },
    { key: "vendor", label: "Vendor" },
    { key: "project", label: "Project" },
    { key: "date", label: "Date" },
    { key: "total", label: "Total", render: (r) => "₹ " + Number(r.total || r.amount || 0).toLocaleString("en-IN") },
    { key: "paid", label: "Paid", render: (r) => (r.paid ? "Yes" : "No") },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: toneFor(PO_STATUS_TONE, r.status, "warning") }) },
    {
      key: "_actions",
      label: "Actions",
      render: (row) => (
        <div className="inline-flex gap-1">
          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(row)} data-testid={`po-lineage-${row.id}`} title="View end-to-end procurement lineage">
            <Network className="h-3 w-3 mr-1" /> Lineage
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/pos/${row.id}/pdf`, `${row.po_number || row.id}.pdf`)} data-testid={`po-pdf-${row.id}`} title="Download PO PDF">
            <FileDown className="h-3 w-3 mr-1" /> PDF
          </Button>
          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => setEmailFor(row)} data-testid={`purchase-email-${row.id}`}>
            <Mail className="h-3 w-3 mr-1" /> Email
          </Button>
        </div>
      ),
    },
  ];
  const fields = [
    { key: "po_number", label: "PO Number" },
    { key: "vendor", label: "Vendor Name", full: true },
    { key: "project", label: "Project" },
    { key: "date", label: "Date", type: "date" },
    { key: "total", label: "Total (INR)", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["draft", "pending", "approved", "rejected", "received", "partially_received"] },
    { key: "paid", label: "Paid (true/false)", type: "select", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
  ];
  return (
    <>
      <DataTableShell title="Purchase Orders" description="Requisition → RFQ → PO → GRN. Multi-level approvals." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="purchase" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="purchase_orders" />
      <SendEmailDialog
        open={!!emailFor}
        onOpenChange={(o) => !o && setEmailFor(null)}
        module="purchase_order"
        recordId={emailFor?.id}
      />
      <Dialog open={!!lineageFor} onOpenChange={(o) => !o && setLineageFor(null)}>
        <DialogContent className="max-w-5xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Procurement Lineage — {lineageFor?.po_number}</DialogTitle>
            <DialogDescription>Full traceability from the originating PR to every GRN posted against this PO.</DialogDescription>
          </DialogHeader>
          {lineageFor && <LineageTrail kind="po" recordId={lineageFor.id} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
