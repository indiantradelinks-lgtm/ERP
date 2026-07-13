import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Paperclip } from "lucide-react";
import FileUploader from "@/components/FileUploader";
import { api } from "@/lib/api";

/**
 * Reusable attachments dialog scoped to a single record (parentType, parentId).
 * Lazy-loads file list when opened, supports drag-drop multi-file upload.
 */
export default function RowAttachments({
  open,
  onOpenChange,
  parentType,
  parentId,
  recordTitle,
  testidPrefix = "row-attach",
}) {
  const [files, setFiles] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!open || loaded || !parentId) return;
    let active = true;
    api
      .get(`/files?parent_type=${parentType}&parent_id=${parentId}`)
      .then((r) => { if (active) { setFiles(r.data || []); setLoaded(true); } })
      .catch(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [open, loaded, parentType, parentId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid={`${testidPrefix}-dialog`}>
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Paperclip className="h-4 w-4 text-primary" />
            Attachments
            {recordTitle && (
              <span className="text-sm font-normal text-muted-foreground ml-1">· {String(recordTitle).slice(0, 60)}</span>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Drag and drop files or click to browse. Files are linked to this record.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <FileUploader
            folder={parentType}
            parent_type={parentType}
            parent_id={parentId}
            files={files}
            onUploaded={(f) => setFiles((s) => [f, ...s])}
            onDeleted={(id) => setFiles((s) => s.filter((x) => x.id !== id))}
            testidPrefix={testidPrefix}
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt,.csv"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} data-testid={`${testidPrefix}-close`}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
