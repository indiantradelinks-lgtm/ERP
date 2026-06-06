import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Link2, ChevronRight, ExternalLink } from "lucide-react";

const COLLECTION_TO_ROUTE = {
  enquiries: "/app/enquiries",
  quotations: "/app/quotations",
  orders: "/app/orders",
  projects: "/app/projects",
  sites: "/app/clients",
  purchase_requisitions: "/app/purchase-requisitions",
  rfqs: "/app/rfqs",
  purchase_orders: "/app/purchase-orders",
  grns: "/app/grn",
  dprs: "/app/dprs",
  measurements: "/app/measurements",
  ra_bills: "/app/ra-bills",
  deployments: "/app/deployments",
  safety_reports: "/app/safety",
  vendor_invoices: "/app/vendors",
  vendor_evaluations: "/app/vendors",
};

/**
 * Reusable cross-module link panel.
 *
 * Props:
 *  - resource: parent collection name (e.g. "projects", "clients")
 *  - recordId: id of the parent record
 *  - title (optional)
 */
export default function LinkagePanel({ resource, recordId, title = "Linked Records" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!resource || !recordId) return;
    setLoading(true);
    setErr(null);
    api
      .get(`/linkage/graph/${resource}/${recordId}`)
      .then(({ data }) => setData(data))
      .catch((e) => setErr(e.response?.data?.detail || "Failed to load linkage graph"))
      .finally(() => setLoading(false));
  }, [resource, recordId]);

  if (loading) return <div className="text-xs text-muted-foreground p-2">Loading linked records…</div>;
  if (err) return <div className="text-xs text-rose-600 p-2">{err}</div>;
  if (!data) return null;

  const total = (data.groups || []).reduce((s, g) => s + g.count, 0);

  return (
    <Card data-testid="linkage-panel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Link2 className="h-4 w-4 text-blue-600" /> {title}
          <Badge variant="outline" className="ml-2">{total}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.groups.length === 0 && (
          <div className="text-xs text-muted-foreground">No linked records found.</div>
        )}
        {data.groups.map((g) => (
          <div key={g.collection} className="border-t pt-2" data-testid={`linkage-group-${g.collection}`}>
            <div className="flex items-center justify-between mb-1">
              <div className="text-xs font-semibold uppercase tracking-wide">{g.label}</div>
              <Badge variant="outline">{g.count}</Badge>
            </div>
            <ul className="space-y-1 text-sm">
              {g.items.slice(0, 5).map((row) => {
                const route = COLLECTION_TO_ROUTE[g.collection];
                const labelKey =
                  row.code || row.po_number || row.quote_number || row.enquiry_no || row.order_no || row.rfq_no ||
                  row.pr_no || row.grn_no || row.dpr_no || row.measurement_no || row.bill_no || row.report_id ||
                  row.payment_no || row.site_code || row.name || row.employee_name || row.id;
                const meta = row.status || row.severity || row.amount || row.total || row.gross || row.billable_value || "";
                return (
                  <li key={row.id} className="flex items-center justify-between hover:bg-slate-50 px-2 py-1 rounded">
                    {route ? (
                      <RouterLink to={route} className="text-blue-600 hover:underline flex items-center gap-1 truncate">
                        {labelKey}
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </RouterLink>
                    ) : (
                      <span className="truncate">{labelKey}</span>
                    )}
                    <span className="text-xs text-muted-foreground ml-2">{String(meta)}</span>
                  </li>
                );
              })}
              {g.items.length > 5 && (
                <li className="text-xs text-muted-foreground flex items-center gap-1 pl-2">
                  <ChevronRight className="h-3 w-3" /> + {g.items.length - 5} more
                </li>
              )}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
