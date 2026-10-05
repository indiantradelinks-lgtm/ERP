/**
 * HR · Attendance Center → Google Sheet Sync.
 * Connect the monthly Google attendance sheet, preview the mapping, sync manually
 * or let the scheduler do it, and read the full sync report.
 */
import { useCallback, useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtDT } from "@/lib/datetime";
import { CloudDownload, Eye, Link2, RefreshCw, Save, TriangleAlert } from "lucide-react";

const TONE = { success: "bg-emerald-100 text-emerald-800 border-emerald-300",
               partial: "bg-amber-100 text-amber-800 border-amber-300",
               failed: "bg-rose-100 text-rose-800 border-rose-300" };

export default function GoogleSheetSync({ canWrite = true }) {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ sheet_url: "", gid: "", enabled: true, auto_sync: true, sync_hour_ist: 7, sync_minute_ist: 0, label: "" });
  const [runs, setRuns] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [report, setReport] = useState(null);

  const load = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([
        api.get("/hr2/attendance-gsheet/config"),
        api.get("/hr2/attendance-gsheet/runs?limit=15").catch(() => ({ data: [] })),
      ]);
      setCfg(c.data.config);
      setRuns(r.data || []);
      if (c.data.config) setForm((f) => ({ ...f, ...c.data.config }));
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (what) => {
    setBusy(what);
    try {
      if (what === "save") {
        await api.put("/hr2/attendance-gsheet/config", {
          sheet_url: form.sheet_url, gid: form.gid || "", enabled: !!form.enabled,
          auto_sync: !!form.auto_sync, sync_hour_ist: Number(form.sync_hour_ist) || 0,
          sync_minute_ist: Number(form.sync_minute_ist) || 0, label: form.label || "",
        });
        toast.success("Google Sheet connected");
        setPreview(null);
        await load();
      } else if (what === "preview") {
        const { data } = await api.get("/hr2/attendance-gsheet/preview");
        setPreview(data);
        toast.success(`${data.employees_in_sheet} employee(s) · ${data.matched} matched · ${data.date_count} day column(s)`);
      } else {
        const { data } = await api.post("/hr2/attendance-gsheet/sync", { dry_run: what === "dry" });
        setReport(data);
        toast[data.failed ? "warning" : "success"](
          `${what === "dry" ? "Dry run" : "Sync"} done — ${data.imported} new, ${data.updated} updated, ${data.skipped_locked} locked, ${data.failed} failed`);
        await load();
      }
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(""); }
  };

  const last = runs[0];
  const shown = report || last;

  return (
    <div className="space-y-4" data-testid="gsheet-sync-tab">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Link2 className="h-4 w-4 text-emerald-600" /> Google Sheet Attendance Connection
            {cfg?.last_sync_at && (
              <Badge variant="outline" className="text-[10px]" data-testid="gsheet-last-sync">
                Last sync {fmtDT(cfg.last_sync_at)}
              </Badge>
            )}
            {cfg?.last_sync_status && (
              <Badge variant="outline" className={`text-[10px] ${TONE[cfg.last_sync_status] || ""}`}>{cfg.last_sync_status}</Badge>
            )}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Attendance and OT are read straight from the sheet, employees are matched on <b>E-Code</b> against
            the Employee Master, and each day is stamped with the employee's project. Approved or locked days are never overwritten.
            Share the sheet as “Anyone with the link → Viewer” so the ERP can read it.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
            <div className="md:col-span-4">
              <Label className="text-xs">Google Sheet Link *</Label>
              <Input value={form.sheet_url || ""} disabled={!canWrite} placeholder="https://docs.google.com/spreadsheets/d/…"
                onChange={(e) => setForm({ ...form, sheet_url: e.target.value })} data-testid="gsheet-url" />
            </div>
            <div>
              <Label className="text-xs">Tab (gid)</Label>
              <Input value={form.gid || ""} disabled={!canWrite} placeholder="auto from link"
                onChange={(e) => setForm({ ...form, gid: e.target.value })} data-testid="gsheet-gid" />
            </div>
            <div>
              <Label className="text-xs">Label</Label>
              <Input value={form.label || ""} disabled={!canWrite} placeholder="e.g. Mysore site"
                onChange={(e) => setForm({ ...form, label: e.target.value })} data-testid="gsheet-label" />
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!form.enabled} disabled={!canWrite} className="h-4 w-4"
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })} data-testid="gsheet-enabled" />
              Connection active
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!form.auto_sync} disabled={!canWrite} className="h-4 w-4"
                onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })} data-testid="gsheet-auto" />
              Automatic daily sync
            </label>
            <div>
              <Label className="text-xs">Daily sync at (IST)</Label>
              <div className="flex gap-1">
                <Input type="number" min="0" max="23" className="w-16" value={form.sync_hour_ist ?? 7} disabled={!canWrite}
                  onChange={(e) => setForm({ ...form, sync_hour_ist: e.target.value })} data-testid="gsheet-hour" />
                <Input type="number" min="0" max="59" step="15" className="w-16" value={form.sync_minute_ist ?? 0} disabled={!canWrite}
                  onChange={(e) => setForm({ ...form, sync_minute_ist: e.target.value })} data-testid="gsheet-minute" />
              </div>
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              {canWrite && (
                <Button variant="outline" size="sm" onClick={() => act("save")} disabled={busy === "save" || !form.sheet_url}
                  data-testid="gsheet-save"><Save className="h-3.5 w-3.5 mr-1" /> {busy === "save" ? "Saving…" : "Save Connection"}</Button>
              )}
              <Button variant="outline" size="sm" onClick={() => act("preview")} disabled={busy === "preview" || !cfg}
                data-testid="gsheet-preview"><Eye className="h-3.5 w-3.5 mr-1" /> {busy === "preview" ? "Reading…" : "Preview Sheet"}</Button>
              {canWrite && (
                <>
                  <Button variant="outline" size="sm" onClick={() => act("dry")} disabled={busy === "dry" || !cfg}
                    data-testid="gsheet-dry-run">{busy === "dry" ? "Checking…" : "Dry Run"}</Button>
                  <Button size="sm" onClick={() => act("sync")} disabled={busy === "sync" || !cfg} data-testid="gsheet-sync">
                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${busy === "sync" ? "animate-spin" : ""}`} />
                    {busy === "sync" ? "Syncing…" : "Sync Now"}
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {preview && (
        <Card data-testid="gsheet-preview-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Sheet Preview — {preview.month} · {preview.date_from} → {preview.date_to} · {preview.date_count} day column(s)
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {preview.employees_in_sheet} employee(s) in the sheet · <b className="text-emerald-700">{preview.matched} matched</b> to the Employee Master
              {preview.employees_in_sheet - preview.matched > 0 && <span className="text-amber-700"> · {preview.employees_in_sheet - preview.matched} unmatched</span>}
            </p>
          </CardHeader>
          <CardContent>
            <div className="border rounded-sm overflow-x-auto max-h-72">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>E-Code</TableHead><TableHead>Name in Sheet</TableHead>
                  <TableHead>Match</TableHead><TableHead className="text-right">Days</TableHead>
                  <TableHead className="text-right">Total OT</TableHead><TableHead>First days</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {preview.sample.map((s) => (
                    <TableRow key={s.emp_code} data-testid={`gsheet-prev-${s.emp_code}`}>
                      <TableCell className="font-mono text-xs">{s.emp_code}</TableCell>
                      <TableCell className="text-sm">{s.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${s.matched ? TONE.success : TONE.failed}`}>
                          {s.matched ? "matched" : "not in ERP"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right text-xs">{s.days_with_status}</TableCell>
                      <TableCell className="text-right text-xs">{s.total_ot}</TableCell>
                      <TableCell className="text-[10px] text-muted-foreground">
                        {s.first_days.map((d) => `${d.date.slice(8)}:${d.status_raw}${d.ot_raw ? `+${d.ot_raw}h` : ""}`).join("  ")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {shown && (
        <Card data-testid="gsheet-report">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <CloudDownload className="h-4 w-4" /> Sync Report
              <Badge variant="outline" className={`text-[10px] ${TONE[shown.status] || ""}`}>{shown.status}</Badge>
              {shown.dry_run && <Badge variant="outline" className="text-[10px]">dry run</Badge>}
              <span className="text-xs font-normal text-muted-foreground">
                {fmtDT(shown.finished_at)} · {shown.trigger} · {shown.by}
              </span>
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {shown.month} · {shown.date_from} → {shown.date_to} · {shown.matched_employees} of {shown.sheet_employees} employee(s) matched
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Stat label="Imported" value={shown.imported} testid="gsheet-stat-imported" tone="text-emerald-700" />
              <Stat label="Updated" value={shown.updated} testid="gsheet-stat-updated" tone="text-sky-700" />
              <Stat label="Unchanged" value={shown.unchanged} testid="gsheet-stat-unchanged" />
              <Stat label="Skipped (locked)" value={shown.skipped_locked} testid="gsheet-stat-skipped" tone="text-amber-700" />
              <Stat label="Failed" value={shown.failed} testid="gsheet-stat-failed" tone="text-rose-700" />
            </div>
            {(shown.errors || []).length > 0 && (
              <div className="border border-amber-200 bg-amber-50 rounded-sm p-3" data-testid="gsheet-errors">
                <div className="text-xs font-semibold text-amber-900 mb-1 flex items-center gap-1">
                  <TriangleAlert className="h-3 w-3" /> Error report ({shown.errors.length})
                </div>
                <ul className="text-xs text-amber-900 space-y-0.5 max-h-48 overflow-y-auto">
                  {shown.errors.map((e, i) => (
                    <li key={i}>{e.emp_code ? `${e.emp_code} ` : ""}{e.employee_name ? `· ${e.employee_name} ` : ""}{e.date ? `· ${e.date} ` : ""}— {e.error}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {runs.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Sync History</CardTitle></CardHeader>
          <CardContent>
            <div className="border rounded-sm overflow-x-auto">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Sync Date / Time</TableHead><TableHead>Trigger</TableHead><TableHead>By</TableHead>
                  <TableHead>Month</TableHead><TableHead className="text-right">Imported</TableHead>
                  <TableHead className="text-right">Updated</TableHead><TableHead className="text-right">Skipped</TableHead>
                  <TableHead className="text-right">Failed</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {runs.map((r) => (
                    <TableRow key={r.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setReport(r)} data-testid={`gsheet-run-${r.id}`}>
                      <TableCell className="text-xs whitespace-nowrap">{fmtDT(r.finished_at)}</TableCell>
                      <TableCell className="text-xs">{r.trigger}{r.dry_run ? " (dry)" : ""}</TableCell>
                      <TableCell className="text-xs">{r.by}</TableCell>
                      <TableCell className="text-xs">{r.month || "—"}</TableCell>
                      <TableCell className="text-right text-xs">{r.imported}</TableCell>
                      <TableCell className="text-right text-xs">{r.updated}</TableCell>
                      <TableCell className="text-right text-xs">{r.skipped_locked}</TableCell>
                      <TableCell className="text-right text-xs">{r.failed}</TableCell>
                      <TableCell><Badge variant="outline" className={`text-[10px] ${TONE[r.status] || ""}`}>{r.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, testid, tone = "" }) {
  return (
    <div className="border rounded-sm p-3 bg-card" data-testid={testid}>
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className={`text-lg font-bold ${tone}`}>{value ?? 0}</div>
    </div>
  );
}
