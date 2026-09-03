import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Paperclip, RefreshCw, Pencil, History, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ProjectSelect, SiteLocationSelect } from "@/components/MasterSelect";
import RowAttachments from "@/components/RowAttachments";

const FORM_TYPES = ["Labour License", "Form V", "Form VI", "Form XVII"];
const STATUS_STYLE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-300",
  renewed: "bg-blue-50 text-blue-700 border-blue-300",
  expiring_soon: "bg-amber-50 text-amber-700 border-amber-300",
  expired: "bg-red-50 text-red-700 border-red-300",
};
const blank = () => ({ project_code: "", project_name: "", site_location: "", license_number: "", license_type: "Labour License", form_type: "Labour License", issue_date: "", valid_from: "", expiry_date: "", remarks: "" });

const StatusBadge = ({ r }) => (
  <Badge variant="outline" className={`${STATUS_STYLE[r.status] || ""} text-[10px] uppercase`} data-testid={`ll-status-${r.id}`}>
    {r.status.replace("_", " ")}{r.days_remaining != null && r.status !== "expired" ? ` · ${r.days_remaining}d` : ""}
  </Badge>
);

export default function LabourLicenses() {
  const { user } = useAuth();
  const isHr = ["super_admin", "hr_executive", "hr_manager", "general_manager", "director"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [dash, setDash] = useState(null);
  const [statusF, setStatusF] = useState("");
  const [editing, setEditing] = useState(null);
  const [renewing, setRenewing] = useState(null);
  const [docsFor, setDocsFor] = useState(null);
  const [historyFor, setHistoryFor] = useState(null);

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([
        api.get(`/labour-licenses?status=${statusF}`),
        api.get("/labour-licenses/dashboard"),
      ]);
      setRows(a.data);
      setDash(b.data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  }, [statusF]);
  useEffect(() => { load(); }, [load]);

  const cards = dash?.cards || {};
  const tiles = [
    ["Total Licenses", cards.total, ""],
    ["Active", cards.active, "text-emerald-700"],
    ["Expiring ≤ 7 Days", cards.expiring_soon, "text-amber-700"],
    ["Expired", cards.expired, "text-red-700"],
    ["Renewed", cards.renewed, "text-blue-700"],
  ];

  return (
    <div className="p-4 space-y-4" data-testid="labour-licenses-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><ShieldCheck className="h-5 w-5" /> Labour License Compliance</h1>
          <p className="text-xs text-muted-foreground">Project-wise labour license & form tracking with automatic expiry alerts (7-day HR notification)</p>
        </div>
        {isHr && <Button onClick={() => setEditing(blank())} data-testid="ll-new-btn"><Plus className="h-4 w-4 mr-1" /> New License</Button>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {tiles.map(([l, v, cls]) => (
          <div key={l} className="border rounded-md bg-white p-3" data-testid={`ll-tile-${l.split(" ")[0].toLowerCase()}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{l}</div>
            <div className={`text-2xl font-bold tabular-nums ${cls}`}>{v ?? 0}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Label className="text-xs">Status</Label>
        <select value={statusF} onChange={(e) => setStatusF(e.target.value)} className="h-8 rounded-sm border border-input bg-background px-2 text-sm" data-testid="ll-status-filter">
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="expiring_soon">Expiring Soon</option>
          <option value="expired">Expired</option>
          <option value="renewed">Renewed</option>
        </select>
        {isHr && (
          <Button size="sm" variant="outline" className="h-8 ml-auto" data-testid="ll-run-check"
            onClick={async () => {
              try { const { data } = await api.post("/labour-licenses/admin/run-daily-check"); toast.success(`Checked ${data.checked} · alerts sent ${data.alerted}`); load(); }
              catch (e) { toast.error(apiErrorMessage(e)); }
            }}>Run Expiry Check Now</Button>
        )}
      </div>

      <div className="border rounded-lg overflow-x-auto bg-white">
        <Table className="min-w-[1100px]">
          <TableHeader><TableRow>
            <TableHead>Project / Site</TableHead><TableHead>License No</TableHead><TableHead>Form / Type</TableHead>
            <TableHead>Issue</TableHead><TableHead>Valid From</TableHead><TableHead>Expiry</TableHead>
            <TableHead>Days Left</TableHead><TableHead>Status</TableHead><TableHead>Renewals</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-8">No labour licenses{statusF ? " for this status" : ""} — {isHr ? "click New License to add one" : "none assigned to your projects"}</TableCell></TableRow>}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`ll-row-${r.license_number}`}>
                <TableCell className="text-xs"><b>{r.project_code}</b> {r.project_name && <span className="text-muted-foreground">· {r.project_name}</span>}<div className="text-[10px] text-muted-foreground">{r.site_location}</div></TableCell>
                <TableCell className="text-xs font-mono">{r.license_number}</TableCell>
                <TableCell className="text-xs">{r.form_type}{r.license_type && r.license_type !== r.form_type ? ` · ${r.license_type}` : ""}</TableCell>
                <TableCell className="text-xs">{r.issue_date || "—"}</TableCell>
                <TableCell className="text-xs">{r.valid_from || "—"}</TableCell>
                <TableCell className="text-xs font-semibold">{r.expiry_date}</TableCell>
                <TableCell className={`text-xs tabular-nums font-semibold ${r.days_remaining != null && r.days_remaining < 0 ? "text-red-600" : r.days_remaining <= 7 ? "text-amber-700" : ""}`}>{r.days_remaining ?? "—"}</TableCell>
                <TableCell><StatusBadge r={r} /></TableCell>
                <TableCell className="text-xs text-center">{r.renewal_count > 0 ? (
                  <button className="underline text-blue-700" onClick={() => setHistoryFor(r)} data-testid={`ll-history-${r.id}`}><History className="h-3 w-3 inline mr-0.5" />{r.renewal_count}</button>
                ) : "—"}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button size="sm" variant="outline" className="h-7 mr-1" onClick={() => setDocsFor(r)} data-testid={`ll-docs-${r.id}`}><Paperclip className="h-3 w-3 mr-1" />Docs</Button>
                  {isHr && <Button size="sm" variant="outline" className="h-7 mr-1" onClick={() => setEditing(r)} data-testid={`ll-edit-${r.id}`}><Pencil className="h-3 w-3" /></Button>}
                  {isHr && <Button size="sm" className="h-7" onClick={() => setRenewing({ id: r.id, license_number: r.license_number, valid_from: "", expiry_date: "", remarks: "" })} data-testid={`ll-renew-${r.id}`}><RefreshCw className="h-3 w-3 mr-1" />Renew</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {dash?.by_project?.length > 0 && (
        <div className="border rounded-lg bg-white p-3">
          <h3 className="text-sm font-semibold mb-2">Project-wise License Status</h3>
          <div className="grid md:grid-cols-3 gap-2">
            {dash.by_project.map((p) => (
              <div key={p.project_code} className="border rounded p-2 text-xs" data-testid={`ll-proj-${p.project_code}`}>
                <b>{p.project_code}</b> {p.project_name && <span className="text-muted-foreground">· {p.project_name}</span>}
                <div className="mt-1 flex gap-2 flex-wrap">
                  <span className="text-emerald-700">Active {p.active + (p.renewed || 0)}</span>
                  <span className="text-amber-700">Expiring {p.expiring_soon || 0}</span>
                  <span className="text-red-600">Expired {p.expired || 0}</span>
                  <span className="text-slate-500">Total {p.total}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {editing && <LicenseDialog initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {renewing && <RenewDialog r={renewing} setR={setRenewing} onSaved={() => { setRenewing(null); load(); }} />}
      {docsFor && (
        <RowAttachments open onOpenChange={(v) => !v && setDocsFor(null)}
          parentType="labour_license" parentId={docsFor.id}
          recordTitle={`Documents — ${docsFor.license_number} (${docsFor.form_type})`} testidPrefix="ll-attach" />
      )}
      {historyFor && (
        <Dialog open onOpenChange={() => setHistoryFor(null)}>
          <DialogContent className="max-w-lg" data-testid="ll-history-dialog">
            <DialogHeader><DialogTitle>Renewal History — {historyFor.license_number}</DialogTitle></DialogHeader>
            <div className="space-y-2 max-h-[50vh] overflow-y-auto">
              {(historyFor.renewal_history || []).slice().reverse().map((h, i) => (
                <div key={i} className="border rounded p-2 text-xs bg-slate-50">
                  <div><b>{h.license_number}</b> · {h.valid_from || "—"} → {h.expiry_date}</div>
                  <div className="text-muted-foreground">Renewed by {h.renewed_by} on {new Date(h.renewed_at).toLocaleString("en-IN")}</div>
                  {h.renewal_remarks && <div>{h.renewal_remarks}</div>}
                </div>
              ))}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function LicenseDialog({ initial, onClose, onSaved }) {
  const [f, setF] = useState(initial);
  const isEdit = !!initial.id;
  const save = async () => {
    if (!f.project_code || !f.license_number || !f.expiry_date || !f.form_type) { toast.error("Project, License Number, Form Type and Expiry Date are required"); return; }
    try {
      const payload = { project_code: f.project_code, project_name: f.project_name, site_location: f.site_location, license_number: f.license_number, license_type: f.license_type, form_type: f.form_type, issue_date: f.issue_date, valid_from: f.valid_from, expiry_date: f.expiry_date, remarks: f.remarks };
      if (isEdit) await api.put(`/labour-licenses/${f.id}`, payload);
      else await api.post("/labour-licenses", payload);
      toast.success(isEdit ? "License updated" : "License created — upload the document via Docs");
      onSaved();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl" data-testid="ll-form-dialog">
        <DialogHeader><DialogTitle>{isEdit ? `Edit — ${initial.license_number}` : "New Labour License"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <ProjectSelect label="Project / Site *" value={f.project_code} onChange={(code, row) => setF({ ...f, project_code: code, project_name: row?.name || "" })} testid="ll-form-project" />
          <SiteLocationSelect label="Site Location" value={f.site_location} onChange={(v) => setF({ ...f, site_location: v })} testid="ll-form-site" />
          <div><Label className="text-xs">Labour License Number *</Label><Input value={f.license_number} onChange={(e) => setF({ ...f, license_number: e.target.value })} data-testid="ll-form-number" /></div>
          <div>
            <Label className="text-xs">Form Type *</Label>
            <select value={f.form_type} onChange={(e) => setF({ ...f, form_type: e.target.value })} className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="ll-form-type">
              {FORM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div><Label className="text-xs">License Type</Label><Input value={f.license_type} onChange={(e) => setF({ ...f, license_type: e.target.value })} data-testid="ll-form-ltype" /></div>
          <div><Label className="text-xs">Issue Date</Label><Input type="date" value={f.issue_date} onChange={(e) => setF({ ...f, issue_date: e.target.value })} data-testid="ll-form-issue" /></div>
          <div><Label className="text-xs">Valid From</Label><Input type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} data-testid="ll-form-validfrom" /></div>
          <div><Label className="text-xs">Expiry Date *</Label><Input type="date" value={f.expiry_date} onChange={(e) => setF({ ...f, expiry_date: e.target.value })} data-testid="ll-form-expiry" /></div>
          <div className="col-span-2"><Label className="text-xs">Remarks / Notes</Label><Textarea rows={2} value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} data-testid="ll-form-remarks" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} data-testid="ll-form-save">{isEdit ? "Save Changes" : "Create License"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RenewDialog({ r, setR, onSaved }) {
  const save = async () => {
    if (!r.valid_from || !r.expiry_date) { toast.error("New Valid From and Expiry Date are required"); return; }
    try {
      await api.post(`/labour-licenses/${r.id}/renew`, { valid_from: r.valid_from, expiry_date: r.expiry_date, license_number: r.license_number, remarks: r.remarks });
      toast.success("License renewed — status reset to Active, next 7-day alert scheduled. Upload the renewed document via Docs.");
      onSaved();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={() => setR(null)}>
      <DialogContent className="max-w-md" data-testid="ll-renew-dialog">
        <DialogHeader><DialogTitle>Renew License</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label className="text-xs">License Number (new, if changed)</Label><Input value={r.license_number} onChange={(e) => setR({ ...r, license_number: e.target.value })} data-testid="ll-renew-number" /></div>
          <div><Label className="text-xs">New Valid From *</Label><Input type="date" value={r.valid_from} onChange={(e) => setR({ ...r, valid_from: e.target.value })} data-testid="ll-renew-validfrom" /></div>
          <div><Label className="text-xs">New Expiry Date *</Label><Input type="date" value={r.expiry_date} onChange={(e) => setR({ ...r, expiry_date: e.target.value })} data-testid="ll-renew-expiry" /></div>
          <div><Label className="text-xs">Renewal Remarks</Label><Textarea rows={2} value={r.remarks} onChange={(e) => setR({ ...r, remarks: e.target.value })} data-testid="ll-renew-remarks" /></div>
          <p className="text-[11px] text-muted-foreground">Previous validity is kept in the renewal history. Upload the renewed document from the Docs button after saving.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setR(null)}>Cancel</Button>
          <Button onClick={save} data-testid="ll-renew-save">Renew &amp; Reset to Active</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
