/**
 * ApprovalDocsGate — universal reference-documents picker for any approval
 * submission across modules (Quotations, PR, GRN, Resource Requests, etc.).
 *
 * Two modes:
 *   • "I have docs" → user uploads new files (PDF/JPG/PNG/XLSX/DOCX, ≤25MB each)
 *                     AND/OR picks existing files already linked to the record
 *   • "Not applicable" → toggle on; force ≥5-char reason
 *
 * Yields a value of:
 *   {
 *     documents: [file_id, ...],
 *     linked_attachments: [file_id, ...],
 *     documents_not_required: bool,
 *     documents_not_required_reason: "...",
 *   }
 *
 * The parent component is responsible for forwarding this value as the request
 * body (or merging it into one) to the relevant backend endpoint.
 */
import { useEffect, useState } from "react";
import { Paperclip, Upload, X, FileCheck, AlertCircle, Trash2 } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ApprovalDocsGate({
  parentType,                // e.g. "quotations", "purchase_requisitions"
  parentId,                  // record id whose existing files we can re-link
  value,                     // controlled value object
  onChange,                  // (next) => void
  className = "",
  testidPrefix = "approval-docs",
}) {
  const v = value || { documents: [], linked_attachments: [], documents_not_required: false, documents_not_required_reason: "" };
  const [existingFiles, setExistingFiles] = useState([]);
  const [uploadedFiles, setUploadedFiles] = useState([]);  // local copy of newly uploaded files (with name)
  const [uploading, setUploading] = useState(false);

  // Load existing files linked to the parent record
  useEffect(() => {
    if (!parentType || !parentId) { setExistingFiles([]); return; }
    api.get(`/files?parent_type=${parentType}&parent_id=${parentId}`)
      .then((r) => setExistingFiles(r.data || []))
      .catch(() => setExistingFiles([]));
  }, [parentType, parentId]);

  const set = (patch) => onChange({ ...v, ...patch });

  const toggleNA = (next) => {
    if (next) {
      set({ documents_not_required: true, documents: [], linked_attachments: [] });
      setUploadedFiles([]);
    } else {
      set({ documents_not_required: false, documents_not_required_reason: "" });
    }
  };

  const toggleLinked = (fileId) => {
    const linked = v.linked_attachments || [];
    const next = linked.includes(fileId) ? linked.filter((x) => x !== fileId) : [...linked, fileId];
    set({ linked_attachments: next });
  };

  const handleUpload = async (files) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const newDocs = [...(v.documents || [])];
      const newLocal = [...uploadedFiles];
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        if (parentType) fd.append("parent_type", parentType);
        if (parentId)   fd.append("parent_id", parentId);
        const r = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
        const id = r.data.id || r.data.file_id;
        if (id) {
          newDocs.push(id);
          newLocal.push({ file_id: id, name: r.data.original_name || f.name, size: f.size });
        }
      }
      set({ documents: newDocs });
      setUploadedFiles(newLocal);
      toast.success(`Uploaded ${files.length} file(s)`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed");
    } finally { setUploading(false); }
  };

  const removeUploaded = (fileId) => {
    set({ documents: (v.documents || []).filter((x) => x !== fileId) });
    setUploadedFiles(uploadedFiles.filter((f) => f.file_id !== fileId));
  };

  const totalAttached = (v.documents?.length || 0) + (v.linked_attachments?.length || 0);

  return (
    <div className={`border border-amber-200 bg-amber-50/40 rounded-md p-3 space-y-3 ${className}`} data-testid={testidPrefix}>
      <div className="flex items-start gap-2">
        <Paperclip className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
        <div className="flex-1">
          <div className="text-xs font-semibold uppercase tracking-wider text-amber-800">Reference Documents</div>
          <div className="text-[11px] text-amber-700/80">
            Attach at least one supporting document, or mark as Not Applicable with a short reason.
          </div>
        </div>
      </div>

      {/* N/A toggle */}
      <label className="flex items-center gap-2 text-sm select-none" data-testid={`${testidPrefix}-na-toggle`}>
        <input
          type="checkbox"
          className="h-4 w-4 accent-amber-600"
          checked={!!v.documents_not_required}
          onChange={(e) => toggleNA(e.target.checked)}
        />
        <span>Not applicable — no reference documents required</span>
      </label>

      {v.documents_not_required ? (
        <div>
          <Label className="text-[10px] uppercase tracking-wider text-amber-800">Reason <span className="text-destructive">*</span></Label>
          <Textarea
            rows={2}
            className="mt-1 bg-background"
            value={v.documents_not_required_reason || ""}
            onChange={(e) => set({ documents_not_required_reason: e.target.value })}
            placeholder="e.g. Internal allocation, no external docs needed"
            data-testid={`${testidPrefix}-na-reason`}
          />
          {v.documents_not_required_reason && v.documents_not_required_reason.trim().length < 5 && (
            <div className="text-[11px] text-destructive mt-1 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" /> Reason must be at least 5 characters.
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Existing record attachments */}
          {existingFiles.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-wider text-amber-800">Existing attachments on this record</Label>
              <div className="space-y-1 max-h-40 overflow-y-auto bg-background rounded border border-amber-200/60 p-1.5">
                {existingFiles.map((f) => {
                  const checked = (v.linked_attachments || []).includes(f.id);
                  return (
                    <label key={f.id} className="flex items-center gap-2 text-xs px-1.5 py-1 rounded hover:bg-muted/40 cursor-pointer" data-testid={`${testidPrefix}-linked-${f.id}`}>
                      <input type="checkbox" className="h-3.5 w-3.5 accent-amber-600" checked={checked} onChange={() => toggleLinked(f.id)} />
                      <FileCheck className="h-3.5 w-3.5 text-amber-700" />
                      <span className="flex-1 truncate" title={f.original_name || f.name}>{f.original_name || f.name}</span>
                      <span className="text-[10px] text-muted-foreground">{Math.round((f.size || 0) / 1024)} KB</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {/* Upload new files */}
          <div>
            <Label className="text-[10px] uppercase tracking-wider text-amber-800">Upload new files</Label>
            <div className="mt-1 flex items-center gap-2">
              <Input
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.docx,.doc,.csv"
                disabled={uploading}
                onChange={(e) => handleUpload(e.target.files)}
                className="bg-background h-9"
                data-testid={`${testidPrefix}-upload`}
              />
              {uploading && <Upload className="h-4 w-4 text-amber-700 animate-pulse" />}
            </div>
            {uploadedFiles.length > 0 && (
              <ul className="mt-2 space-y-1">
                {uploadedFiles.map((f) => (
                  <li key={f.file_id} className="text-xs flex items-center gap-2 bg-background rounded border border-amber-200/60 px-2 py-1" data-testid={`${testidPrefix}-uploaded-${f.file_id}`}>
                    <FileCheck className="h-3.5 w-3.5 text-emerald-600" />
                    <span className="flex-1 truncate" title={f.name}>{f.name}</span>
                    <span className="text-[10px] text-muted-foreground">{Math.round(f.size / 1024)} KB</span>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => removeUploaded(f.file_id)}>
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="text-[11px] text-amber-800 font-medium pt-1 border-t border-amber-200/60">
            {totalAttached > 0
              ? <><FileCheck className="inline h-3 w-3 mr-1" /> {totalAttached} document(s) attached.</>
              : <><AlertCircle className="inline h-3 w-3 mr-1" /> No documents attached yet.</>}
          </div>
        </>
      )}
    </div>
  );
}

/** Helper: validate a value before submission. Returns null if OK, error string otherwise. */
export function validateApprovalDocs(value) {
  const v = value || {};
  if (v.documents_not_required) {
    const reason = (v.documents_not_required_reason || "").trim();
    if (reason.length < 5) return "Please provide a short reason (min 5 characters) for marking documents as Not Applicable.";
    return null;
  }
  const total = (v.documents?.length || 0) + (v.linked_attachments?.length || 0);
  if (total < 1) return "Attach at least one reference document or mark Not Applicable.";
  return null;
}

/** Helper: empty initial value */
export function emptyApprovalDocs() {
  return { documents: [], linked_attachments: [], documents_not_required: false, documents_not_required_reason: "" };
}
