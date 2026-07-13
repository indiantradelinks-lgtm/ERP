/**
 * Vendor Compliance Center · Procurement Extras
 *
 * Single workbench for compliance + alerts:
 *   • Document expiry alerts (vendor docs expiring within window)
 *   • Procurement notifications inbox (PR pending, RFQ pending, payment due …)
 *   • Vendor performance 5-tier (Excellent / Good / Average / Poor / Blacklisted)
 *
 * Backend:
 *   /api/procurement-extras/document-expiry
 *   /api/procurement-extras/notifications
 *   /api/procurement-extras/performance/tiers
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck, BellRing, Award, RefreshCcw, ExternalLink, AlertTriangle } from "lucide-react";

const SEV_TONE = {
  critical: "bg-rose-100 text-rose-700 border-rose-200",
  expired: "bg-rose-100 text-rose-700 border-rose-200",
  warning: "bg-amber-100 text-amber-700 border-amber-200",
  info: "bg-blue-100 text-blue-700 border-blue-200",
};
const TIER_TONE = {
  Excellent: "bg-emerald-100 text-emerald-700",
  Good: "bg-green-100 text-green-700",
  Average: "bg-amber-100 text-amber-700",
  Poor: "bg-orange-100 text-orange-700",
  Blacklisted: "bg-rose-100 text-rose-700",
};

export default function VendorComplianceCenter() {
  const [tab, setTab] = useState("notifications");
  const [notifications, setNotifications] = useState({ total: 0, items: [] });
  const [docExpiry, setDocExpiry] = useState({ count: 0, alerts: [] });
  const [tiers, setTiers] = useState({ counts: {}, rows: [] });
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [nRes, dRes, tRes] = await Promise.all([
        api.get("/procurement-extras/notifications"),
        api.get("/procurement-extras/document-expiry?window_days=60&include_expired=true"),
        api.get("/procurement-extras/performance/tiers"),
      ]);
      setNotifications(nRes.data || { total: 0, items: [] });
      setDocExpiry(dRes.data || { count: 0, alerts: [] });
      setTiers(tRes.data || { counts: {}, rows: [] });
    } catch (e) {
      toast.error("Failed to load compliance data");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadAll(); }, []);

  return (
    <div className="p-6 space-y-4" data-testid="page-compliance-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="h-6 w-6 text-primary" /> Vendor Compliance Center</h1>
          <p className="text-sm text-muted-foreground">Procurement inbox · document expiry · vendor performance — single pane of glass.</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadAll} data-testid="cc-refresh"><RefreshCcw className="h-4 w-4 mr-1" />Refresh</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <KpiCard testid="kpi-notifications" icon={<BellRing className="h-4 w-4" />} label="Open Notifications" value={notifications.total} tone="amber" />
        <KpiCard testid="kpi-doc-expiry" icon={<AlertTriangle className="h-4 w-4" />} label="Doc Expiry (60d)" value={docExpiry.count} tone="rose" />
        <KpiCard testid="kpi-vendors-evaluated" icon={<Award className="h-4 w-4" />} label="Vendors Evaluated" value={tiers.rows?.length || 0} tone="emerald" />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="notifications" data-testid="cc-tab-notifications"><BellRing className="h-3.5 w-3.5 mr-1" />Notifications</TabsTrigger>
          <TabsTrigger value="doc-expiry" data-testid="cc-tab-doc-expiry"><AlertTriangle className="h-3.5 w-3.5 mr-1" />Doc Expiry</TabsTrigger>
          <TabsTrigger value="tiers" data-testid="cc-tab-tiers"><Award className="h-3.5 w-3.5 mr-1" />Vendor Tiers</TabsTrigger>
        </TabsList>

        <TabsContent value="notifications">
          <Card><CardContent className="p-0">
            {loading && <div className="py-8 text-center text-slate-400">Loading…</div>}
            {!loading && notifications.items.length === 0 && <div className="py-12 text-center text-emerald-600"><ShieldCheck className="h-8 w-8 mx-auto mb-2" />All clear — no procurement alerts.</div>}
            <ul className="divide-y">
              {notifications.items.map((n, i) => (
                <li key={i} className="px-4 py-3 flex items-center gap-3" data-testid={`notif-${n.kind}`}>
                  <Badge className={SEV_TONE[n.severity] || SEV_TONE.info}>{n.severity}</Badge>
                  <span className="flex-1 text-sm">{n.title}</span>
                  {n.link && <a href={n.link} className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">Open <ExternalLink className="h-3 w-3" /></a>}
                </li>
              ))}
            </ul>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="doc-expiry">
          <Card><CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-3 py-2 text-left">Severity</th>
                  <th className="px-3 py-2 text-left">Vendor</th>
                  <th className="px-3 py-2 text-left">Document</th>
                  <th className="px-3 py-2 text-left">Expiry</th>
                  <th className="px-3 py-2 text-right">Days</th>
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-400">Loading…</td></tr>}
                {!loading && docExpiry.alerts.length === 0 && <tr><td colSpan={5} className="px-3 py-8 text-center text-emerald-600">No documents expiring in the next 60 days.</td></tr>}
                {docExpiry.alerts.map((a, i) => (
                  <tr key={i} className="border-b" data-testid={`doc-row-${i}`}>
                    <td className="px-3 py-2"><Badge className={SEV_TONE[a.severity] || ""}>{a.severity}</Badge></td>
                    <td className="px-3 py-2 text-xs"><span className="font-mono">{a.vendor_code}</span> · {a.vendor_name}</td>
                    <td className="px-3 py-2 text-xs">{a.doc_type}{a.doc_name ? ` · ${a.doc_name}` : ""}</td>
                    <td className="px-3 py-2 text-xs">{a.expiry}</td>
                    <td className="px-3 py-2 text-right text-xs font-mono">{a.days_to_expiry < 0 ? `−${-a.days_to_expiry}` : a.days_to_expiry}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="tiers">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
            {["Excellent", "Good", "Average", "Poor", "Blacklisted"].map((t) => (
              <Card key={t} className="p-3" data-testid={`tier-card-${t}`}>
                <div className="text-xs text-slate-600">{t}</div>
                <div className="text-2xl font-bold mt-1"><span className={`inline-block px-2 py-0.5 rounded text-base ${TIER_TONE[t]}`}>{tiers.counts?.[t] || 0}</span></div>
              </Card>
            ))}
          </div>
          <Card><CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                <tr>
                  <th className="px-3 py-2 text-left">Code</th>
                  <th className="px-3 py-2 text-left">Vendor</th>
                  <th className="px-3 py-2 text-left">Type</th>
                  <th className="px-3 py-2 text-right">Score</th>
                  <th className="px-3 py-2 text-left">Tier</th>
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-400">Loading…</td></tr>}
                {!loading && tiers.rows.map((r) => (
                  <tr key={r.vendor_id} className="border-b" data-testid={`tier-row-${r.vendor_id}`}>
                    <td className="px-3 py-2 font-mono text-xs">{r.vendor_code}</td>
                    <td className="px-3 py-2 text-xs">{r.vendor_name}</td>
                    <td className="px-3 py-2 text-xs">{r.vendor_type || "—"}</td>
                    <td className="px-3 py-2 text-right text-xs">{r.score}</td>
                    <td className="px-3 py-2"><Badge className={TIER_TONE[r.tier] || ""}>{r.tier}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function KpiCard({ icon, label, value, tone = "slate", testid }) {
  const colors = { amber: "border-amber-200 bg-amber-50", rose: "border-rose-200 bg-rose-50", emerald: "border-emerald-200 bg-emerald-50", slate: "border-slate-200 bg-slate-50" };
  return (
    <Card className={`${colors[tone] || colors.slate} border`} data-testid={testid}>
      <CardContent className="p-4 flex items-center gap-3">
        <div className="p-2 rounded bg-white">{icon}</div>
        <div>
          <div className="text-xs text-slate-600">{label}</div>
          <div className="text-2xl font-bold">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}
