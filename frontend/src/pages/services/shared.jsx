import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

export const inr = (n) => (n == null || isNaN(Number(n)) ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 }));
export const dt = (s) => (s ? String(s).slice(0, 10) : "—");

export const STATUS_STYLE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  submitted: "bg-blue-50 text-blue-700 border-blue-300",
  under_review: "bg-blue-50 text-blue-700 border-blue-300",
  pending_approval: "bg-blue-50 text-blue-700 border-blue-300",
  approved: "bg-emerald-50 text-emerald-700 border-emerald-300",
  selection_approved: "bg-emerald-50 text-emerald-700 border-emerald-300",
  rejected: "bg-red-50 text-red-700 border-red-300",
  sent_back: "bg-amber-50 text-amber-700 border-amber-300",
  exception_review: "bg-red-50 text-red-700 border-red-300",
  rfq_created: "bg-indigo-50 text-indigo-700 border-indigo-300",
  issued: "bg-indigo-50 text-indigo-700 border-indigo-300",
  quotations_received: "bg-violet-50 text-violet-700 border-violet-300",
  recommended: "bg-violet-50 text-violet-700 border-violet-300",
  po_created: "bg-indigo-50 text-indigo-700 border-indigo-300",
  service_in_progress: "bg-cyan-50 text-cyan-700 border-cyan-300",
  in_progress: "bg-cyan-50 text-cyan-700 border-cyan-300",
  srn_created: "bg-teal-50 text-teal-700 border-teal-300",
  completed: "bg-teal-50 text-teal-700 border-teal-300",
  invoice_received: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-300",
  payment_pending: "bg-orange-50 text-orange-700 border-orange-300",
  partially_paid: "bg-orange-50 text-orange-700 border-orange-300",
  payment_completed: "bg-emerald-50 text-emerald-700 border-emerald-300",
  paid: "bg-emerald-50 text-emerald-700 border-emerald-300",
  closed: "bg-slate-200 text-slate-700 border-slate-400",
  unpaid: "bg-slate-100 text-slate-600 border-slate-300",
};

export const PRIORITY_STYLE = {
  Low: "bg-slate-100 text-slate-600 border-slate-300",
  Medium: "bg-blue-50 text-blue-700 border-blue-300",
  High: "bg-amber-50 text-amber-700 border-amber-300",
  Urgent: "bg-red-50 text-red-700 border-red-300",
};

export const StatusChip = ({ status, testid }) => (
  <Badge variant="outline" className={`${STATUS_STYLE[status] || "bg-slate-100 text-slate-700 border-slate-300"} text-[10px] uppercase whitespace-nowrap`} data-testid={testid}>
    {String(status || "—").replace(/_/g, " ")}
  </Badge>
);

export const Tile = ({ label, value, cls = "", testid, onClick }) => (
  <button type="button" onClick={onClick} disabled={!onClick}
    className={`border rounded-md bg-white p-3 text-left ${onClick ? "hover:border-primary/60 hover:shadow-sm transition-colors" : "cursor-default"}`}
    data-testid={testid}>
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className={`text-2xl font-bold tabular-nums ${cls}`}>{value ?? 0}</div>
  </button>
);

export function useSvcMeta() {
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    let live = true;
    api.get("/service-workflow/meta").then((r) => { if (live) setMeta(r.data); }).catch(() => {});
    return () => { live = false; };
  }, []);
  return meta;
}
