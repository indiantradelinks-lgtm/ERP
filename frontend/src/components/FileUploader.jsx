import { useCallback, useRef, useState } from "react";
import { Upload, Loader2, FileText, Trash2, ExternalLink, Camera } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const MAX_BYTES = 25 * 1024 * 1024;

function humanSize(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function isImage(ct) { return ct?.startsWith("image/"); }

function dropzoneLabel({ busy, capture }) {
  if (busy) return "Uploading…";
  if (capture) return "Tap to capture or drop photos";
  return "Drop files or click to browse";
}

/**
 * Drag-drop multi-file uploader bound to a parent record.
 * Props: folder ('documents'|'safety'), parent_type, parent_id, accept, capture (mobile camera)
 * onUploaded(file) called after each successful upload.
 */
export default function FileUploader({ folder = "documents", parent_type, parent_id, category, accept, capture, onUploaded, files = [], onDeleted, compact = false, testidPrefix = "uploader" }) {
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState({});
  const inputRef = useRef();

  const upload = useCallback(async (file) => {
    if (file.size > MAX_BYTES) { toast.error(`${file.name} exceeds 25MB`); return; }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("folder", folder);
    if (parent_type) fd.append("parent_type", parent_type);
    if (parent_id) fd.append("parent_id", parent_id);
    if (category) fd.append("category", category);
    fd.append("title", file.name);
    setProgress((p) => ({ ...p, [file.name]: 0 }));
    try {
      const { data } = await api.post("/uploads", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          const pct = evt.total ? Math.round((evt.loaded / evt.total) * 100) : 0;
          setProgress((p) => ({ ...p, [file.name]: pct }));
        },
      });
      onUploaded?.(data);
      toast.success(`Uploaded ${file.name}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || `Upload failed: ${file.name}`);
    } finally {
      setProgress((p) => {
        const { [file.name]: _drop, ...rest } = p;
        return rest;
      });
    }
  }, [folder, parent_type, parent_id, category, onUploaded]);

  const handleFiles = async (fileList) => {
    setBusy(true);
    try {
      for (const f of Array.from(fileList || [])) {
        await upload(f);
      }
    } finally { setBusy(false); }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false);
    handleFiles(e.dataTransfer.files);
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this file?")) return;
    try {
      await api.delete(`/files/${id}`);
      onDeleted?.(id);
      toast.success("Removed");
    } catch {
      toast.error("Failed to remove");
    }
  };

  return (
    <div className="space-y-3" data-testid={testidPrefix}>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-sm transition-colors cursor-pointer",
          drag ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 bg-muted/20",
          compact ? "p-4" : "p-8"
        )}
        data-testid={`${testidPrefix}-dropzone`}
      >
        <div className="flex flex-col items-center text-center gap-2">
          {busy ? <Loader2 className="h-6 w-6 text-primary animate-spin" /> : <Upload className="h-6 w-6 text-muted-foreground" />}
          <div className="text-sm font-semibold">{dropzoneLabel({ busy, capture })}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Max 25MB · PDF · DOCX · XLSX · PNG · JPG</div>
          {capture && (
            <Button type="button" variant="outline" size="sm" className="mt-2 rounded-sm" onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }} data-testid={`${testidPrefix}-camera-btn`}>
              <Camera className="h-3.5 w-3.5 mr-1.5" /> Open camera
            </Button>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          accept={accept}
          capture={capture}
          onChange={(e) => handleFiles(e.target.files)}
          data-testid={`${testidPrefix}-input`}
        />
      </div>

      {Object.keys(progress).length > 0 && (
        <ul className="space-y-1.5">
          {Object.entries(progress).map(([name, pct]) => (
            <li key={name} className="flex items-center gap-3 px-2 py-1.5 border border-border rounded-sm bg-muted/30 text-xs" data-testid={`${testidPrefix}-progress-${name}`}>
              <Loader2 className="h-3.5 w-3.5 text-primary animate-spin shrink-0" />
              <span className="truncate flex-1">{name}</span>
              <Progress value={pct} className="h-1.5 w-32" />
              <span className="tabular w-9 text-right font-mono-data text-[10px] text-muted-foreground">{pct}%</span>
            </li>
          ))}
        </ul>
      )}

      {files.length > 0 && (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {files.map((f) => (
            <li key={f.id} className="border border-border rounded-sm p-2.5 flex items-center gap-3 bg-card">
              <Thumb file={f} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold truncate">{f.original_filename || f.title}</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{humanSize(f.size)} · {f.uploaded_by}</div>
              </div>
              <a
                href={`${process.env.REACT_APP_BACKEND_URL}/api/files/${f.id}/download`}
                target="_blank"
                rel="noreferrer"
                className="h-7 w-7 grid place-items-center rounded-sm hover:bg-muted text-muted-foreground"
                data-testid={`${testidPrefix}-open-${f.id}`}
                title="Open"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
              {onDeleted && (
                <button onClick={() => remove(f.id)} className="h-7 w-7 grid place-items-center rounded-sm hover:bg-destructive/10 text-destructive" data-testid={`${testidPrefix}-remove-${f.id}`} title="Remove">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Thumb({ file }) {
  const ct = file.content_type || "";
  if (isImage(ct)) {
    return (
      <img
        src={`${process.env.REACT_APP_BACKEND_URL}/api/files/${file.id}/download`}
        alt={file.original_filename}
        className="h-10 w-10 object-cover rounded-sm border border-border"
        loading="lazy"
      />
    );
  }
  return (
    <div className="h-10 w-10 grid place-items-center bg-primary/10 text-primary rounded-sm border border-primary/30">
      <FileText className="h-5 w-5" />
    </div>
  );
}
