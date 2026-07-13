import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Network, Clock, Building2, ShieldAlert, Search, GitBranch } from "lucide-react";
import { toast } from "sonner";

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function DeptGovernance() {
  const [tab, setTab] = useState("delays");

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="dept-gov-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Network className="h-6 w-6 text-indigo-600" /> Department Governance
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Inter-department workflow delays · dept-wise performance · audit trail viewer
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="delays" data-testid="tab-delays"><Clock className="h-4 w-4 mr-1" /> Hand-off Delays</TabsTrigger>
          <TabsTrigger value="performance" data-testid="tab-performance"><Building2 className="h-4 w-4 mr-1" /> Dept Performance</TabsTrigger>
          <TabsTrigger value="manpower" data-testid="tab-manpower">Dept Manpower</TabsTrigger>
          <TabsTrigger value="audit" data-testid="tab-audit"><ShieldAlert className="h-4 w-4 mr-1" /> Audit Trail</TabsTrigger>
          <TabsTrigger value="record-trail" data-testid="tab-record-trail"><GitBranch className="h-4 w-4 mr-1" /> Record Trail</TabsTrigger>
        </TabsList>

        <TabsContent value="delays"><DelaysTab /></TabsContent>
        <TabsContent value="performance"><PerformanceTab /></TabsContent>
        <TabsContent value="manpower"><ManpowerTab /></TabsContent>
        <TabsContent value="audit"><AuditTab /></TabsContent>
        <TabsContent value="record-trail"><RecordTrailTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function DelaysTab() {
  const [days, setDays] = useState(90);
  const [rows, setRows] = useState([]);
  const load = async () => {
    try { const { data } = await api.get(`/dept-gov/reports/handoff-delays?days=${days}`); setRows(data.rows); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Approval Hand-off Turnaround (avg per step)</CardTitle>
        <Label className="text-xs">Last</Label>
        <Input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-20 h-8" />
        <span className="text-xs">days</span>
        <Button onClick={load} size="sm">Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded overflow-x-auto">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Doc Type</TableHead>
              <TableHead className="text-right">Samples</TableHead>
              <TableHead className="text-right">Avg / Step</TableHead>
              <TableHead className="text-right">Longest Step</TableHead>
              <TableHead className="text-right">Approved</TableHead>
              <TableHead className="text-right">Rejected</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No approval activity in this window</TableCell></TableRow>}
              {rows.map((r) => (
                <TableRow key={r.type}><TableCell className="font-medium">{r.type}</TableCell><TableCell className="text-right">{r.samples}</TableCell><TableCell className="text-right">{r.avg_hours_per_step >= 1 ? `${r.avg_hours_per_step} h` : `${r.avg_minutes_per_step} min`}</TableCell><TableCell className="text-right">{r.longest_step_minutes >= 60 ? `${Math.round(r.longest_step_minutes / 60)} h` : `${Math.round(r.longest_step_minutes)} min`}</TableCell><TableCell className="text-right"><Badge className="bg-emerald-100 text-emerald-700">{r.approved}</Badge></TableCell><TableCell className="text-right">{r.rejected > 0 ? <Badge className="bg-rose-100 text-rose-700">{r.rejected}</Badge> : <span className="text-muted-foreground">0</span>}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function PerformanceTab() {
  const [days, setDays] = useState(30);
  const [rows, setRows] = useState([]);
  const load = async () => {
    try { const { data } = await api.get(`/dept-gov/reports/dept-performance?days=${days}`); setRows(data.rows); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3">
        <CardTitle className="text-base flex-1">Department Performance · Last {days} days</CardTitle>
        <Input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-20 h-8" />
        <Button onClick={load} size="sm">Refresh</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {rows.length === 0 && <div className="text-sm text-muted-foreground">No data</div>}
        {rows.map((r) => (
          <div key={r.department} className="p-3 border rounded bg-slate-50">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold flex items-center gap-2"><Badge variant="outline" className="uppercase font-mono">{r.department}</Badge>{r.count} records · {inr(r.amount)}</div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              {(r.by_doctype || []).map((d) => (
                <div key={d.doc_type} className="p-2 rounded bg-white border">
                  <div className="font-medium">{d.doc_type}</div>
                  <div className="text-muted-foreground">{d.count} · {inr(d.amount)}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ManpowerTab() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/dept-gov/reports/dept-manpower").then(({ data }) => setRows(data.rows)).catch((e) => toast.error(apiErrorMessage(e)));
  }, []);
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Department Manpower Utilisation</CardTitle></CardHeader>
      <CardContent>
        <div className="border rounded">
          <Table>
            <TableHeader><TableRow><TableHead>Department</TableHead><TableHead className="text-right">Headcount</TableHead><TableHead className="text-right">Deployed</TableHead><TableHead className="text-right">Available</TableHead><TableHead className="text-right">Utilisation</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-6">No data</TableCell></TableRow>}
              {rows.map((r) => {
                const util = r.headcount > 0 ? Math.round((r.deployed / r.headcount) * 100) : 0;
                return (
                  <TableRow key={r.department}><TableCell className="font-medium">{r.department}</TableCell><TableCell className="text-right">{r.headcount}</TableCell><TableCell className="text-right">{r.deployed}</TableCell><TableCell className="text-right">{r.available}</TableCell><TableCell className="text-right"><Badge className={util >= 80 ? "bg-emerald-100 text-emerald-700" : util >= 50 ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700"}>{util}%</Badge></TableCell></TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function AuditTab() {
  const [filter, setFilter] = useState({ dept: "", action: "", resource: "", date_from: "", date_to: "" });
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const p = new URLSearchParams();
      Object.entries(filter).forEach(([k, v]) => { if (v) p.append(k, v); });
      const { data } = await api.get(`/dept-gov/audit/by-dept?${p}`);
      setRows(data.rows || []);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Audit Trail</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-3">
          <Select value={filter.dept} onValueChange={(v) => setFilter({ ...filter, dept: v === "all" ? "" : v })}>
            <SelectTrigger data-testid="audit-dept"><SelectValue placeholder="Department" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Depts</SelectItem>
              {["hr","sales","accounts","finance","store","safety","logistics","projects","procurement"].map((d) => (
                <SelectItem key={d} value={d}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input placeholder="Action (create/update/delete/approve)" value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })} />
          <Input placeholder="Resource (e.g. employee_advances)" value={filter.resource} onChange={(e) => setFilter({ ...filter, resource: e.target.value })} />
          <Input type="date" value={filter.date_from} onChange={(e) => setFilter({ ...filter, date_from: e.target.value })} />
          <Input type="date" value={filter.date_to} onChange={(e) => setFilter({ ...filter, date_to: e.target.value })} />
          <Button onClick={load} disabled={busy}><Search className="h-4 w-4 mr-1" />{busy ? "…" : "Search"}</Button>
        </div>
        <div className="border rounded max-h-[500px] overflow-y-auto">
          <Table>
            <TableHeader><TableRow><TableHead>When</TableHead><TableHead>User</TableHead><TableHead>Action</TableHead><TableHead>Resource</TableHead><TableHead>Record ID</TableHead><TableHead>IP</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-6">No matching logs</TableCell></TableRow>}
              {rows.map((r, i) => (
                <TableRow key={i}><TableCell className="text-xs">{new Date(r.at || r.created_at).toLocaleString()}</TableCell><TableCell className="text-xs">{r.user_name || r.user_id}<div className="text-[10px] text-muted-foreground">{r.user_role}</div></TableCell><TableCell><Badge variant="outline">{r.action}</Badge></TableCell><TableCell className="text-xs font-mono">{r.resource}</TableCell><TableCell className="text-xs font-mono truncate max-w-[160px]">{r.record_id}</TableCell><TableCell className="text-xs text-muted-foreground">{r.ip}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function RecordTrailTab() {
  const [coll, setColl] = useState("employee_advances");
  const [rid, setRid] = useState("");
  const [data, setData] = useState(null);
  const load = async () => {
    if (!coll || !rid) { toast.error("Pick collection and record id"); return; }
    try { const { data } = await api.get(`/dept-gov/audit/record/${coll}/${rid}`); setData(data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Per-Record Trail (Created → Approved → Modified)</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input placeholder="collection (e.g. employee_advances)" value={coll} onChange={(e) => setColl(e.target.value)} className="max-w-xs" />
          <Input placeholder="record id" value={rid} onChange={(e) => setRid(e.target.value)} className="flex-1" />
          <Button onClick={load}>Load</Button>
        </div>
        {data && (
          <div className="space-y-2">
            <div className="p-2 border rounded bg-slate-50 text-xs">
              <strong>{data.record.collection} · {data.record.dept_doc_no || data.record.id}</strong> · Owner: <Badge variant="outline">{data.record.ownership_department || "—"}</Badge> · {data.audit_log_count} audit log(s)
            </div>
            <ul className="space-y-1">
              {data.timeline.map((t, i) => (
                <li key={i} className="flex items-center gap-2 border-b pb-1 text-xs">
                  <Badge variant="outline" className={t.phase === "created" ? "bg-blue-100 text-blue-800" : t.phase === "approval" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}>{t.phase}{t.action ? `:${t.action}` : ""}</Badge>
                  <span className="text-muted-foreground">{t.at && new Date(t.at).toLocaleString()}</span>
                  <span>· {t.by} <span className="text-muted-foreground">({t.by_role})</span></span>
                  {t.department && <Badge variant="outline" className="text-[10px]">{t.department}</Badge>}
                  {t.comment && <span className="italic">"{t.comment}"</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
