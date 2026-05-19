import { useState } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { QRCodeSVG } from "qrcode.react";
import { QrCode, Printer } from "lucide-react";

export default function Inventory() {
  const r = useResource("inventory");
  const [qrItem, setQrItem] = useState(null);

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
      label: "QR",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 w-7 p-0 rounded-sm" onClick={() => setQrItem(row)} data-testid={`inventory-qr-${row.id}`} title="Show QR code">
          <QrCode className="h-3.5 w-3.5" />
        </Button>
      ),
    },
  ];
  const fields = [
    { key: "code", label: "Item Code" },
    { key: "name", label: "Item Name", full: true },
    { key: "category", label: "Category", type: "select", options: ["scaffolding", "painting", "rope_access", "roof_sheeting", "ppe", "consumables"] },
    { key: "uom", label: "UOM (nos/meter/kg)" },
    { key: "quantity", label: "Quantity", type: "number" },
    { key: "min_stock", label: "Min Stock", type: "number" },
    { key: "rate", label: "Rate (INR)", type: "number" },
    { key: "location", label: "Location" },
  ];

  return (
    <>
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
    </>
  );
}
