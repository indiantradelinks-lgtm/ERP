import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";

const JE_TYPE_TONE = { revenue: "success", expense: "danger" };

export default function Accounts() {
  const r = useResource("journal-entries");
  const columns = [
    { key: "je_number", label: "JE #" },
    { key: "date", label: "Date" },
    { key: "account", label: "Account" },
    { key: "type", label: "Type", badge: (r) => ({ text: r.type, tone: toneFor(JE_TYPE_TONE, r.type, "info") }) },
    { key: "cost_centre", label: "Cost Centre" },
    { key: "amount", label: "Amount", render: (r) => "₹ " + Number(r.amount || 0).toLocaleString("en-IN") },
    { key: "narration", label: "Narration" },
  ];
  const fields = [
    { key: "je_number", label: "JE Number" },
    { key: "date", label: "Date", type: "date" },
    { key: "account", label: "Account / Ledger" },
    { key: "type", label: "Type", type: "select", options: ["revenue", "expense", "asset", "liability"] },
    { key: "cost_centre", label: "Cost Centre" },
    { key: "amount", label: "Amount (INR)", type: "number" },
    { key: "narration", label: "Narration", full: true, type: "textarea" },
  ];
  return <DataTableShell title="Accounts & Finance" description="Journal entries, ledgers, and cost-centre wise booking." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="accounts" exportResource={r.exportResource} canWrite={r.canWrite} canDelete={r.canDelete} />;
}
