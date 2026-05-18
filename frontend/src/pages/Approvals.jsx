import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Eye } from "lucide-react";
import ApprovalDetail from "@/components/ApprovalDetail";

export default function Approvals() {
  const r = useResource("approvals");
  const [active, setActive] = useState(null);
  const [open, setOpen] = useState(false);
  const [params, setParams] = useSearchParams();

  const openDetail = (row) => { setActive(row); setOpen(true); };

  // If URL has ?id=xxx, auto-open the matching approval once data loads
  useEffect(() => {
    const id = params.get("id");
    if (id && r.data?.length) {
      const found = r.data.find((x) => x.id === id);
      if (found) { setActive(found); setOpen(true); }
    }
  }, [params, r.data]);

  const columns = [
    { key: "title", label: "Request" },
    { key: "type", label: "Type", render: (r) => (r.type || "").replaceAll("_", " ") },
    { key: "reference", label: "Ref" },
    { key: "amount", label: "Amount", render: (r) => r.amount ? "₹ " + Number(r.amount).toLocaleString("en-IN") : "—" },
    { key: "requested_by", label: "Requested By" },
    {
      key: "current_step",
      label: "Step",
      render: (row) => {
        const chain = row.chain || [];
        const idx = row.current_step ?? 0;
        const step = chain[idx];
        if (!step || row.status === "approved" || row.status === "rejected") return "—";
        return <span className="text-xs">{idx + 1}/{chain.length} · {step.label}</span>;
      },
    },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status || "pending", tone: r.status === "approved" ? "success" : r.status === "rejected" ? "danger" : r.status === "in_progress" ? "info" : "warning" }) },
    {
      key: "_act",
      label: "Action",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openDetail(row)} data-testid={`approval-open-${row.id}`}>
          <Eye className="h-3.5 w-3.5 mr-1" /> Review
        </Button>
      ),
    },
  ];
  const fields = [
    { key: "title", label: "Title", full: true },
    { key: "type", label: "Type", type: "select", options: ["purchase_order", "leave", "capex", "expense", "vendor", "quotation"] },
    { key: "reference", label: "Reference ID" },
    { key: "amount", label: "Amount", type: "number" },
    { key: "requested_by", label: "Requested By" },
  ];

  const onUpdated = (updated) => {
    // refresh the list inline
    r.reload();
    setActive(updated);
  };

  return (
    <>
      <DataTableShell
        title="Approvals Queue"
        description="Multi-level chains: requester → dept head → finance → director. Click Review to act."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={null}
        onDelete={r.remove}
        testidPrefix="approvals"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
      />
      <ApprovalDetail approval={active} open={open} onOpenChange={setOpen} onUpdated={onUpdated} />
    </>
  );
}
