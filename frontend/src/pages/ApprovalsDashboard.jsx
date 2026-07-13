import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Layers, RotateCcw, FileQuestion, XCircle, Clock, CheckCircle2 } from "lucide-react";
import ApprovalDetail from "@/components/ApprovalDetail";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const LANES = [
  { key: "pending", label: "Pending", icon: Clock, tone: "border-blue-200 bg-blue-50 text-blue-900" },
  { key: "revision_required", label: "Revision Required", icon: XCircle, tone: "border-rose-200 bg-rose-50 text-rose-900" },
  { key: "additional_info", label: "Info Needed", icon: FileQuestion, tone: "border-amber-200 bg-amber-50 text-amber-900" },
  { key: "resubmitted", label: "Resubmitted", icon: RotateCcw, tone: "border-blue-200 bg-blue-50 text-blue-900" },
  { key: "rejected", label: "Rejected", icon: XCircle, tone: "border-rose-200 bg-rose-50 text-rose-900" },
];

export default function ApprovalsDashboard() {
  const [lanes, setLanes] = useState({});
  const [totals, setTotals] = useState({});
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState("pending");
  const [viewing, setViewing] = useState(null);

  const load = async () => {
    setBusy(true);
    try {
      const { data } = await api.get("/approvals/lanes");
      setLanes(data.lanes || {});
      setTotals(data.totals || {});
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="approvals-dashboard">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="h-6 w-6 text-primary" /> Approvals Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-1">5-lane view of every approval flowing through the org. Auto-refreshes every minute.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={busy} data-testid="approvals-dashboard-refresh">Refresh</Button>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {LANES.map((l) => {
          const Icon = l.icon;
          return (
            <button
              key={l.key}
              onClick={() => setActive(l.key)}
              className={`p-3 border rounded-sm text-left transition-all ${l.tone} ${active === l.key ? "ring-2 ring-primary" : "hover:opacity-80"}`}
              data-testid={`lane-tile-${l.key}`}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                <span className="text-xs uppercase tracking-wider font-semibold">{l.label}</span>
              </div>
              <div className="text-3xl font-bold mt-2">{totals[l.key] ?? 0}</div>
            </button>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base capitalize">{LANES.find((l) => l.key === active)?.label} lane</CardTitle>
        </CardHeader>
        <CardContent>
          <LaneTable rows={lanes[active] || []} onOpen={setViewing} />
        </CardContent>
      </Card>

      <ApprovalDetail
        approval={viewing}
        open={!!viewing}
        onOpenChange={(o) => !o && setViewing(null)}
        onUpdated={() => { load(); setViewing(null); }}
      />
    </div>
  );
}

function LaneTable({ rows, onOpen }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="p-8 text-center text-muted-foreground border rounded-sm">
        <CheckCircle2 className="h-8 w-8 mx-auto mb-2 opacity-40" />
        Nothing in this lane right now.
      </div>
    );
  }
  return (
    <div className="border rounded-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="text-left p-2">Title</th>
            <th className="text-left p-2">Type</th>
            <th className="text-left p-2">Version</th>
            <th className="text-left p-2">Status</th>
            <th className="text-left p-2">Originator</th>
            <th className="text-left p-2">Updated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-testid={`lane-row-${r.id}`} className="border-t hover:bg-slate-50">
              <td className="p-2 font-medium">{r.title || r.type}</td>
              <td className="p-2 text-xs">{(r.type || "").replaceAll("_", " ")}</td>
              <td className="p-2 text-xs font-mono">v{r.version || "1.0"}{r.resubmit_count ? ` · ${r.resubmit_count}↻` : ""}</td>
              <td className="p-2"><Badge variant="outline" className="text-[10px]">{(r.status || "").replaceAll("_", " ")}</Badge></td>
              <td className="p-2 text-xs">{r.created_by || r.requested_by || "—"}</td>
              <td className="p-2 text-xs text-muted-foreground">{(r.updated_at || r.created_at || "").slice(0, 16).replace("T", " ")}</td>
              <td className="p-2"><Button size="sm" variant="outline" onClick={() => onOpen(r)} data-testid={`lane-open-${r.id}`}>Open</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
