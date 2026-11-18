/**
 * HR · Attendance Center → Google Sheet Sync.
 * Connect up to 40 monthly Google attendance sheets, sync them all at once
 * (manual or scheduled) and read per-sheet status + error reports.
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
import { CloudDownload, Eye, Link2, Pencil, Plus, RefreshCw, Save, Trash2, TriangleAlert } from "lucide-react";

const TONE = { success: "bg-emerald-100 text-emerald-800 border-emerald-300",
               partial: "bg-amber-100 text-amber-800 border-amber-300",
               failed: "bg-rose-100 text-rose-800 border-rose-300" };

export default function GoogleSheetSync({ canWrite = true }) {
  const [cfg, setCfg] = useState(null);
  const [sheets, setSheets] = useState([]);
  const [maxSheets, setMaxSheets] = useState(40);
  const [settings, setSettings] = useState({ enabled: true, auto_sync: true, sync_hour_ist: 7, sync_minute_ist: 0 });
  const [add, setAdd] = useState({ sheet_url: "", gid: "", label: "" });
  const [runs, setRuns] = useState([]);
  const [preview, setPreview] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([
        api.get("/hr2/attendance-gsheet/config"),
        api.get("/hr2/attendance-gsheet/runs?limit=15").catch(() => ({ data: [] })),
      ]);
      setCfg(c.data.config);
      setSheets(c.data.sheets || []);
      setMaxSheets(c.data.max_sheets || null);
      if (c.data.config) setSettings((s) => ({ ...s, ...c.data.config }));
      setRuns(r.data || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async (key, fn, okMsg) => {
    setBusy(key);
    try { const out = await fn(); if (okMsg) toast.success(typeof okMsg === "function" ? okMsg(out) : okMsg); await load(); return out; }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(""); }
  };

  const saveSettings = () => run("settings", () => api.put("/hr2/attendance-gsheet/config", {
    enabled: !!settings.enabled, auto_sync: !!settings.auto_sync,
    sync_hour_ist: Number(settings.sync_hour_ist) || 0, sync_minute_ist: Number(settings.sync_minute_ist) || 0,
  }), "Sync settings saved");

  const addSheet = () => run("add", async () => {
    await api.post("/hr2/attendance-gsheet/sheets", add);
    setAdd({ sheet_url: "", gid: "", label: "" });
  }, "Google Sheet connected");

  const [edit, setEdit] = useState(null); // {id, gid, label, sheet_url}
  const saveEdit = () => run(`e-${edit.id}`, async () => {
    const cur = sheets.find((x) => x.id === edit.id);
    await api.put(`/hr2/attendance-gsheet/sheets/${edit.id}`,
      { sheet_url: edit.sheet_url || cur.sheet_url, gid: (edit.gid || "").trim(), label: (edit.label || "").trim(), enabled: cur.enabled !== false });
    setEdit(null);
  }, "Sheet tab updated — the next sync reads the new tab");

  const toggleSheet = (s) => run(`t-${s.id}`, () => api.put(`/hr2/attendance-gsheet/sheets/${s.id}`,
    { sheet_url: s.sheet_url, gid: s.gid, label: s.label, enabled: !s.enabled }),
    `${s.label} ${s.enabled ? "paused" : "activated"}`);

  const removeSheet = (s) => {
    if (!window.confirm(`Remove "${s.label}" from the attendance sync?`)) return;
    run(`d-${s.id}`, () => api.delete(`/hr2/attendance-gsheet/sheets/${s.id}`), "Sheet removed");
  };

  const previewSheet = (s) => run(`p-${s.id}`, async () => {
    const { data } = await api.get(`/hr2/attendance-gsheet/preview?sheet_row_id=${s.id}`);
    setPreview(data);
    return data;
  }, (d) => `${d.label}: ${d.employees_in_sheet} employee(s) · ${d.matched} matched · ${d.date_count} day column(s)`);

  const sync = (dry, sheet_ids = []) => run(dry ? "dry" : "sync", async () => {
    const { data } = await api.post("/hr2/attendance-gsheet/sync", { dry_run: dry, sheet_ids });
    setReport(data);
    return data;
  }, (d) => `${d.dry_run ? "Dry run" : "Sync"} — ${d.sheets_synced} sheet(s): ${d.imported} new, ${d.updated} updated, ${d.skipped_locked} locked, ${d.failed} failed`);

  const shown = report || runs[0];
  const active = sheets.filter((s) => s.enabled !== false).length;

  return (
    <div className="space-y-4" data-testid="gsheet-sync-tab">
      {/* ── Connections ─────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Link2 className="h-4 w-4 text-emerald-600" /> Google Sheet Attendance Connections
            <Badge variant="outline" className="text-[10px]" data-testid="gsheet-count">{sheets.length} connected{maxSheets ? ` of ${maxSheets}` : ""} · {active} active</Badge>
            {cfg?.last_sync_at && <Badge variant="outline" className="text-[10px]" data-testid="gsheet-last-sync">Last sync {fmtDT(cfg.last_sync_at)}</Badge>}
            {cfg?.last_sync_status && <Badge variant="outline" className={`text-[10px] ${TONE[cfg.last_sync_status] || ""}`}>{cfg.last_sync_status}</Badge>}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Add one link per project sheet — no limit on connections. When a new month's tab is created, click the pencil on
            the row and update its <b>Tab (gid)</b>; the scheduled sync picks up the new tab automatically.
            Employees are matched on <b>E-Code</b> and each day is stamped with the employee's project.
            Approved or locked days are never overwritten. Share each sheet as “Anyone with the link → Viewer”.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {canWrite && (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end border border-dashed border-border rounded-sm p-2">
              <div className="md:col-span-6">
                <Label className="text-xs">Google Sheet Link</Label>
                <Input value={add.sheet_url} placeholder="https://docs.google.com/spreadsheets/d/…"
                  onChange={(e) => setAdd({ ...add, sheet_url: e.target.value })} data-testid="gsheet-url" />
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs">Tab (gid)</Label>
                <Input value={add.gid} placeholder="auto" onChange={(e) => setAdd({ ...add, gid: e.target.value })} data-testid="gsheet-gid" />
              </div>
              <div className="md:col-span-3">
                <Label className="text-xs">Label</Label>
                <Input value={add.label} placeholder="e.g. Mysore · Sep'26"
                  onChange={(e) => setAdd({ ...add, label: e.target.value })} data-testid="gsheet-label" />
              </div>
              <Button className="md:col-span-1" disabled={busy === "add" || !add.sheet_url || (maxSheets && sheets.length >= maxSheets)}
                onClick={addSheet} data-testid="gsheet-add">
                <Plus className="h-4 w-4 mr-1" /> Add
              </Button>
            </div>
          )}

          <div className="border rounded-sm overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Sheet</TableHead><TableHead>Tab</TableHead><TableHead>Status</TableHead>
                <TableHead>Last Sync</TableHead><TableHead>Month</TableHead>
                <TableHead className="text-right">New</TableHead><TableHead className="text-right">Upd</TableHead>
                <TableHead className="text-right">Skip</TableHead><TableHead className="text-right">Fail</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {sheets.length === 0 && (
                  <TableRow><TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-6" data-testid="gsheet-none">
                    No Google Sheet connected yet — paste the link above and click Add.
                  </TableCell></TableRow>
                )}
                {sheets.map((s) => {
                  const c = s.last_sync_counts || {};
                  return (
                    <TableRow key={s.id} data-testid={`gsheet-row-${s.id}`}>
                      <TableCell className="text-sm">
                        {edit?.id === s.id ? (
                          <div className="space-y-1">
                            <Input className="h-7 text-xs" value={edit.label} placeholder="Label" onChange={(e) => setEdit({ ...edit, label: e.target.value })} data-testid={`gsheet-edit-label-${s.id}`} />
                            <Input className="h-7 text-[11px]" value={edit.sheet_url} placeholder="Sheet link" onChange={(e) => setEdit({ ...edit, sheet_url: e.target.value })} data-testid={`gsheet-edit-url-${s.id}`} />
                          </div>
                        ) : (
                          <>
                            <a href={s.sheet_url} target="_blank" rel="noreferrer" className="hover:underline">{s.label}</a>
                            {s.last_error && <div className="text-[10px] text-rose-700">{s.last_error}</div>}
                          </>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-[11px]">
                        {edit?.id === s.id ? (
                          <div className="flex items-center gap-1">
                            <Input className="h-7 w-28 font-mono text-[11px]" value={edit.gid} placeholder="gid" onChange={(e) => setEdit({ ...edit, gid: e.target.value })} data-testid={`gsheet-edit-gid-${s.id}`} />
                            <Button size="sm" className="h-7 text-[10px]" disabled={busy === `e-${s.id}`} onClick={saveEdit} data-testid={`gsheet-edit-save-${s.id}`}>Save</Button>
                            <Button size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => setEdit(null)} data-testid={`gsheet-edit-cancel-${s.id}`}>Cancel</Button>
                          </div>
                        ) : (
                          <span data-testid={`gsheet-gid-${s.id}`}>{s.gid}{s.previous_gid ? <span className="text-muted-foreground"> (was {s.previous_gid})</span> : null}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-[10px] ${s.enabled === false ? "" : TONE.success}`}>
                          {s.enabled === false ? "paused" : "active"}
                        </Badge>
                        {s.last_sync_status && <Badge variant="outline" className={`ml-1 text-[10px] ${TONE[s.last_sync_status] || ""}`}>{s.last_sync_status}</Badge>}
                      </TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{s.last_sync_at ? fmtDT(s.last_sync_at) : "—"}</TableCell>
                      <TableCell className="text-xs">{s.last_sync_month || "—"}</TableCell>
                      <TableCell className="text-right text-xs">{c.imported ?? "—"}</TableCell>
                      <TableCell className="text-right text-xs">{c.updated ?? "—"}</TableCell>
                      <TableCell className="text-right text-xs">{c.skipped_locked ?? "—"}</TableCell>
                      <TableCell className="text-right text-xs">{c.failed ?? "—"}</TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <Button size="icon" variant="ghost" className="h-7 w-7" title="Preview sheet"
                          onClick={() => previewSheet(s)} data-testid={`gsheet-preview-${s.id}`}><Eye className="h-3.5 w-3.5" /></Button>
                        {canWrite && (
                          <>
                            <Button size="icon" variant="ghost" className="h-7 w-7" title="Edit tab (gid) / label / link"
                              onClick={() => setEdit({ id: s.id, gid: s.gid || "", label: s.label || "", sheet_url: s.sheet_url || "" })} data-testid={`gsheet-edit-${s.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7" title="Sync only this sheet"
                              onClick={() => sync(false, [s.id])} data-testid={`gsheet-sync-one-${s.id}`}><RefreshCw className="h-3.5 w-3.5" /></Button>
                            <Button size="sm" variant="ghost" className="h-7 text-[10px]" onClick={() => toggleSheet(s)}
                              data-testid={`gsheet-toggle-${s.id}`}>{s.enabled === false ? "Activate" : "Pause"}</Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600" title="Remove"
                              onClick={() => removeSheet(s)} data-testid={`gsheet-remove-${s.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {/* Global sync settings */}
          <div className="flex flex-wrap items-end gap-4 border-t pt-3">
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!settings.enabled} disabled={!canWrite} className="h-4 w-4"
                onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })} data-testid="gsheet-enabled" />
              Connector active
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!settings.auto_sync} disabled={!canWrite} className="h-4 w-4"
                onChange={(e) => setSettings({ ...settings, auto_sync: e.target.checked })} data-testid="gsheet-auto" />
              Automatic daily sync (all active sheets)
            </label>
            <div>
              <Label className="text-xs">Daily sync at (IST)</Label>
              <div className="flex gap-1">
                <Input type="number" min="0" max="23" className="w-16" value={settings.sync_hour_ist ?? 7} disabled={!canWrite}
                  onChange={(e) => setSettings({ ...settings, sync_hour_ist: e.target.value })} data-testid="gsheet-hour" />
                <Input type="number" min="0" max="59" step="15" className="w-16" value={settings.sync_minute_ist ?? 0} disabled={!canWrite}
                  onChange={(e) => setSettings({ ...settings, sync_minute_ist: e.target.value })} data-testid="gsheet-minute" />
              </div>
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              {canWrite && (
                <>
                  <Button variant="outline" size="sm" onClick={saveSettings} disabled={busy === "settings"} data-testid="gsheet-save">
                    <Save className="h-3.5 w-3.5 mr-1" /> Save Settings
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => sync(true)} disabled={busy === "dry" || !sheets.length} data-testid="gsheet-dry-run">
                    {busy === "dry" ? "Checking…" : "Dry Run All"}
                  </Button>
                  <Button size="sm" onClick={() => sync(false)} disabled={busy === "sync" || !sheets.length} data-testid="gsheet-sync">
                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${busy === "sync" ? "animate-spin" : ""}`} />
                    {busy === "sync" ? "Syncing…" : "Sync All Sheets"}
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
              Preview — {preview.label} · {preview.month} · {preview.date_from} → {preview.date_to} · {preview.date_count} day column(s)
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {preview.employees_in_sheet} employee(s) · <b className="text-emerald-700">{preview.matched} matched</b>
              {preview.employees_in_sheet - preview.matched > 0 && <span className="text-amber-700"> · {preview.employees_in_sheet - preview.matched} unmatched</span>}
            </p>
          </CardHeader>
          <CardContent>
            <div className="border rounded-sm overflow-x-auto max-h-64">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>E-Code</TableHead><TableHead>Name in Sheet</TableHead><TableHead>Match</TableHead>
                  <TableHead className="text-right">Days</TableHead><TableHead className="text-right">Total OT</TableHead><TableHead>First days</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {preview.sample.map((s) => (
                    <TableRow key={s.emp_code} data-testid={`gsheet-prev-${s.emp_code}`}>
                      <TableCell className="font-mono text-xs">{s.emp_code}</TableCell>
                      <TableCell className="text-sm">{s.name}</TableCell>
                      <TableCell><Badge variant="outline" className={`text-[10px] ${s.matched ? TONE.success : TONE.failed}`}>{s.matched ? "matched" : "not in ERP"}</Badge></TableCell>
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
            <CardTitle className="text-sm flex items-center gap-2 flex-wrap">
              <CloudDownload className="h-4 w-4" /> Sync Report
              <Badge variant="outline" className={`text-[10px] ${TONE[shown.status] || ""}`}>{shown.status}</Badge>
              {shown.dry_run && <Badge variant="outline" className="text-[10px]">dry run</Badge>}
              <span className="text-xs font-normal text-muted-foreground">
                {fmtDT(shown.finished_at)} · {shown.trigger} · {shown.by} · {shown.sheets_synced} sheet(s)
                {shown.sheets_failed ? ` · ${shown.sheets_failed} failed` : ""}
              </span>
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {shown.month} · {shown.matched_employees} of {shown.sheet_employees} employee(s) matched
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

            {(shown.sheets || []).length > 0 && (
              <div className="border rounded-sm overflow-x-auto" data-testid="gsheet-per-sheet">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Sheet</TableHead><TableHead>Status</TableHead><TableHead>Month</TableHead>
                    <TableHead className="text-right">Matched</TableHead><TableHead className="text-right">Imported</TableHead>
                    <TableHead className="text-right">Updated</TableHead><TableHead className="text-right">Unchanged</TableHead>
                    <TableHead className="text-right">Skipped</TableHead><TableHead className="text-right">Failed</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {shown.sheets.map((s) => (
                      <TableRow key={s.sheet_row_id} data-testid={`gsheet-res-${s.sheet_row_id}`}>
                        <TableCell className="text-sm">{s.label}</TableCell>
                        <TableCell><Badge variant="outline" className={`text-[10px] ${TONE[s.status] || ""}`}>{s.status}</Badge></TableCell>
                        <TableCell className="text-xs">{s.month || "—"}</TableCell>
                        <TableCell className="text-right text-xs">{s.matched_employees} / {s.sheet_employees}</TableCell>
                        <TableCell className="text-right text-xs">{s.imported}</TableCell>
                        <TableCell className="text-right text-xs">{s.updated}</TableCell>
                        <TableCell className="text-right text-xs">{s.unchanged}</TableCell>
                        <TableCell className="text-right text-xs">{s.skipped_locked}</TableCell>
                        <TableCell className="text-right text-xs">{s.failed}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {(shown.errors || []).length > 0 && (
              <div className="border border-amber-200 bg-amber-50 rounded-sm p-3" data-testid="gsheet-errors">
                <div className="text-xs font-semibold text-amber-900 mb-1 flex items-center gap-1">
                  <TriangleAlert className="h-3 w-3" /> Error report ({shown.errors.length})
                </div>
                <ul className="text-xs text-amber-900 space-y-0.5 max-h-48 overflow-y-auto">
                  {shown.errors.map((e, i) => (
                    <li key={i}>{e.sheet ? `[${e.sheet}] ` : ""}{e.emp_code ? `${e.emp_code} ` : ""}{e.employee_name ? `· ${e.employee_name} ` : ""}{e.date ? `· ${e.date} ` : ""}— {e.error}</li>
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
                  <TableHead className="text-right">Sheets</TableHead><TableHead className="text-right">Imported</TableHead>
                  <TableHead className="text-right">Updated</TableHead><TableHead className="text-right">Skipped</TableHead>
                  <TableHead className="text-right">Failed</TableHead><TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {runs.map((r) => (
                    <TableRow key={r.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setReport(r)} data-testid={`gsheet-run-${r.id}`}>
                      <TableCell className="text-xs whitespace-nowrap">{fmtDT(r.finished_at)}</TableCell>
                      <TableCell className="text-xs">{r.trigger}{r.dry_run ? " (dry)" : ""}</TableCell>
                      <TableCell className="text-xs">{r.by}</TableCell>
                      <TableCell className="text-right text-xs">{r.sheets_synced ?? 1}</TableCell>
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
