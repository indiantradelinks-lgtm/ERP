import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { FileText, ShoppingCart, Truck, Package, CheckCircle2, AlertCircle, ArrowRight } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Link } from "react-router-dom";
import { toast } from "sonner";

const KIND_META = {
  pr: { icon: FileText, label: "Purchase Requisition", path: "/app/purchase-requisitions", tone: "bg-blue-50 border-blue-200 text-blue-900" },
  rfq: { icon: ShoppingCart, label: "Request for Quote", path: "/app/rfqs", tone: "bg-violet-50 border-violet-200 text-violet-900" },
  po: { icon: Truck, label: "Purchase Order", path: "/app/purchase-orders", tone: "bg-emerald-50 border-emerald-200 text-emerald-900" },
  grn: { icon: Package, label: "Goods Receipt Note", path: "/app/grn", tone: "bg-amber-50 border-amber-200 text-amber-900" },
};

function statusTone(s) {
  if (!s) return "bg-slate-100 text-slate-700";
  const ok = ["approved", "po_generated", "closed", "received", "vendor_selected", "converted_to_po"];
  const warn = ["partially_received", "partially_fulfilled", "partial_accepted", "under_evaluation", "response_pending", "pending_approval"];
  const bad = ["rejected", "rejected_revision_required", "pending_revision", "cancelled"];
  if (ok.includes(s)) return "bg-emerald-100 text-emerald-700";
  if (warn.includes(s)) return "bg-amber-100 text-amber-700";
  if (bad.includes(s)) return "bg-rose-100 text-rose-700";
  return "bg-blue-100 text-blue-700";
}

export default function LineageTrail({ kind, recordId, className = "" }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!kind || !recordId) return;
    setBusy(true);
    api.get(`/procurement/lineage/${kind}/${recordId}`)
      .then((r) => setData(r.data))
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setBusy(false));
  }, [kind, recordId]);

  if (busy && !data) return <div className="p-3 text-xs text-muted-foreground">Loading lineage…</div>;
  if (!data) return null;

  const { chain, fulfilment, anchor } = data;

  return (
    <Card className={className} data-testid="lineage-trail">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          Procurement Lineage
          <Badge variant="outline" className="text-[10px]">anchor: {anchor.toUpperCase()}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-stretch gap-2 overflow-x-auto pb-2">
          {chain.map((node, i) => {
            const meta = KIND_META[node.kind] || { icon: FileText, label: node.kind, path: "#", tone: "bg-slate-50 border-slate-200" };
            const Icon = meta.icon;
            const isAnchor = node.kind === anchor && node.id === recordId;
            return (
              <div key={`${node.kind}-${node.id}`} className="flex items-center gap-2">
                <Link
                  to={`${meta.path}?id=${node.id}`}
                  className={`flex-1 min-w-[180px] p-3 border rounded-sm ${meta.tone} ${isAnchor ? "ring-2 ring-primary" : "hover:opacity-80"} transition-all`}
                  data-testid={`lineage-node-${node.kind}`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4" />
                    <span className="text-[10px] uppercase tracking-wider font-bold">{meta.label}</span>
                  </div>
                  <div className="text-sm font-mono mt-1.5 truncate">{node.dept_doc_no || node.doc_no}</div>
                  <div className="mt-1.5">
                    <Badge className={`${statusTone(node.status)} text-[10px]`}>
                      {(node.status || "—").replaceAll("_", " ")}
                    </Badge>
                  </div>
                  {(node.vendor || node.amount) && (
                    <div className="text-[10px] text-muted-foreground mt-1 truncate">
                      {node.vendor && <span>{node.vendor}</span>}
                      {node.vendor && node.amount ? " · " : ""}
                      {node.amount ? `₹${Number(node.amount).toLocaleString("en-IN")}` : ""}
                    </div>
                  )}
                </Link>
                {i < chain.length - 1 && <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />}
              </div>
            );
          })}
        </div>

        {fulfilment.ordered > 0 && (
          <div className="border-t pt-3" data-testid="lineage-fulfilment">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold flex items-center gap-1">
                {fulfilment.pct >= 100 ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                )}
                Fulfilment
              </span>
              <span className="text-xs text-muted-foreground">
                {fulfilment.received} / {fulfilment.ordered} ({fulfilment.pct}%)
                {fulfilment.rejected > 0 && (
                  <span className="ml-2 text-rose-600">· {fulfilment.rejected} rejected</span>
                )}
              </span>
            </div>
            <Progress value={fulfilment.pct} className="h-2" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
