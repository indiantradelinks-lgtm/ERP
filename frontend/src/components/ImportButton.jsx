import { useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import CsvImporter from "@/components/CsvImporter";

/**
 * Convenience wrapper: renders an "Import CSV" toolbar button + the
 * `<CsvImporter />` dialog. Slot it into DataTableShell's `rightSlot`.
 *
 *   <ImportButton collection="clients" onCompleted={r.reload} />
 */
export default function ImportButton({ collection, onCompleted }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outline"
        className="h-9 rounded-sm"
        onClick={() => setOpen(true)}
        data-testid={`import-btn-${collection}`}
        title="Bulk import from CSV"
      >
        <Upload className="h-4 w-4 mr-1.5" /> Import
      </Button>
      <CsvImporter
        open={open}
        onOpenChange={setOpen}
        collection={collection}
        onCompleted={onCompleted}
      />
    </>
  );
}
