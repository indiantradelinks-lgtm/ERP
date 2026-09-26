/**
 * HR view of everything the project user entered while raising a manpower request.
 * Opened from Recruitment Requests → View.
 */
import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fmtDT } from "@/lib/datetime";
import { toast } from "sonner";

const inr = (v) => (v || v === 0 ? `₹ ${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—");

const Field = ({ label, value, testid }) => (
  <div className="border border-border rounded-sm px-2 py-1.5" data-testid={testid}>
    <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className="text-xs font-medium break-words">{value || value === 0 ? value : "—"}</div>
  </div>
);

const Section = ({ title, children }) => (
  <div className="space-y-1.5">
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">{title}</div>
    {children}
  </div>
);

export default function RecruitmentDetailDialog({ row, open, onOpenChange, onUpdate }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !row) return;
    setLoading(true); setD(null);
    api.get(`/recruitment-requests/${row.id}/source`)
      .then((r) => setD(r.data))
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [open, row]);

  const rec = d?.recruitment || row || {};
  const src = d?.source_request;
  const line = d?.source_line;
  const proj = d?.project;
  const avail = (src?.availability_lines || []).find((a) => (a.name || "").toLowerCase() === (line?.name || "").toLowerCase());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[92vh] overflow-y-auto" data-testid="recruit-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            {rec.position} <span className="font-mono text-xs text-muted-foreground">{rec.req_no}</span>
            <Badge variant="outline" className="text-[10px]">{String(rec.status || "open").replace(/_/g, " ")}</Badge>
            {rec.pool_covered && <Badge variant="outline" className="text-[10px] bg-emerald-50 text-emerald-800 border-emerald-300">internal pool available</Badge>}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {src ? `Raised by ${src.created_by || "—"} via ${src.request_no} · ${fmtDT(src.created_at)}` : "Manually created requisition"}
          </p>
        </DialogHeader>

        {loading && <div className="text-sm text-muted-foreground py-6 text-center" data-testid="recruit-detail-loading">Loading request details…</div>}

        {!loading && (
          <div className="space-y-4">
            <Section title="Requisition">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <Field label="Vacancies" value={rec.vacancies} testid="rd-vacancies" />
                <Field label="Hired" value={`${rec.hired || 0} of ${rec.vacancies || 0}`} testid="rd-hired" />
                <Field label="Needed By" value={rec.needed_by} testid="rd-needed-by" />
                <Field label="Department" value={rec.department} />
                <Field label="Budget / head / month" value={inr(rec.budget_monthly_per_head)} testid="rd-budget" />
                <Field label="Deployment From" value={rec.deployment_from} />
                <Field label="Deployment To" value={rec.deployment_to} />
                <Field label="PM Info Received" value={rec.pm_info_received == null ? "—" : (rec.pm_info_received ? "Yes" : "Pending")} />
                <div className="col-span-2 md:col-span-4"><Field label="Required Skills / Specs" value={rec.skills || rec.skill_set} testid="rd-skills" /></div>
                <div className="col-span-2 md:col-span-4"><Field label="Remarks" value={rec.remarks} /></div>
              </div>
            </Section>

            <Section title="Project & Site (as entered by the project user)">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <Field label="Project Code" value={rec.project_code || src?.project_code} testid="rd-project" />
                <Field label="Project Name" value={proj?.name || rec.project_name || src?.project_name} />
                <Field label="Client" value={proj?.client_name} />
                <Field label="Site / Location" value={rec.site || src?.site_location || proj?.site_location} testid="rd-site" />
                <Field label="Project Manager" value={rec.project_manager || proj?.project_manager_name || proj?.manager} />
                <Field label="Requested By" value={src?.created_by || rec.requested_by} testid="rd-requested-by" />
                <Field label="Raised On" value={src?.created_at ? fmtDT(src.created_at) : "—"} />
                <Field label="Approved On" value={src?.approved_at ? fmtDT(src.approved_at) : "—"} testid="rd-approved-on" />
              </div>
            </Section>

            {src && (
              <Section title="Manpower Request Details">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <Field label="Request No" value={src.request_no} />
                  <Field label="Request Status" value={String(src.status || "").replace(/_/g, " ")} />
                  <Field label="Deployment Period" value={`${src.period_from || "—"} → ${src.period_to || "—"}`} />
                  <Field label="Months" value={src.months} />
                  <Field label="Estimated Budget" value={inr(src.est_value)} />
                  <Field label="Owning Dept" value={src.owning_dept} />
                  <Field label="Cost Center" value={src.cost_center_label || src.cost_center_name} />
                  <Field label="Priority" value={src.priority} />
                  <div className="col-span-2 md:col-span-4"><Field label="Description / Justification" value={src.description} testid="rd-description" /></div>
                </div>
              </Section>
            )}

            {line && (
              <Section title="This Position — as requested">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <Field label="Position" value={line.name} />
                  <Field label="Qty Requested" value={`${line.quantity || 0} ${line.unit || ""}`} />
                  <Field label="Budget Rate" value={inr(line.rate)} />
                  <Field label="Designation" value={line.designation || line.category} />
                  <div className="col-span-2 md:col-span-4"><Field label="Specs / Experience" value={line.specs || line.tech_details} testid="rd-line-specs" /></div>
                  {avail && (
                    <div className="col-span-2 md:col-span-4">
                      <Field label="Internal Pool Check"
                        value={avail.in_pool
                          ? `Pool covers this line — ${avail.available_workers || 0} worker(s) + ${avail.matching_employees || 0} employee(s) available`
                          : `Short by ${avail.shortfall} (${avail.available || 0} available in pool)`}
                        testid="rd-pool" />
                    </div>
                  )}
                </div>
              </Section>
            )}

            {(src?.items || []).length > 1 && (
              <Section title={`All Positions in ${src.request_no}`}>
                <div className="border border-border rounded-sm overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead><tr className="bg-muted/40 text-left">
                      <th className="p-1.5">Position</th><th className="p-1.5">Qty</th>
                      <th className="p-1.5">Budget</th><th className="p-1.5">Requisition</th><th className="p-1.5">Hired</th>
                    </tr></thead>
                    <tbody>
                      {src.items.map((it, i) => (
                        <tr key={i} className={`border-t border-border/50 ${it.recruitment_no === rec.req_no ? "bg-secondary/60" : ""}`} data-testid={`rd-item-${i}`}>
                          <td className="p-1.5">{it.name}{it.specs && <div className="text-[10px] text-muted-foreground">{it.specs}</div>}</td>
                          <td className="p-1.5">{it.quantity} {it.unit}</td>
                          <td className="p-1.5">{inr(it.rate)}</td>
                          <td className="p-1.5 font-mono text-[11px]">{it.recruitment_no || "—"}</td>
                          <td className="p-1.5">{it.hired_count || 0} / {it.vacancy_count || it.quantity || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {(src?.chain || []).length > 0 && (
              <Section title="Approval Trail">
                <div className="flex flex-wrap gap-1.5" data-testid="rd-approval-chain">
                  {src.chain.map((s, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded-sm border ${s.status === "approved" ? "bg-emerald-50 border-emerald-300 text-emerald-800" : s.status === "rejected" ? "bg-rose-50 border-rose-300 text-rose-800" : "bg-secondary border-border text-muted-foreground"}`}>
                      {s.label}{s.by ? ` · ${s.by}` : ""}{s.at ? ` · ${fmtDT(s.at)}` : ""}
                    </span>
                  ))}
                </div>
              </Section>
            )}

            {(d?.attachments || []).length > 0 && (
              <Section title="Attachments from the requester">
                <ul className="text-xs space-y-0.5" data-testid="rd-attachments">
                  {d.attachments.map((f) => (
                    <li key={f.id}>{f.filename} <span className="text-muted-foreground">· {f.uploaded_by || ""} {f.uploaded_at ? fmtDT(f.uploaded_at) : ""}</span></li>
                  ))}
                </ul>
              </Section>
            )}

            {(rec.history || []).length > 0 && (
              <Section title="HR Status History">
                <div className="border border-border rounded-sm p-2 max-h-40 overflow-y-auto" data-testid="rd-history">
                  {[...rec.history].reverse().map((h, i) => (
                    <div key={i} className="text-xs border-l-2 border-primary/30 pl-2 mb-1">
                      <div>{fmtDT(h.at)} · <b>{h.from || "—"} → {h.to}</b> · {h.by}</div>
                      {h.remarks && <div className="text-muted-foreground">{h.remarks}</div>}
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="recruit-detail-close">Close</Button>
          {onUpdate && <Button onClick={() => { onOpenChange(false); onUpdate(rec); }} data-testid="recruit-detail-update">HR Update</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
