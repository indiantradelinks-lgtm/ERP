import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { toneFor } from "@/lib/statusTone";
import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { fmtDT } from "@/lib/datetime";
import { lookupGet } from "@/lib/lookups";
import { RefreshCw, Eye } from "lucide-react";
import RecruitmentDetailDialog from "./RecruitmentDetailDialog";

const RECRUIT_STATUS_TONE = {
  filled: "success", closed: "neutral", approved: "success", completed: "success",
  rejected: "danger", shortlisting: "info", interview: "info", offer: "info",
};
const HR_STATUSES = ["open", "approved", "rejected", "shortlisting", "interview", "offer", "filled", "completed", "closed"];

export default function RecruitmentRequests() {
  const r = useResource("recruitment-requests");
  const [projMap, setProjMap] = useState({});
  const [acting, setActing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [act, setAct] = useState({ status: "", pm_info_received: null, hired: "", remarks: "" });
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const syncApproved = async () => {
    setSyncing(true);
    try {
      const { data } = await api.post("/project-requests/sync-recruitment");
      toast.success(data.count
        ? `${data.count} requisition(s) pulled in from ${data.requests_synced} approved manpower request(s)`
        : "All approved manpower requests are already in this list");
      r.reload();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setSyncing(false); }
  };
  useEffect(() => {
    lookupGet("/projects").then((res) => {
      const m = {};
      (res.data || []).forEach((p) => {
        const info = { code: p.code || p.project_code, name: p.name, manager: p.project_manager_name || p.manager || p.manager_name || p.project_manager };
        if (info.code) m[info.code] = info;
        if (p.id) m[p.id] = info;
      });
      setProjMap(m);
    }).catch(() => {});
  }, []);
  const projInfo = (row) => projMap[row.project_code] || projMap[row.project_id] || projMap[row.project] || null;

  const openAction = (row) => {
    setAct({ status: row.status || "open", pm_info_received: row.pm_info_received ?? null,
             hired: row.hired ?? "", remarks: "" });
    setActing(row);
  };

  const submitAction = async () => {
    setBusy(true);
    try {
      await api.post(`/recruitment-requests/${acting.id}/hr-action`, {
        status: act.status,
        pm_info_received: act.pm_info_received,
        hired: act.hired === "" ? null : Number(act.hired),
        remarks: act.remarks,
      });
      toast.success(`${acting.position} — status updated to ${act.status}`);
      setActing(null);
      r.reload();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const columns = [
    { key: "req_no", label: "Req #", render: (row) => <span className="font-mono text-xs" data-testid={`recruit-no-${row.id}`}>{row.req_no || "—"}</span> },
    { key: "position", label: "Position" },
    {
      key: "project", label: "Project",
      render: (row) => {
        const p = projInfo(row);
        const code = p?.code || row.project_code || row.project;
        if (!code) return "—";
        return (
          <div data-testid={`recruit-project-${row.id}`}>
            <div className="font-medium">{code}</div>
            {p?.name && <div className="text-[11px] text-muted-foreground max-w-[180px] truncate" title={p.name}>{p.name}</div>}
          </div>
        );
      },
    },
    { key: "site", label: "Site", render: (row) => <span data-testid={`recruit-site-${row.id}`}>{row.site || row.site_location || "—"}</span> },
    {
      key: "project_manager", label: "Project Manager",
      render: (row) => {
        const p = projInfo(row);
        return <span data-testid={`recruit-pm-${row.id}`}>{row.project_manager || p?.manager || "—"}</span>;
      },
    },
    { key: "source", label: "Source", badge: (row) => row.source === "project_request"
        ? { text: "Project Request", tone: "info" }
        : { text: "Manual", tone: "neutral" } },
    { key: "source_request_no", label: "Source Request", render: (row) => (
      <div data-testid={`recruit-src-${row.id}`}>
        <div className="font-mono text-[11px]">{row.source_request_no || "—"}</div>
        {row.requested_by && <div className="text-[10px] text-muted-foreground">by {row.requested_by}</div>}
      </div>
    ) },
    { key: "vacancies", label: "Vacancies" },
    { key: "hired", label: "Hired", badge: (row) => ({ text: `${row.hired || 0} / ${row.vacancies || 0}`, tone: (row.hired || 0) >= (row.vacancies || 0) && row.vacancies ? "success" : "warning" }) },
    { key: "needed_by", label: "Needed By" },
    {
      key: "pm_info_received", label: "PM Info",
      render: (row) => row.pm_info_received == null
        ? <span className="text-muted-foreground text-xs">—</span>
        : <Badge variant="outline" className={`text-[10px] ${row.pm_info_received ? "bg-emerald-50 text-emerald-700 border-emerald-300" : "bg-amber-50 text-amber-700 border-amber-300"}`} data-testid={`recruit-pminfo-${row.id}`}>{row.pm_info_received ? "Received" : "Pending"}</Badge>,
    },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status || "open", tone: toneFor(RECRUIT_STATUS_TONE, row.status, "warning") }) },
    {
      key: "hr_action", label: "HR Action",
      render: (row) => (
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" className="h-7 text-xs rounded-sm" onClick={(e) => { e.stopPropagation(); setViewing(row); }} data-testid={`recruit-view-${row.id}`}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
          {r.canWrite && (
            <Button size="sm" variant="outline" className="h-7 text-xs rounded-sm" onClick={(e) => { e.stopPropagation(); openAction(row); }} data-testid={`recruit-hr-action-${row.id}`}>Update</Button>
          )}
        </div>
      ),
    },
  ];
  const fields = [
    { key: "position", label: "Position Title" },
    { key: "department", label: "Department" },
    { key: "project_code", label: "Project Code" },
    { key: "site", label: "Site / Location" },
    { key: "vacancies", label: "Vacancies", type: "number" },
    { key: "hired", label: "Hired So Far", type: "number" },
    { key: "skill_set", label: "Required Skills", full: true },
    { key: "experience_yrs", label: "Min. Experience (yrs)", type: "number" },
    { key: "needed_by", label: "Needed By", type: "date" },
    { key: "raised_by", label: "Raised By" },
    { key: "justification", label: "Business Justification", type: "textarea", full: true },
    { key: "status", label: "Status", type: "select", options: HR_STATUSES },
  ];
  return (
    <>
      <DataTableShell title="Recruitment Requests" description="Every approved Manpower / Site Staff request lands here automatically — HR updates outcomes; every change is history-tracked and visible to the requester." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="recruit" exportResource="recruitment-requests" canWrite={r.canWrite} pagination={r.pagination} canDelete={r.canDelete} attachmentsParentType="documents"
        rightSlot={r.canWrite ? (
          <Button variant="outline" size="sm" className="h-8 rounded-sm text-xs" disabled={syncing} onClick={syncApproved} data-testid="recruit-sync-approved">
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Syncing…" : "Sync Approved Requests"}
          </Button>
        ) : null} />

      <RecruitmentDetailDialog row={viewing} open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}
        onUpdate={r.canWrite ? openAction : null} />

      <Dialog open={!!acting} onOpenChange={(o) => !o && setActing(null)}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto rounded-sm" data-testid="recruit-action-dialog">
          <DialogHeader><DialogTitle>HR Update — {acting?.position} ({acting?.req_no || acting?.project_code || ""})</DialogTitle></DialogHeader>
          {acting && (
            <div className="space-y-3">
              <div className="text-xs border rounded-sm p-2 bg-muted/30">
                Project: <b>{acting.project_code || "—"}</b> · Site: <b>{acting.site || "—"}</b> · Vacancies: <b>{acting.vacancies}</b> · Hired: <b>{acting.hired || 0}</b>
              </div>
              <div>
                <Label className="text-xs">Status *</Label>
                <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" value={act.status} onChange={(e) => setAct({ ...act, status: e.target.value })} data-testid="recruit-action-status">
                  {HR_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">PM / Manager OP information received?</Label>
                <div className="flex gap-4 mt-1">
                  {[["yes", true], ["no", false]].map(([lbl, v]) => (
                    <label key={lbl} className="flex items-center gap-1.5 text-sm cursor-pointer">
                      <input type="radio" name="pm_info" checked={act.pm_info_received === v} onChange={() => setAct({ ...act, pm_info_received: v })} data-testid={`recruit-action-pminfo-${lbl}`} /> {lbl.toUpperCase()}
                    </label>
                  ))}
                </div>
              </div>
              <div><Label className="text-xs">Hired count</Label><Input type="number" min="0" value={act.hired} onChange={(e) => setAct({ ...act, hired: e.target.value })} data-testid="recruit-action-hired" /></div>
              <div><Label className="text-xs">Recruitment outcome / remarks {act.status === "rejected" ? "*" : ""}</Label>
                <Textarea rows={2} value={act.remarks} onChange={(e) => setAct({ ...act, remarks: e.target.value })} data-testid="recruit-action-remarks" /></div>
              {(acting.history || []).length > 0 && (
                <div className="border rounded-sm p-2 max-h-40 overflow-y-auto" data-testid="recruit-action-history">
                  <div className="text-[10px] uppercase text-muted-foreground mb-1">Status History</div>
                  {[...acting.history].reverse().map((h, i) => (
                    <div key={i} className="text-xs border-l-2 border-primary/30 pl-2 mb-1">
                      <div>{fmtDT(h.at)} · <b>{h.from || "—"} → {h.to}</b> · {h.by}</div>
                      {(h.remarks || h.pm_info_received != null) && (
                        <div className="text-muted-foreground">
                          {h.pm_info_received != null ? `PM info: ${h.pm_info_received ? "received" : "pending"} · ` : ""}{h.remarks}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setActing(null)}>Cancel</Button>
            <Button disabled={busy} onClick={submitAction} data-testid="recruit-action-save">Save Update</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
