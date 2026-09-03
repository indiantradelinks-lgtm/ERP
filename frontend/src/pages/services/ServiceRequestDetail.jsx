import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ArrowLeft, Paperclip, RefreshCw, Lock } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import RowAttachments from "@/components/RowAttachments";
import { StatusChip, inr, dt, useSvcMeta } from "./shared";

const Row = ({ k, v }) => (
  <div className="flex justify-between gap-4 text-sm py-0.5">
    <span className="text-muted-foreground">{k}</span><span className="text-right font-medium">{v || "—"}</span>
  </div>
);

const Card = ({ title, children, testid }) => (
  <div className="border rounded-md bg-white" data-testid={testid}>
    <div className="px-3 py-2 border-b text-sm font-semibold">{title}</div>
    <div className="p-3">{children}</div>
  </div>
);

export default function ServiceRequestDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const meta = useSvcMeta();
  const [d, setD] = useState(null);
  const [docsFor, setDocsFor] = useState(null);
  const [closing, setClosing] = useState(false);
  const [closeRemarks, setCloseRemarks] = useState("");

  const load = useCallback(async () => {
    try { setD((await api.get(`/service-workflow/requests/${id}`)).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  const sr = d.request;
  const caps = meta?.role_caps || {};

  const doClose = async () => {
    try {
      await api.post(`/service-workflow/requests/${id}/close`, { action: "close", remarks: closeRemarks });
      toast.success(`${sr.sr_no} closed`);
      setClosing(false); load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <div className="p-4 space-y-4" data-testid="svc-req-detail-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => nav("/app/services/requests")} data-testid="svc-detail-back"><ArrowLeft className="h-4 w-4" /></Button>
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">{sr.sr_no} <StatusChip status={sr.status} testid="svc-detail-status" /></h1>
            <p className="text-xs text-muted-foreground">Created by {sr.created_by} on {dt(sr.created_at)} · Current owner: {sr.current_owner || "—"}</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={load} data-testid="svc-detail-refresh"><RefreshCw className="h-4 w-4 mr-1" /> Refresh</Button>
          <Button variant="outline" size="sm" onClick={() => setDocsFor(sr)} data-testid="svc-detail-attach"><Paperclip className="h-4 w-4 mr-1" /> Attachments</Button>
          {sr.status === "approved" && caps.procurement &&
            <Button size="sm" onClick={() => nav(`/app/services/rfqs?create_sr=${sr.id}`)} data-testid="svc-detail-create-rfq">Create RFQ</Button>}
          {sr.status === "rfq_created" && caps.procurement &&
            <Button size="sm" variant="secondary" onClick={() => nav("/app/services/rfqs")} data-testid="svc-detail-goto-rfq">Open RFQ</Button>}
          {["paid", "invoice_received", "payment_pending", "srn_created", "service_in_progress"].includes(sr.status) && (caps.procurement || caps.accounts) &&
            <Button size="sm" variant="destructive" onClick={() => setClosing(true)} data-testid="svc-detail-close"><Lock className="h-4 w-4 mr-1" /> Close Request</Button>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card title="Service Request" testid="svc-detail-sr-card">
          <Row k="Request Date" v={dt(sr.request_date)} />
          <Row k="Requester" v={sr.requester_name} />
          <Row k="Department" v={sr.department} />
          <Row k="Project" v={[sr.project_code, sr.project_name].filter(Boolean).join(" · ")} />
          <Row k="Site / Location" v={sr.site_location} />
          <Row k="Category" v={sr.service_category} />
          <Row k="Service Type" v={sr.service_type} />
          <Row k="Required Date" v={dt(sr.required_date)} />
          <Row k="Priority" v={sr.priority} />
          <Row k="Est. Budget" v={inr(sr.estimated_budget)} />
          <Row k="Cost Center" v={sr.cost_center_label} />
          <div className="mt-2 pt-2 border-t text-sm">
            <div className="text-muted-foreground text-xs uppercase">Description</div>
            <p className="whitespace-pre-wrap">{sr.service_description || "—"}</p>
            {sr.scope_of_work && <><div className="text-muted-foreground text-xs uppercase mt-2">Scope of Work</div>
              <p className="whitespace-pre-wrap">{sr.scope_of_work}</p></>}
          </div>
          {sr.approval && (
            <div className="mt-2 pt-2 border-t text-xs">
              <span className="font-semibold uppercase">{sr.approval.action}</span> by {sr.approval.by} ({sr.approval.role}) · {dt(sr.approval.at)}
              {sr.approval.remarks && <p className="text-muted-foreground">“{sr.approval.remarks}”</p>}
            </div>
          )}
        </Card>

        <div className="space-y-3">
          <Card title={`RFQ ${d.rfq ? `— ${d.rfq.rfq_no}` : ""}`} testid="svc-detail-rfq-card">
            {d.rfq ? (
              <>
                <div className="flex items-center justify-between"><StatusChip status={d.rfq.status} /><span className="text-xs text-muted-foreground">{dt(d.rfq.rfq_date)}</span></div>
                <div className="mt-2 space-y-1">
                  {d.rfq.vendors.map((v) => (
                    <div key={v.vendor_id} className="flex justify-between text-sm border rounded px-2 py-1">
                      <span>{v.vendor_name}</span>
                      <span className="tabular-nums">{v.quotation ? inr(v.quotation.total) : <span className="text-xs text-muted-foreground">no quote</span>}</span>
                    </div>
                  ))}
                </div>
                {d.rfq.recommended_vendor_id && <p className="text-xs mt-2">Recommended: <b>{(d.rfq.vendors.find((v) => v.vendor_id === d.rfq.recommended_vendor_id) || {}).vendor_name}</b></p>}
              </>
            ) : <p className="text-sm text-muted-foreground">Not created yet {sr.status === "approved" ? "— request is approved and eligible for RFQ" : ""}</p>}
          </Card>

          <Card title="Purchase Orders" testid="svc-detail-po-card">
            {d.pos.length ? d.pos.map((po) => (
              <div key={po.id} className="border rounded px-2 py-1.5 mb-1 text-sm">
                <div className="flex justify-between"><span className="font-medium text-primary">{po.po_no}</span><StatusChip status={po.status} /></div>
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{po.vendor_name}</span><span>{inr(po.total_value)} · recd {po.accepted_pct_total || 0}% · <StatusChip status={po.payment_status} /></span>
                </div>
              </div>
            )) : <p className="text-sm text-muted-foreground">No PO yet</p>}
          </Card>

          <Card title="Service Receipt Notes (SRN)" testid="svc-detail-srn-card">
            {d.srns.length ? d.srns.map((s) => (
              <div key={s.id} className="border rounded px-2 py-1.5 mb-1 text-sm flex justify-between">
                <span>{s.srn_no} · {dt(s.receipt_date)} · {s.accepted_pct}% accepted</span><StatusChip status={s.status} />
              </div>
            )) : <p className="text-sm text-muted-foreground">No SRN yet</p>}
          </Card>

          <Card title="Vendor Invoices & Payments" testid="svc-detail-inv-card">
            {d.invoices.length ? d.invoices.map((i) => (
              <div key={i.id} className="border rounded px-2 py-1.5 mb-1 text-sm">
                <div className="flex justify-between"><span>{i.inv_no} · {i.vendor_invoice_no}</span><StatusChip status={i.status} /></div>
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Net {inr(i.net_payable)}</span>
                  <span>{i.payment_stage ? `Queue: ${(i.payment_stage.stage || "").replace(/_/g, " ")}${i.payment_stage.utr_no ? ` · UTR ${i.payment_stage.utr_no}` : ""}` : ""}</span>
                </div>
              </div>
            )) : <p className="text-sm text-muted-foreground">No invoice yet</p>}
          </Card>
        </div>

        <Card title="Complete Timeline & Audit Trail" testid="svc-detail-timeline">
          <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
            {d.timeline.map((t, i) => (
              <div key={`${t.at}-${i}`} className="border-l-2 border-primary/30 pl-3 relative">
                <span className="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-primary/60" />
                <div className="text-xs text-muted-foreground">{String(t.at).replace("T", " ").slice(0, 16)} · {t.doc} {t.ref}</div>
                <div className="text-sm font-medium">{String(t.action || "").replace(/_/g, " ")}{t.to ? ` → ${t.to.replace(/_/g, " ")}` : ""}</div>
                <div className="text-xs">{t.by} ({t.role}){t.remarks ? ` — “${t.remarks}”` : ""}</div>
              </div>
            ))}
            {!d.timeline.length && <p className="text-sm text-muted-foreground">No events</p>}
          </div>
        </Card>
      </div>

      <Dialog open={closing} onOpenChange={setClosing}>
        <DialogContent className="max-w-md rounded-sm" data-testid="svc-detail-close-dialog">
          <DialogHeader><DialogTitle>Close {sr.sr_no}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Closing marks the full service cycle complete. Unpaid invoices block closure (Super Admin can force).</p>
          <div><Label className="text-xs">Closing remarks</Label><Textarea rows={2} value={closeRemarks} onChange={(e) => setCloseRemarks(e.target.value)} data-testid="svc-detail-close-remarks" /></div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClosing(false)}>Cancel</Button>
            <Button variant="destructive" onClick={doClose} data-testid="svc-detail-close-confirm">Close Request</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RowAttachments open={!!docsFor} onOpenChange={(o) => !o && setDocsFor(null)}
        parentType="service_requests" parentId={docsFor?.id} recordTitle={docsFor?.sr_no} testidPrefix="svc-detail-attach" />
    </div>
  );
}
