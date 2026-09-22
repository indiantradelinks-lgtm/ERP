/**
 * Attendance Import tab — AI punch-machine import (preview → commit → history/rollback)
 * + row-based Excel bulk update (template / upload / error report).
 */
import { useEffect, useRef, useState } from "react";
import { Bot, Download, FileUp, History, RotateCcw, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import { fmtDT } from "@/lib/datetime";

const FLAG_TONE = {
  duplicate: "bg-amber-100 text-amber-800 border-amber-300",
  missing_punch: "bg-orange-100 text-orange-800 border-orange-300",
  unmatched_employee: "bg-red-100 text-red-800 border-red-300",
  locked: "bg-red-100 text-red-800 border-red-300",
  future_date: "bg-slate-100 text-slate-600 border-slate-300",
  no_punch_time: "bg-slate-100 text-slate-600 border-slate-300",
  machine_absent: "bg-rose-50 text-rose-700 border-rose-200",
  existing_kept: "bg-sky-50 text-sky-700 border-sky-200",
};

export default function AttendanceImport() {
  const aiRef = useRef(null);
  const xlRef = useRef(null);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const [xlResult, setXlResult] = useState(null);
  const { rows: history, pagination: histPg, reload: loadHistory } = usePagedList("/hr2/attendance-plus/punch-imports", {}, {
    viewKey: "hr_punch_imports", errorLabel: "import history", pageSize: 25, defaultSort: { by: "at", dir: "desc" },
  });


  const aiUpload = async (file) => {
    if (!file) return;
    setBusy("ai");
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post("/hr2/attendance-plus/punch-import/preview", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(r.data);
      const um = r.data.unmatched_employees?.length || 0;
      const msg = `${r.data.total_rows} record(s) · ${r.data.matched_employees} employee(s) matched by Legacy Emp Code${um ? ` · ${um} unmatched` : ""} — review & confirm`;
      um ? toast.warning(msg) : toast.success(msg);
    } catch (e) { toast.error(e.response?.data?.detail || "AI import failed"); }
    finally { setBusy(""); if (aiRef.current) aiRef.current.value = ""; }
  };

  const commit = async () => {
    setBusy("commit");
    try {
      const r = await api.post(`/hr2/attendance-plus/punch-import/${preview.batch_id}/commit`, { overwrite: true });
      toast.success(`Imported — ${r.data.created} created, ${r.data.updated} overwritten, ${r.data.skipped} skipped`);
      setPreview(null);
      loadHistory();
    } catch (e) { toast.error(e.response?.data?.detail || "Commit failed"); }
    finally { setBusy(""); }
  };

  const rollback = async (b) => {
    if (!window.confirm(`Rollback import "${b.file_name}"? Created rows are removed and overwritten rows restored.`)) return;
    try {
      const r = await api.post(`/hr2/attendance-plus/punch-import/${b.id}/rollback`);
      toast.success(`Rolled back — ${r.data.removed} removed, ${r.data.restored} restored`);
      loadHistory();
    } catch (e) { toast.error(e.response?.data?.detail || "Rollback failed"); }
  };

  const template = async () => {
    try {
      const r = await api.get("/hr2/attendance-plus/bulk-rows/template", { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = "attendance_bulk_rows_template.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Template download failed"); }
  };

  const xlUpload = async (file) => {
    if (!file) return;
    setBusy("xl");
    setXlResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post("/hr2/attendance-plus/bulk-rows/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setXlResult(r.data);
      toast.success(`Uploaded — ${r.data.created} created, ${r.data.updated} updated${r.data.error_count ? `, ${r.data.error_count} error(s)` : ""}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    finally { setBusy(""); if (xlRef.current) xlRef.current.value = ""; }
  };

  return (
    <div className="space-y-4" data-testid="attendance-import-tab">
      {/* AI Punch Import */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="font-display font-bold text-lg flex items-center gap-2"><Bot className="h-5 w-5 text-violet-600" /> AI Punch Machine Import</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Upload any biometric export (Excel / CSV / TXT / DAT). Per-employee machine reports (e.g. MyOfficeGuardian) are parsed directly; other layouts are AI-detected. Punch-machine Employee ID is matched to Employee Master → Legacy Emp Code. Duplicates are overwritten on confirm.</p>
          </div>
          <input ref={aiRef} type="file" accept=".xlsx,.xls,.csv,.txt,.dat" className="hidden" onChange={(e) => aiUpload(e.target.files?.[0])} data-testid="ai-punch-file" />
          <Button className="bg-violet-600 hover:bg-violet-700" disabled={busy === "ai"} onClick={() => aiRef.current?.click()} data-testid="ai-punch-upload-btn">
            <FileUp className="h-4 w-4 mr-1.5" /> {busy === "ai" ? "AI analysing…" : "Upload Punch File"}
          </Button>
        </div>

        {preview && (
          <div className="space-y-2" data-testid="ai-punch-preview">
            <div className="flex items-center gap-3 flex-wrap text-sm">
              <span className="font-semibold">{preview.total_rows} record(s)</span>
              <span className="text-emerald-700">{preview.importable} importable</span>
              <span className="text-slate-600" data-testid="ai-punch-matched">{preview.matched_employees ?? 0} employee(s) matched</span>
              {preview.unmatched_employees?.length > 0 && <span className="text-red-600" data-testid="ai-punch-unmatched">{preview.unmatched_employees.length} unmatched Legacy Emp Code(s)</span>}
              <span className="text-amber-700">{preview.duplicates} duplicate(s) will be overwritten</span>
              {preview.exceptions.length > 0 && <span className="text-red-600">{preview.exceptions.length} exception(s)</span>}
              <div className="ml-auto flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setPreview(null)} data-testid="ai-punch-cancel">Cancel</Button>
                <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" disabled={busy === "commit" || preview.importable === 0} onClick={commit} data-testid="ai-punch-commit">
                  {busy === "commit" ? "Importing…" : `Confirm Import (${preview.importable})`}
                </Button>
              </div>
            </div>
            <div className="border rounded-sm overflow-x-auto max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 uppercase text-slate-600 sticky top-0">
                  <tr><th className="text-left px-2 py-1.5">Employee</th><th className="text-left px-2 py-1.5">Date</th>
                    <th className="text-left px-2 py-1.5">In</th><th className="text-left px-2 py-1.5">Out</th>
                    <th className="text-right px-2 py-1.5">Hours</th><th className="text-right px-2 py-1.5">OT</th>
                    <th className="text-right px-2 py-1.5">Late (min)</th><th className="text-left px-2 py-1.5">Status</th>
                    <th className="text-left px-2 py-1.5">Flags</th></tr>
                </thead>
                <tbody>
                  {preview.rows.map((r, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1">{r.employee_name || r.employee_code}{r.employee_code ? <span className="ml-1 font-mono-data text-slate-500">[{r.employee_code}]</span> : null}</td>
                      <td className="px-2 py-1 font-mono-data">{r.date}</td>
                      <td className="px-2 py-1">{r.in_time || "—"}</td>
                      <td className="px-2 py-1">{r.out_time || "—"}</td>
                      <td className="px-2 py-1 text-right tabular">{r.working_hours ?? "—"}</td>
                      <td className="px-2 py-1 text-right tabular">{r.overtime_hours ?? 0}</td>
                      <td className="px-2 py-1 text-right tabular">{r.late_minutes || 0}</td>
                      <td className="px-2 py-1">{(r.status || "").replaceAll("_", " ")}</td>
                      <td className="px-2 py-1">
                        {(r.flags || []).map((f) => (
                          <span key={f} className={`inline-block mr-1 px-1.5 py-0.5 rounded border text-[10px] ${FLAG_TONE[f] || "bg-slate-100"}`}>{f.replaceAll("_", " ")}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.unmatched_employees?.length > 0 && (
              <div className="text-xs bg-amber-50 border border-amber-200 rounded-sm p-2" data-testid="ai-punch-unmatched-list">
                <span className="font-semibold">Not in Employee Master (add the punch-machine ID as Legacy Emp Code to map):</span> {preview.unmatched_employees.join(", ")}
              </div>
            )}
            {preview.exceptions.length > 0 && (
              <div className="text-xs bg-red-50 border border-red-200 rounded-sm p-2 max-h-28 overflow-y-auto" data-testid="ai-punch-exceptions">
                {preview.exceptions.slice(0, 30).map((x, i) => <div key={i}>• {x.date} — {x.who}: {x.issue}</div>)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Excel row bulk update */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="font-display font-bold text-lg flex items-center gap-2"><Upload className="h-5 w-5 text-blue-600" /> Excel Bulk Update (Row-based)</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Template columns: Employee Code · Name · Date · Shift · Status (P/A/HD/L/WO/OD) · In Time · Out Time · OT Hours · Remarks. Rows are validated; invalid rows come back as an error report.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={template} data-testid="bulk-rows-template-btn"><Download className="h-4 w-4 mr-1.5" /> Download Template</Button>
            <input ref={xlRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => xlUpload(e.target.files?.[0])} data-testid="bulk-rows-file" />
            <Button disabled={busy === "xl"} onClick={() => xlRef.current?.click()} data-testid="bulk-rows-upload-btn">
              <FileUp className="h-4 w-4 mr-1.5" /> {busy === "xl" ? "Uploading…" : "Upload Excel"}
            </Button>
          </div>
        </div>
        {xlResult && (
          <div className="text-sm" data-testid="bulk-rows-result">
            <span className="text-emerald-700 font-semibold">{xlResult.created} created</span> · <span className="text-blue-700 font-semibold">{xlResult.updated} updated</span>
            {xlResult.error_count > 0 && (
              <div className="mt-2 text-xs bg-red-50 border border-red-200 rounded-sm p-2 max-h-32 overflow-y-auto">
                <div className="font-semibold text-red-700 mb-1">{xlResult.error_count} error(s):</div>
                {xlResult.errors.map((e, i) => <div key={i}>• Row {e.row}: {e.error}</div>)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Import history */}
      <div className="bg-card border border-border rounded-sm p-4">
        <h3 className="font-display font-bold text-lg flex items-center gap-2 mb-2"><History className="h-5 w-5 text-slate-500" /> Punch Import History</h3>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr><th className="text-left px-2 py-1.5">File</th><th className="text-left px-2 py-1.5">By</th>
              <th className="text-left px-2 py-1.5">At</th><th className="text-left px-2 py-1.5">Dates</th>
              <th className="text-left px-2 py-1.5">Result</th><th className="text-left px-2 py-1.5">Status</th><th></th></tr>
          </thead>
          <tbody>
            {history.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-slate-400">No imports yet.</td></tr>}
            {history.map((b) => (
              <tr key={b.id} className="border-t" data-testid={`punch-batch-${b.id}`}>
                <td className="px-2 py-1.5 font-mono-data text-xs">{b.file_name}</td>
                <td className="px-2 py-1.5 text-xs">{b.uploaded_by}</td>
                <td className="px-2 py-1.5 text-xs">{fmtDT(b.at)}</td>
                <td className="px-2 py-1.5 text-xs">{(b.dates || []).slice(0, 3).join(", ")}{(b.dates || []).length > 3 ? "…" : ""}</td>
                <td className="px-2 py-1.5 text-xs">{b.result ? `${b.result.created}C / ${b.result.updated}U / ${b.result.skipped}S` : "—"}</td>
                <td className="px-2 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase ${b.status === "committed" ? "bg-emerald-50 border-emerald-300 text-emerald-700" : b.status === "rolled_back" ? "bg-red-50 border-red-300 text-red-700" : "bg-slate-50 border-slate-300 text-slate-600"}`}>{b.status}</span>
                </td>
                <td className="px-2 py-1.5 text-right">
                  {b.status === "committed" && (
                    <Button size="sm" variant="outline" className="h-7 text-red-600 border-red-300" onClick={() => rollback(b)} data-testid={`punch-rollback-${b.id}`}>
                      <RotateCcw className="h-3 w-3 mr-1" /> Rollback
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-3 py-2 border-t border-border"><TablePager pagination={histPg} testidPrefix="punch-hist" /></div>
      </div>
    </div>
  );
}
