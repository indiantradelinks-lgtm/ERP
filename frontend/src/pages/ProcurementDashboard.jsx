import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, ClipboardList, FileText, ShoppingCart, PackageCheck, ArrowRight, Clock, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ProcurementDashboard() {
  const navigate = useNavigate();
  const [k, setK] = useState(null);

  useEffect(() => {
    api.get("/procurement/dashboard")
      .then((r) => setK(r.data.kpis))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load dashboard"));
  }, []);

  if (!k) return <div className="text-sm text-muted-foreground py-10">Loading…</div>;

  const tiles = [
    { label: "PR · Total", value: k.pr_total, tone: "primary", icon: ClipboardList, link: "/app/purchase-requisitions" },
    { label: "PR · Pending", value: k.pr_pending, tone: "warning", icon: Clock, link: "/app/purchase-requisitions" },
    { label: "PR · Approved", value: k.pr_approved, tone: "success", icon: ClipboardList, link: "/app/purchase-requisitions" },
    { label: "RFQ · Open", value: k.rfq_open, tone: "info", icon: FileText, link: "/app/rfqs" },
    { label: "PO · Open", value: k.po_open, tone: "info", icon: ShoppingCart, link: "/app/purchase-orders" },
    { label: "GRN · Total", value: k.grn_total, tone: "primary", icon: PackageCheck, link: "/app/grn" },
    { label: "GRN · Partial", value: k.grn_partial, tone: "warning", icon: PackageCheck, link: "/app/grn" },
    { label: "Avg PR→PO (d)", value: k.avg_cycle_days ?? "—", tone: "success", icon: TrendingUp },
  ];
  const TONE_TEXT = { primary: "text-primary", info: "text-chart-3", success: "text-success", warning: "text-warning", danger: "text-destructive" };

  return (
    <div className="space-y-6" data-testid="procurement-dashboard">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Briefcase className="h-3 w-3" /> Procurement · Command Centre
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Procurement Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">PR → RFQ → PO → GRN cycle health, in one glance.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {tiles.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.label}
              onClick={() => t.link && navigate(t.link)}
              className="text-left bg-card border border-border rounded-sm p-4 hover:border-primary/40 transition-colors"
              data-testid={`pd-tile-${t.label.toLowerCase().replaceAll(" ", "-").replaceAll("·", "")}`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{t.label}</div>
                  <div className={`font-display font-black text-3xl tabular mt-1 ${TONE_TEXT[t.tone] || "text-foreground"}`}>{t.value ?? 0}</div>
                </div>
                <Icon className={`h-6 w-6 ${TONE_TEXT[t.tone] || "text-muted-foreground"}`} />
              </div>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {[
          { label: "New PR", to: "/app/purchase-requisitions", icon: ClipboardList },
          { label: "New RFQ", to: "/app/rfqs", icon: FileText },
          { label: "Purchase Orders", to: "/app/purchase-orders", icon: ShoppingCart },
          { label: "Record GRN", to: "/app/grn", icon: PackageCheck },
        ].map((q) => {
          const I = q.icon;
          return (
            <Button key={q.label} variant="outline" className="rounded-sm h-12 justify-between" onClick={() => navigate(q.to)} data-testid={`pd-quick-${q.label.toLowerCase().replaceAll(" ", "-")}`}>
              <span className="flex items-center gap-2"><I className="h-4 w-4" /> {q.label}</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          );
        })}
      </div>
    </div>
  );
}
