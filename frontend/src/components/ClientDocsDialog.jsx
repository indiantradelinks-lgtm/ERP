import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { FileText, FolderArchive } from "lucide-react";
import { StatusBadge } from "@/components/DataTableShell";
import FileUploader from "@/components/FileUploader";
import { api } from "@/lib/api";
import { toast } from "sonner";

export const CLIENT_DOC_CATEGORIES = ["PAN", "GST", "MSA", "NDA", "TradeLicense", "IncorporationCert", "AddressProof", "BankDetails", "Other"];

/**
 * Reusable client/site document attachments dialog with category dropdown.
 * Props:
 *   parentType: "clients" | "client_sites"
 *   parentId: client or site id
 *   title: header title
 */
export default function ClientDocsDialog({ parentType, parentId, title, onClose }) {
  const [files, setFiles] = useState([]);
  const [category, setCategory] = useState("PAN");
  const folder = parentType === "client_sites" ? "client_sites" : "clients";

  const load = async () => {
    try {
      const { data } = await api.get(`/files?parent_type=${parentType}&parent_id=${parentId}`);
      setFiles(data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load files"); }
  };
  useEffect(() => { if (parentId) load(); /* eslint-disable-next-line */ }, [parentId, parentType]);

  const grouped = useMemo(() => {
    const m = {};
    for (const f of files) {
      const k = f.category || "Uncategorised";
      (m[k] ||= []).push(f);
    }
    return m;
  }, [files]);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <FolderArchive className="h-4 w-4 text-primary" /> {title} · Documents
          </DialogTitle>
          <DialogDescription className="sr-only">Upload, categorise and download client documents (PAN, GST, MSA, NDA, etc.).</DialogDescription>
        </DialogHeader>

        <div className="mb-4 flex items-end gap-3">
          <div className="flex-1 max-w-xs">
            <Label className="text-xs uppercase tracking-wider mb-1.5 block">Upload Category</Label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm"
              data-testid="docs-category-select"
            >
              {CLIENT_DOC_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground pb-2">
            New uploads will be tagged as <span className="text-primary font-bold">{category}</span>
          </div>
        </div>

        <FileUploader
          folder={folder}
          parent_type={parentType}
          parent_id={parentId}
          category={category}
          accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
          onUploaded={() => load()}
          testidPrefix="client-docs-upload"
        />

        <div className="mt-6 space-y-4">
          {Object.keys(grouped).length === 0 && (
            <div className="text-center text-xs text-muted-foreground py-6 border border-dashed border-border rounded-sm">No documents yet.</div>
          )}
          {Object.entries(grouped).map(([cat, list]) => (
            <div key={cat} data-testid={`docs-group-${cat}`}>
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2 flex items-center gap-1.5">
                <FileText className="h-3 w-3" /> {cat}
                <StatusBadge text={`${list.length}`} tone="info" />
              </div>
              <ul className="space-y-1.5">
                {list.map((f) => (
                  <li key={f.id} className="flex items-center gap-3 p-2 rounded-sm border border-border bg-muted/20" data-testid={`docs-file-${f.id}`}>
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{f.original_filename || f.title}</div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        {f.uploaded_by} · {(f.created_at || "").slice(0, 16).replace("T", " ")}
                      </div>
                    </div>
                    <a
                      href={`${process.env.REACT_APP_BACKEND_URL}/api/files/${f.id}/download`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs underline text-primary"
                      data-testid={`docs-open-${f.id}`}
                    >Open</a>
                    <button
                      onClick={async () => {
                        if (!window.confirm(`Remove ${f.original_filename}?`)) return;
                        try { await api.delete(`/files/${f.id}`); load(); toast.success("Removed"); }
                        catch (e) { toast.error("Delete failed"); }
                      }}
                      className="text-xs underline text-destructive"
                      data-testid={`docs-remove-${f.id}`}
                    >Delete</button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
