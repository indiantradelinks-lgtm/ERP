import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Upload, FileDown, History } from "lucide-react";

const CATS = ["material", "labour", "transport", "subcontract", "service", "other"];
const fmt = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 });

export const DirectBookingDialog = ({ onClose }) => {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ vendor_name: "", invoice_no: "", invoice_date: "", project_id: "", expense_category: "other", taxable_value: "", gst_amount: "", tds_amount: "", remarks: "" });
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const gross = Number(form.taxable_value || 0) + Number(form.gst_amount || 0);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/payables/vendor-bills/direct", {
        ...form,
        taxable_value: Number(form.taxable_value || 0),
        gst_amount: Number(form.gst_amount || 0),
        tds_amount: Number(form.tds_amount || 0),
      });
      toast.success(`${data.bill_no} booked — ${fmt(data.amount)} added to project ${data.project_code} cost`);
      onClose(true);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to book"));
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (file) => {
    setImporting(true);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/payables/vendor-bills/direct/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setImportResult(data);
      if (data.inserted) toast.success(`${data.inserted} bill(s) booked${data.errors.length ? `, ${data.errors.length} row(s) skipped` : ""}`);
      else toast.error("No rows imported — check errors below");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Import failed"));
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const downloadTemplate = async () => {
    const res = await api.get("/payables/vendor-bills/direct/template", { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url; a.download = "direct_cost_booking_template.xlsx"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(!!importResult?.inserted)}>
      <DialogContent className="max-w-2xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="direct-booking-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><History className="h-4 w-4" /> Direct Cost Booking (Historical / Pre-ERP)</DialogTitle>
          <DialogDescription>
            For bills where PO & GRN were completed before ERP. Books instantly to the project's cost with a HISTORICAL tag (treated as already paid). Use the actual past bill date.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div><Label className="text-xs">Vendor Name *</Label><Input value={form.vendor_name} onChange={set("vendor_name")} className="rounded-sm" data-testid="db-vendor" /></div>
          <div><Label className="text-xs">Bill / Invoice No *</Label><Input value={form.invoice_no} onChange={set("invoice_no")} className="rounded-sm" data-testid="db-invoice-no" /></div>
          <div><Label className="text-xs">Bill Date (actual) *</Label><Input type="date" value={form.invoice_date} onChange={set("invoice_date")} className="rounded-sm" data-testid="db-date" /></div>
          <div>
            <Label className="text-xs">Project *</Label>
            <select value={form.project_id} onChange={set("project_id")} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="db-project">
              <option value="">— select project —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.code || p.project_code} · {p.name}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-xs">Expense Category *</Label>
            <select value={form.expense_category} onChange={set("expense_category")} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="db-category">
              {CATS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div><Label className="text-xs">Basic Amount *</Label><Input type="number" min="0" value={form.taxable_value} onChange={set("taxable_value")} className="rounded-sm text-right" data-testid="db-basic" /></div>
          <div><Label className="text-xs">GST Amount</Label><Input type="number" min="0" value={form.gst_amount} onChange={set("gst_amount")} className="rounded-sm text-right" data-testid="db-gst" /></div>
          <div><Label className="text-xs">TDS Amount</Label><Input type="number" min="0" value={form.tds_amount} onChange={set("tds_amount")} className="rounded-sm text-right" data-testid="db-tds" /></div>
          <div className="col-span-2"><Label className="text-xs">Remarks</Label><Input value={form.remarks} onChange={set("remarks")} placeholder='e.g. "Opening cost booking — Nov 2025" or old PO/GRN reference' className="rounded-sm" data-testid="db-remarks" /></div>
        </div>
        <div className="text-sm text-right font-semibold" data-testid="db-gross">Gross (books to project): {fmt(gross)}</div>

        <div className="border-t pt-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Bulk import old bills (Excel)</div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-sm" onClick={downloadTemplate} data-testid="db-template-btn"><FileDown className="h-3.5 w-3.5 mr-1" /> Template</Button>
            <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} data-testid="db-import-input" />
            <Button size="sm" variant="outline" className="rounded-sm" onClick={() => fileRef.current?.click()} disabled={importing} data-testid="db-import-btn">
              {importing ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Upload className="h-3.5 w-3.5 mr-1" />} Upload filled sheet
            </Button>
          </div>
          {importResult && (
            <div className="mt-2 text-xs" data-testid="db-import-result">
              <span className="text-emerald-700 font-semibold">{importResult.inserted} booked.</span>
              {importResult.errors.length > 0 && (
                <div className="mt-1 max-h-28 overflow-y-auto border border-red-200 bg-red-50 rounded-sm p-1.5 text-red-700">
                  {importResult.errors.map((e, i) => <div key={i}>Row {e.row}: {e.error}</div>)}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onClose(!!importResult?.inserted)} data-testid="db-cancel">Close</Button>
          <Button className="rounded-sm" onClick={save} disabled={busy || !form.vendor_name || !form.invoice_no || !form.invoice_date || !form.project_id || !Number(form.taxable_value)} data-testid="db-save">
            {busy && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Book Cost
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DirectBookingDialog;
