import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Documents() {
  const r = useResource("documents");
  const columns = [
    { key: "doc_id", label: "Doc ID" },
    { key: "title", label: "Title" },
    { key: "category", label: "Category" },
    { key: "project", label: "Project" },
    { key: "uploaded_by", label: "Uploaded By" },
    { key: "version", label: "Version" },
    { key: "expiry", label: "Expiry" },
  ];
  const fields = [
    { key: "doc_id", label: "Document ID" },
    { key: "title", label: "Title", full: true },
    { key: "category", label: "Category", type: "select", options: ["contract", "drawing", "certification", "invoice", "inspection", "hr", "safety"] },
    { key: "project", label: "Project" },
    { key: "uploaded_by", label: "Uploaded By" },
    { key: "version", label: "Version" },
    { key: "expiry", label: "Expiry Date", type: "date" },
  ];
  return <DataTableShell title="Document Management" description="Contracts, drawings, certifications and inspection reports." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="documents" />;
}
