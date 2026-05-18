import { useEffect, useState } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import FileUploader from "@/components/FileUploader";
import { api } from "@/lib/api";
import { Cloud } from "lucide-react";

export default function Documents() {
  const r = useResource("documents");
  const [files, setFiles] = useState([]);

  const loadFiles = async () => {
    try { const { data } = await api.get(`/files?folder=documents`); setFiles(data); } catch { /* ignore */ }
  };
  useEffect(() => { loadFiles(); }, []);

  const columns = [
    { key: "doc_id", label: "Doc ID" },
    { key: "title", label: "Title" },
    { key: "category", label: "Category" },
    { key: "project", label: "Project" },
    { key: "uploaded_by", label: "Uploaded By" },
    { key: "version", label: "Version" },
    {
      key: "expiry",
      label: "Expiry",
      render: (row) => {
        if (!row.expiry) return "—";
        const days = Math.ceil((new Date(row.expiry) - new Date()) / 86400000);
        if (days < 0) return <StatusBadge text={`Expired ${Math.abs(days)}d`} tone="danger" />;
        if (days <= 30) return <StatusBadge text={`${days}d left`} tone="warning" />;
        return row.expiry;
      },
    },
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

  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 border-b border-border">
          <div>
            <h2 className="font-display text-xl font-bold tracking-tight flex items-center gap-2">
              <Cloud className="h-5 w-5 text-primary" /> Document Repository
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">Drag-drop multi-file upload. PDF, DOCX, XLSX, PNG, JPG — max 25 MB each.</p>
          </div>
          <div className="text-xs text-muted-foreground">
            <span className="text-foreground font-semibold tabular">{files.length}</span> files in storage
          </div>
        </div>
        <div className="p-4">
          <FileUploader
            folder="documents"
            parent_type="documents"
            files={files}
            onUploaded={(f) => setFiles((s) => [f, ...s])}
            onDeleted={(id) => setFiles((s) => s.filter((x) => x.id !== id))}
            testidPrefix="documents-uploader"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt,.csv"
          />
        </div>
      </div>

      <DataTableShell
        title="Document Register"
        description="Version control, category tags and expiry tracking for contracts, certifications & drawings."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="documents"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
      />
    </div>
  );
}
