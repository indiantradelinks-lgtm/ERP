/**
 * Security Center · Phase 9
 * Single-payload snapshot of RBAC posture: roles, permissions, audit volume,
 * exports, masking config, period locks. Read-only management cockpit.
 * Backend: /api/finance/phase9/security-summary
 *          /api/finance/phase9/export-logs
 *          /api/finance/phase9/extended-actions
 *          /api/finance/phase9/role-tile-visibility
 *          /api/finance/phase9/permission-matrix.csv
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Shield, Activity, Download, Eye, Lock, RefreshCcw } from "lucide-react";
import { fmtDT } from "@/lib/datetime";

export default function SecurityCenter() {
  const [summary, setSummary] = useState(null);
  const [exports, setExports] = useState([]);
  const [actions, setActions] = useState({});
  const [tileVis, setTileVis] = useState(null);
  const [masking, setMasking] = useState(null);

  const load = async () => {
    try {
      const [s, e, a, t, m] = await Promise.all([
        api.get("/finance/phase9/security-summary"),
        api.get("/finance/phase9/export-logs?limit=50"),
        api.get("/finance/phase9/extended-actions"),
        api.get("/finance/phase9/role-tile-visibility"),
        api.get("/finance/phase9/masking-config"),
      ]);
      setSummary(s.data); setExports(e.data || []);
      setActions(a.data.actions || {}); setTileVis(t.data); setMasking(m.data);
    } catch (err) { toast.error("Failed to load security data"); }
  };
  useEffect(() => { load(); }, []);

  const downloadMatrix = () => {
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/finance/phase9/permission-matrix.csv`, "_blank");
    toast.success("Permission matrix download started");
  };

  if (!summary) return <div className="p-6 text-slate-400">Loading security center…</div>;

  const kpis = [
    { label: "Active Users", value: summary.users.active, icon: Shield, total: summary.users.total },
    { label: "Resources Gated", value: summary.permissions.resources, icon: Lock },
    { label: "Custom Overrides", value: summary.permissions.overrides, icon: Activity },
    { label: "Audit Events (7d)", value: summary.audit.events_7d, icon: Activity },
    { label: "Exports (7d)", value: summary.exports.events_7d, icon: Download },
    { label: "Period Locks", value: summary.period_locks.active, icon: Lock },
    { label: "Pending Approvals", value: summary.approvals.pending, icon: Activity },
    { label: "Failed Logins (24h)", value: summary.security_events.failed_logins_24h, icon: Shield },
  ];

  return (
    <div className="p-6 space-y-4" data-testid="page-security-center">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2"><Shield className="h-6 w-6" /> Security Center</h1>
          <p className="text-sm text-slate-400">Role-based access, audit posture and data-control snapshot</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={downloadMatrix} data-testid="btn-export-matrix">
            <Download className="h-4 w-4 mr-1" /> Export Matrix CSV
          </Button>
          <Button variant="outline" onClick={load} data-testid="btn-reload-security">
            <RefreshCcw className="h-4 w-4 mr-1" /> Reload
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map((k, i) => (
          <Card key={i} data-testid={`kpi-${k.label.toLowerCase().replace(/ /g, "-")}`}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase text-slate-400">{k.label}</span>
                <k.icon className="h-4 w-4 text-slate-500" />
              </div>
              <div className="text-2xl font-semibold mt-1">{k.value}{k.total ? <span className="text-xs text-slate-500"> / {k.total}</span> : null}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="roles">
        <TabsList>
          <TabsTrigger value="roles" data-testid="tab-roles">Roles & Distribution</TabsTrigger>
          <TabsTrigger value="actions" data-testid="tab-actions">Extended Actions</TabsTrigger>
          <TabsTrigger value="masking" data-testid="tab-masking">Sensitive Field Masking</TabsTrigger>
          <TabsTrigger value="tiles" data-testid="tab-tiles">Dashboard Tile Visibility</TabsTrigger>
          <TabsTrigger value="exports" data-testid="tab-exports-log">Export / Print Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="roles" className="mt-4">
          <Card><CardContent className="p-4">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Role</th><th className="text-right">User Count</th></tr></thead>
              <tbody>
                {Object.entries(summary.users.by_role).sort((a, b) => b[1] - a[1]).map(([role, n]) => (
                  <tr key={role} className="border-b border-slate-800"><td className="py-2">{role}</td><td className="text-right">{n}</td></tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="actions" className="mt-4">
          <Card><CardContent className="p-4">
            <p className="text-xs text-slate-400 mb-3">Fine-grained verbs available on finance resources. Each maps to a base RBAC action (read/write/delete) so existing gates keep working.</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {Object.entries(actions).map(([key, def]) => (
                <div key={key} className="p-3 border border-slate-700 rounded" data-testid={`action-${key}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{def.label}</span>
                    <Badge variant="outline">{def.maps_to}</Badge>
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{key}</div>
                </div>
              ))}
            </div>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="masking" className="mt-4">
          <Card><CardContent className="p-4">
            <p className="text-xs text-slate-400 mb-3">Roles {masking?.privileged_roles?.join(", ")} see everything. All other roles see masked/stripped values:</p>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Resource</th><th>Field</th><th>Action</th></tr></thead>
              <tbody>
                {Object.entries(masking?.rules || {}).flatMap(([res, fields]) =>
                  Object.entries(fields).map(([f, act]) => (
                    <tr key={`${res}-${f}`} className="border-b border-slate-800">
                      <td className="py-2">{res}</td><td>{f}</td>
                      <td><Badge variant={act === "strip" ? "destructive" : "secondary"}>{act}</Badge></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="tiles" className="mt-4">
          <Card><CardContent className="p-4">
            <p className="text-xs text-slate-400 mb-3">Which roles see which finance dashboard tiles.</p>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Tile</th><th>Visible To</th></tr></thead>
              <tbody>
                {Object.entries(tileVis?.config || {}).map(([tile, roles]) => (
                  <tr key={tile} className="border-b border-slate-800">
                    <td className="py-2">{tile}</td>
                    <td className="text-xs">{roles.includes("*") ? <Badge>All authenticated</Badge> : roles.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="exports" className="mt-4">
          <Card><CardContent className="p-4">
            {exports.length === 0 ? <div className="text-slate-400 text-sm">No export/print activity logged yet.</div> :
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-700"><th className="py-2">Time</th><th>Actor</th><th>Activity</th><th>Resource</th><th>Format</th></tr></thead>
                <tbody>
                  {exports.map((e, i) => (
                    <tr key={i} className="border-b border-slate-800" data-testid={`export-row-${i}`}>
                      <td className="py-2 text-xs text-slate-400">{fmtDT(e.ts)}</td>
                      <td>{e.actor_name}</td>
                      <td><Badge>{e.activity}</Badge></td>
                      <td>{e.resource}</td>
                      <td>{e.format}</td>
                    </tr>
                  ))}
                </tbody>
              </table>}
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
