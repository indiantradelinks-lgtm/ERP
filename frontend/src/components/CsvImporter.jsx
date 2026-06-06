import { useEffect, useState, useRef } from "react";
import { Upload, CheckCircle2, XCircle, AlertTriangle, Download, FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * Reusable CSV bulk-import dialog for any master collection backed by
 * the /api/import/{collection}/* endpoints.
 *
 * Props:
 *   open / onOpenChange
 *   collection — backend slug (clients|vendors|employees|inventory)
 *   onCompleted({inserted, skipped_duplicates, failed}) — fired after commit
 *
 * Flow:
 *   1) User drops/picks a CSV → posted to /preview
 *   2) Preview table shows valid / error / duplicate rows
 *   3) "Commit" sends only the rows the user opted to keep
 */
export default function CsvImporter({ open, onOpenChange, collection, onCompleted }) {
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setUploading(false);
      setCommitting(false);
    }
  }, [open]);

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post(`/import/${collection}/preview`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(data);
      const { total, valid, errors, duplicates } = data.summary;
      toast.success(`Parsed ${total} rows · ${valid} valid · ${errors} errors · ${duplicates} duplicates`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Preview failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  };

  const downloadTemplate = async () => {
    try {
      const { data } = await api.get(`/import/template/${collection}`);
      const blob = new Blob([data.content], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Template download failed");
    }
  };

  const commit = async () => {
    if (!preview) return;
    // Only forward rows that have no row-level errors. Duplicates are still
    // sent — the backend decides via skip_duplicates whether to insert them.
    const rows = preview.rows
      .filter((r) => r.errors.length === 0)
      .map((r) => r.data);
    if (rows.length === 0) {
      toast.error("Nothing to import");
      return;
    }
    setCommitting(true);
    try {
      const { data } = await api.post(`/import/${collection}/commit`, {
        rows,
        skip_duplicates: skipDuplicates,
      });
      toast.success(`Imported ${data.inserted} · Skipped ${data.skipped_duplicates} duplicates · ${data.failed} failed`);
      onCompleted?.(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Commit failed");
    } finally {
      setCommitting(false);
    }
  };

  const summary = preview?.summary;
  const showHelp = !preview && !uploading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl rounded-sm" data-testid={`csv-import-${collection}`}>
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Upload className="h-4 w-4 text-primary" /> Bulk Import — {preview?.label || collection}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Drop or pick a CSV file with master data. Preview validation results, then commit.
          </DialogDescription>
        </DialogHeader>

        {showHelp && (
          <button
            type="button"
            className="w-full border-2 border-dashed border-border rounded-sm py-12 px-4 text-center hover:border-primary/60 hover:bg-muted/30 transition-colors"
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            data-testid={`csv-dropzone-${collection}`}
          >
            <FileUp className="h-10 w-10 mx-auto text-muted-foreground" />
            <div className="font-display font-bold text-lg mt-3">Drop CSV here, or click to browse</div>
            <p className="text-xs text-muted-foreground mt-1">Headers must match the {collection} schema. UTF-8 / Latin-1.</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-3 rounded-sm"
              onClick={(e) => { e.stopPropagation(); downloadTemplate(); }}
              data-testid={`csv-template-${collection}`}
            >
              <Download className="h-3.5 w-3.5 mr-1.5" /> Download template
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
              data-testid={`csv-file-input-${collection}`}
            />
          </button>
        )}

        {uploading && (
          <div className="py-12 text-center text-sm text-muted-foreground">Parsing CSV…</div>
        )}

        {preview && (
          <div className="space-y-3" data-testid={`csv-preview-${collection}`}>
            {/* Summary strip */}
            <div className="grid grid-cols-4 gap-2">
              <SummaryTile label="Total Rows" value={summary.total} tone="neutral" />
              <SummaryTile label="Valid" value={summary.valid} tone="success" />
              <SummaryTile label="Errors" value={summary.errors} tone={summary.errors ? "danger" : "neutral"} />
              <SummaryTile label="Duplicates" value={summary.duplicates} tone={summary.duplicates ? "warning" : "neutral"} />
            </div>
            {preview.unknown_headers?.length > 0 && (
              <div className="text-xs text-warning bg-warning/10 border border-warning/30 rounded-sm px-3 py-2 flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5" />
                Ignoring unknown columns: <span className="font-mono-data">{preview.unknown_headers.join(", ")}</span>
              </div>
            )}
            <div className="border border-border rounded-sm max-h-[300px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-muted/60 border-b border-border">
                  <tr>
                    <th className="text-left p-2 w-12">#</th>
                    <th className="text-left p-2 w-20">Status</th>
                    <th className="text-left p-2">Row Preview</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => {
                    let badge;
                    if (r.errors.length) badge = <StatusBadge text="error" tone="danger" />;
                    else if (r.duplicate_of) badge = <StatusBadge text="duplicate" tone="warning" />;
                    else badge = <StatusBadge text="ok" tone="success" />;
                    return (
                      <tr key={r.row} className="border-b border-border/60" data-testid={`csv-row-${r.row}`}>
                        <td className="p-2 font-mono-data tabular text-muted-foreground">{r.row}</td>
                        <td className="p-2">{badge}</td>
                        <td className="p-2">
                          <div className="truncate max-w-2xl" title={JSON.stringify(r.data)}>
                            {Object.entries(r.data).slice(0, 4).map(([k, v]) => (
                              <span key={k} className="mr-3"><span className="text-muted-foreground">{k}:</span> {String(v)}</span>
                            ))}
                            {Object.keys(r.data).length > 4 && <span className="text-muted-foreground">…</span>}
                          </div>
                          {r.errors.length > 0 && (
                            <div className="text-destructive text-[11px] mt-0.5 flex items-center gap-1"><XCircle className="h-3 w-3" /> {r.errors.join("; ")}</div>
                          )}
                          {r.duplicate_of && (
                            <div className="text-warning text-[11px] mt-0.5 flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Matches existing record {r.duplicate_of.slice(0, 8)}</div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={skipDuplicates}
                onChange={(e) => setSkipDuplicates(e.target.checked)}
                className="h-4 w-4"
                data-testid={`csv-skip-dups-${collection}`}
              />
              Skip duplicates on commit (recommended)
            </label>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} data-testid={`csv-cancel-${collection}`}>Cancel</Button>
          {preview && (
            <Button
              className="rounded-sm"
              onClick={commit}
              disabled={committing || summary.valid === 0}
              data-testid={`csv-commit-${collection}`}
            >
              <CheckCircle2 className="h-4 w-4 mr-1.5" /> Import {summary.valid} valid rows
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryTile({ label, value, tone }) {
  const styles = {
    success: "border-success/40 text-success",
    danger: "border-destructive/40 text-destructive",
    warning: "border-warning/40 text-warning",
    neutral: "border-border text-foreground",
  };
  return (
    <div className={cn("border rounded-sm p-2 text-center", styles[tone] || styles.neutral)}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-display font-black text-2xl tabular leading-none mt-0.5">{value}</div>
    </div>
  );
}
