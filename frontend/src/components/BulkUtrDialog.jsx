import { useRef, useState } from "react";
import { Upload, Download, FileSpreadsheet, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

/** Bulk UTR upload → validate → bulk Mark Paid (Accounts · Payment Processing Center). */
export default function BulkUtrDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [check, setCheck] = useState(null);   // validate result
  const [result, setResult] = useState(null); // apply result
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  const reset = () => { setFile(null); setCheck(null); setResult(null); };

  const downloadTemplate = async () => {
    try {
      const res = await api.get("/accounts/payment-queue/bulk-utr/template", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `bulk_utr_template_${new Date().toISOString().slice(0, 10)}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.response?.data?.detail || "Template download failed"); }
  };

  const validate = async (f) => {
    setBusy(true); setResult(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/accounts/payment-queue/bulk-utr/validate", fd);
      setCheck(data);
      if (!data.valid.length) toast.warning("No valid rows to mark paid — see errors below");
    } catch (e) { toast.error(e.response?.data?.detail || "Validation failed"); setCheck(null); }
    finally { setBusy(false); }
  };

  const onPick = (e) => { const f = e.target.files?.[0]; if (!f) return; setFile(f); validate(f); e.target.value = ""; };

  const apply = async () => {
    if (!file || !check?.valid?.length) return;
    if (!window.confirm(`Mark ${check.valid.length} payment(s) as PAID with the uploaded UTR numbers? This posts payment vouchers and sends payment advices.`)) return;
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/accounts/payment-queue/bulk-utr/apply", fd);
      setResult(data);
      if (data.paid.length) toast.success(`${data.paid.length} payment(s) marked paid`);
      if (data.failed.length) toast.error(`${data.failed.length} row(s) failed — see details`);
      onDone?.();
    } catch (e) { toast.error(e.response?.data?.detail || "Bulk update failed"); }
    finally { setBusy(false); }
  };

  const errors = [...(check?.errors || []), ...(result?.failed || [])];
  return (
    <>
      <Button size="sm" variant="outline" className="rounded-sm h-9" onClick={() => { reset(); setOpen(true); }} data-testid="ppc-bulk-utr-btn">
        <Upload className="h-3.5 w-3.5 mr-1" /> Bulk UTR Upload
      </Button>
      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
        <DialogContent className="max-w-4xl rounded-sm max-h-[88vh] overflow-y-auto" data-testid="ppc-bulk-utr-dialog">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><FileSpreadsheet className="h-4 w-4 text-primary" /> Bulk UTR Upload / Bulk Mark Paid</DialogTitle>
            <DialogDescription className="text-xs">1. Download the template (pre-filled with every payment awaiting UTR) · 2. Enter UTR numbers against each Request No · 3. Upload — we validate every row, then mark the valid ones paid in one go.</DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-sm" onClick={downloadTemplate} data-testid="ppc-bulk-utr-template">
              <Download className="h-3.5 w-3.5 mr-1" /> Download Excel template
            </Button>
            <input ref={inputRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={onPick} data-testid="ppc-bulk-utr-file" />
            <Button size="sm" className="rounded-sm" onClick={() => inputRef.current?.click()} disabled={busy} data-testid="ppc-bulk-utr-pick">
              <Upload className="h-3.5 w-3.5 mr-1" /> {file ? "Choose another file" : "Upload filled Excel"}
            </Button>
            {file && <span className="text-xs text-muted-foreground truncate max-w-[280px]" data-testid="ppc-bulk-utr-filename">{file.name}</span>}
            {busy && <span className="text-xs text-primary">Working…</span>}
          </div>

          {check && !result && (
            <div className="grid grid-cols-3 gap-2 text-center text-xs" data-testid="ppc-bulk-utr-summary">
              <div className="border border-border rounded-sm py-2"><div className="text-lg font-bold text-success">{check.valid.length}</div>ready to mark paid</div>
              <div className="border border-border rounded-sm py-2"><div className="text-lg font-bold text-destructive">{check.errors.length}</div>invalid / unmatched</div>
              <div className="border border-border rounded-sm py-2"><div className="text-lg font-bold text-muted-foreground">{check.skipped}</div>skipped (blank UTR)</div>
            </div>
          )}

          {result && (
            <div className="border border-success/40 bg-success/5 rounded-sm p-3 text-sm flex items-center gap-2" data-testid="ppc-bulk-utr-result">
              <CheckCircle2 className="h-4 w-4 text-success" /> <b>{result.paid.length}</b> marked paid · {result.failed.length} failed · {result.errors.length} invalid · {result.skipped} skipped
            </div>
          )}

          {check?.valid?.length > 0 && !result && (
            <div className="border border-border rounded-sm overflow-x-auto">
              <Table>
                <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase">Request No</TableHead><TableHead className="text-[10px] uppercase">Vendor</TableHead>
                  <TableHead className="text-[10px] uppercase">UTR No</TableHead><TableHead className="text-[10px] uppercase">Paid Date</TableHead>
                  <TableHead className="text-[10px] uppercase text-right">Net Payable</TableHead><TableHead className="text-[10px] uppercase">Stage</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {check.valid.map((r) => (
                    <TableRow key={r.request_no} data-testid={`ppc-bulk-valid-${r.request_no}`}>
                      <TableCell className="font-mono-data text-xs">{r.request_no}</TableCell><TableCell className="text-sm">{r.vendor_name || "—"}</TableCell>
                      <TableCell className="font-mono-data text-xs">{r.utr_no}</TableCell><TableCell className="text-xs">{r.paid_date}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs">₹{inr(r.net_payable)}</TableCell><TableCell className="text-xs">{r.stage}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {result?.paid?.length > 0 && (
            <div className="text-xs text-muted-foreground" data-testid="ppc-bulk-utr-paid-list">
              Paid: {result.paid.map((p) => `${p.request_no} → ${p.utr_no}`).join(" · ")}
            </div>
          )}

          {errors.length > 0 && (
            <div className="border border-destructive/40 rounded-sm overflow-x-auto" data-testid="ppc-bulk-utr-errors">
              <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-destructive flex items-center gap-1 bg-destructive/5"><AlertTriangle className="h-3 w-3" /> Rows needing attention ({errors.length})</div>
              <Table>
                <TableHeader><TableRow className="hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase">Excel row</TableHead><TableHead className="text-[10px] uppercase">Request No</TableHead>
                  <TableHead className="text-[10px] uppercase">UTR No</TableHead><TableHead className="text-[10px] uppercase">Problem</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {errors.map((e, i) => (
                    <TableRow key={`${e.row}-${i}`} data-testid={`ppc-bulk-error-${e.row}`}>
                      <TableCell className="text-xs">{e.row}</TableCell><TableCell className="font-mono-data text-xs">{e.request_no || "—"}</TableCell>
                      <TableCell className="font-mono-data text-xs">{e.utr_no || "—"}</TableCell><TableCell className="text-xs text-destructive">{e.error}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Close</Button>
            {!result && <Button className="rounded-sm" onClick={apply} disabled={busy || !check?.valid?.length} data-testid="ppc-bulk-utr-apply">
              <CheckCircle2 className="h-4 w-4 mr-1" /> Mark {check?.valid?.length || 0} as Paid
            </Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
