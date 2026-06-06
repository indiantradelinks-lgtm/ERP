import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Wallet, ChevronRight, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

/**
 * Compact self-service widget for the logged-in employee.
 * Hidden if the user has no matching employee record (HR account / vendor / etc.).
 */
export default function MyAdvancesWidget() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/advances/me/summary")
      .then(({ data }) => setData(data))
      .catch(() => setData({ linked: false }))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data?.linked || (data.active_advances?.length === 0 && data.history?.length === 0)) {
    return null;
  }

  const downloadStatement = () => {
    const rows = [["Advance #", "Type", "Status", "Requested", "Approved", "Outstanding", "Created"]];
    (data.history || []).forEach((h) => rows.push([h.advance_no, h.advance_type, h.status, h.requested_amount, h.approved_amount, h.outstanding, h.created_at?.slice(0, 10)]));
    const csv = rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `advance-statement-${data.employee.code || "me"}.csv`;
    a.click();
  };

  return (
    <Card data-testid="my-advances-widget" className="border-emerald-200">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Wallet className="h-4 w-4 text-emerald-600" /> My Advances
          {data.outstanding_total > 0 && <Badge className="bg-emerald-100 text-emerald-800">Outstanding {inr(data.outstanding_total)}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {data.next_emi && (
          <div className="p-2 rounded bg-amber-50 border border-amber-200 flex items-center gap-2 text-xs">
            <AlertCircle className="h-3 w-3 text-amber-600" />
            <span>Next EMI <strong>{inr(data.next_emi.emi)}</strong> on {data.next_emi.advance_no} · {data.next_emi.month || "this month"}</span>
          </div>
        )}

        {data.active_advances?.length === 0 ? (
          <div className="text-xs text-muted-foreground">No active advances</div>
        ) : (
          <ul className="space-y-1">
            {(data.active_advances || []).slice(0, 3).map((a) => (
              <li key={a.id} className="flex items-center justify-between border-b last:border-0 pb-1">
                <div>
                  <div className="font-medium text-xs">{a.advance_no} <Badge variant="outline" className="ml-1 text-[10px]">{a.status.replace(/_/g, " ")}</Badge></div>
                  <div className="text-[10px] text-muted-foreground">{a.advance_type} · EMI {inr(a.emi)} × {a.remaining_installments}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold">{inr(a.outstanding)}</div>
                  <div className="text-[10px] text-muted-foreground">outstanding</div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="flex gap-2 pt-1">
          <Button asChild size="sm" variant="outline" className="flex-1" data-testid="my-adv-view-all">
            <Link to="/app/hr/advances">View All <ChevronRight className="h-3 w-3 ml-1" /></Link>
          </Button>
          <Button size="sm" variant="outline" onClick={downloadStatement} data-testid="my-adv-statement-btn">Statement</Button>
        </div>
      </CardContent>
    </Card>
  );
}
