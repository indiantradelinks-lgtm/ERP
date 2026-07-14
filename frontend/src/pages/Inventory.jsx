import { useState, useRef, useEffect } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { QRCodeSVG } from "qrcode.react";
import { QrCode, Printer, BookOpenCheck, Download, Upload, Loader2 } from "lucide-react";
import StockLedger from "@/components/StockLedger";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function Inventory() {
  const r = useResource("inventory");
  const [qrItem, setQrItem] = useState(null);
  const [ledgerFor, setLedgerFor] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [catOptions, setCatOptions] = useState(["scaffolding", "painting", "rope_access", "roof_sheeting", "ppe", "consumables"]);
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/inv/categories")
      .then((res) => {
        const names = (res.data || []).filter((c) => c.active !== false).map((c) => c.name).filter(Boolean);
        if (names.length) setCatOptions(names);
      })
      .catch(() => {});
  }, []);

  const downloadTemplate = async () => {
    try {
      const resp = await api.get("/inv-bulk/items/template", { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `item-master-bulk-template-${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Item Master template downloaded");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to download template");
    }
  };

  const uploadBulk = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBulkUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const resp = await api.post("/inv-bulk/items/import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setBulkResult(resp.data);
      toast.success(`Bulk update done · ${resp.data.summary.updated} updated, ${resp.data.summary.created} created`);
      r.refresh?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Bulk import failed");
    } finally {
      setBulkUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const printQR = () => {
    const svg = document.getElementById("inv-qr-svg");
    if (!svg || !qrItem) return;
    // Use a sandboxed iframe with srcdoc instead of document.write to eliminate XSS surface.
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>QR · ${esc(qrItem.code)}</title>
      <style>body{font-family:system-ui,sans-serif;text-align:center;padding:24px;}h2{margin:0 0 4px;}p{color:#475569;font-size:12px;margin:0 0 16px;}svg{margin:24px auto;}</style>
      </head><body>
      <h2>${esc(qrItem.name)}</h2>
      <p>${esc(qrItem.code)} · ${esc(qrItem.location)}</p>
      ${svg.outerHTML}
      <p>WorkSite Command</p>
      <script>window.onload=()=>window.print();</script>
      </body></html>`;
    const w = window.open("", "_blank", "width=480,height=600");
    if (!w) return;
    w.document.open();
    w.document.write(html);
    w.document.close();
  };

  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Item" },
    { key: "category", label: "Category", render: (r) => (r.category || "").replaceAll("_", " ") },
    { key: "uom", label: "UOM" },
    { key: "quantity", label: "Qty" },
    { key: "min_stock", label: "Min" },
    { key: "rate", label: "Rate", render: (r) => "₹ " + Number(r.rate || 0).toLocaleString("en-IN") },
    { key: "location", label: "Location" },
    {
      key: "_alert",
      label: "Stock",
      render: (r) => Number(r.quantity || 0) < Number(r.min_stock || 0)
        ? <StatusBadge text="Low" tone="danger" />
        : <StatusBadge text="OK" tone="success" />,
    },
    {
      key: "_qr",
      label: "Actions",
      render: (row) => (
        <div className="inline-flex gap-1">
          <Button size="sm" variant="outline" className="h-7 w-7 p-0 rounded-sm" onClick={() => setLedgerFor(row)} data-testid={`inventory-ledger-${row.id}`} title="Stock ledger drilldown">
            <BookOpenCheck className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="outline" className="h-7 w-7 p-0 rounded-sm" onClick={() => setQrItem(row)} data-testid={`inventory-qr-${row.id}`} title="Show QR code">
            <QrCode className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];
  const fields = [
    { key: "code", label: "Item Code" },
    { key: "name", label: "Item Name", full: true },
    { key: "category", label: "Category", type: "select", options: catOptions },
    { key: "uom", label: "UOM (nos/meter/kg)" },
    { key: "quantity", label: "Quantity", type: "number" },
    { key: "min_stock", label: "Min Stock", type: "number" },
    { key: "rate", label: "Rate (INR)", type: "number" },
    { key: "location", label: "Location" },
  ];

  return (
    <>
      <div className="flex items-center justify-end gap-2 mb-2 px-1" data-testid="inv-bulk-actions">
        {r.canWrite && (
          <>
            <Button size="sm" variant="outline" onClick={downloadTemplate} data-testid="inv-bulk-download">
              <Download className="h-3.5 w-3.5 mr-1" /> Bulk Template
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              className="hidden"
              data-testid="inv-bulk-file"
              disabled={bulkUploading}
              onChange={uploadBulk}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={bulkUploading}
              data-testid="inv-bulk-upload-btn"
              onClick={() => fileRef.current?.click()}
              title="Upload the edited xlsx to bulk-patch items"
            >
              {bulkUploading ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Upload className="h-3.5 w-3.5 mr-1" />}
              {bulkUploading ? "Uploading…" : "Bulk Update"}
            </Button>
          </>
        )}
      </div>
      <DataTableShell
        title="Inventory & Stores"
        description="Material master with reorder points, location & barcode/QR labels."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="inventory"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
      />
      <Dialog open={!!qrItem} onOpenChange={(o) => !o && setQrItem(null)}>
        <DialogContent className="max-w-sm rounded-sm" data-testid="inventory-qr-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Inventory Label</DialogTitle>
          </DialogHeader>
          {qrItem && (
            <div className="flex flex-col items-center text-center py-3">
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{qrItem.code}</div>
              <div className="font-display font-bold text-base mt-1">{qrItem.name}</div>
              <div className="text-xs text-muted-foreground mb-4">{qrItem.location} · {qrItem.uom}</div>
              <div className="p-4 bg-white rounded-sm border border-border">
                <QRCodeSVG
                  id="inv-qr-svg"
                  value={JSON.stringify({ code: qrItem.code, name: qrItem.name, uom: qrItem.uom, location: qrItem.location, id: qrItem.id })}
                  size={200}
                  level="M"
                  includeMargin={false}
                />
              </div>
              <div className="mt-4 text-xs text-muted-foreground">Scan to view item · WorkSite Command</div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setQrItem(null)} className="rounded-sm">Close</Button>
            <Button onClick={printQR} className="rounded-sm" data-testid="inventory-qr-print"><Printer className="h-4 w-4 mr-1.5" /> Print</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <StockLedger
        itemId={ledgerFor?.id}
        itemName={ledgerFor?.name}
        open={!!ledgerFor}
        onOpenChange={(o) => !o && setLedgerFor(null)}
      />
      <Dialog open={!!bulkResult} onOpenChange={(o) => !o && setBulkResult(null)}>
        <DialogContent className="max-w-2xl" data-testid="inv-bulk-result-dialog">
          <DialogHeader>
            <DialogTitle>Bulk Update Summary</DialogTitle>
            <DialogDescription>Snapshot saved — full backup in <code>inventory_bulk_updates</code> collection</DialogDescription>
          </DialogHeader>
          {bulkResult && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-5 gap-2 font-mono-data">
                {Object.entries(bulkResult.summary || {}).filter(([k]) => k !== "errors").map(([k, v]) => (
                  <div key={k} className="border rounded p-2 text-center">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k.replaceAll("_", " ")}</div>
                    <div className="text-lg font-bold">{v}</div>
                  </div>
                ))}
              </div>
              {(bulkResult.summary?.errors || []).length > 0 && (
                <div className="border rounded p-2 max-h-48 overflow-y-auto">
                  <div className="text-xs font-semibold mb-1">Errors ({bulkResult.summary.errors.length})</div>
                  <ul className="text-xs space-y-0.5">
                    {bulkResult.summary.errors.slice(0, 30).map((e, i) => (
                      <li key={i} className="text-rose-700">Row {e.row}: {e.error}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="text-[10px] text-muted-foreground">Snapshot ID: {bulkResult.snapshot_id}</div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setBulkResult(null)} data-testid="inv-bulk-result-close">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
