import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { FileText, Download, ShoppingCart, Truck, Package, AlertTriangle, Building2, FolderOpen, Users } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const REGISTERS = [
  { key: "pr", label: "PR Register", icon: FileText },
  { key: "rfq", label: "RFQ Register", icon: ShoppingCart },
  { key: "po", label: "PO Register", icon: Truck },
  { key: "grn", label: "GRN Register", icon: Package },
];
const DIM_TABS = [
  { key: "department", label: "By Department", icon: Building2 },
  { key: "project", label: "By Project", icon: FolderOpen },
  { key: "vendor", label: "By Vendor", icon: Users },
];

function downloadCsv(filename, rows) {
  if (!rows || rows.length === 0) { toast.error("No rows to export"); return; }
  const keys = Object.keys(rows[0]).filter((k) => !["_id", "items", "history", "chain"].includes(k));
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "object") return `"${JSON.stringify(v).replaceAll('"', '""')}"`;
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const lines = [keys.join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export default function ProcurementReports() {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="procurement-reports">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <FileText className="h-6 w-6 text-primary" /> Procurement Reports
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Registers · pending POs · purchase-value analytics · rejected material — all exportable to CSV.
        </p>
      </div>

      <Tabs defaultValue="registers">
        <TabsList>
          <TabsTrigger value="registers" data-testid="tab-registers">Registers</TabsTrigger>
          <TabsTrigger value="pending" data-testid="tab-pending">Pending POs</TabsTrigger>
          <TabsTrigger value="dimension" data-testid="tab-dimension">By Dept / Project / Vendor</TabsTrigger>
          <TabsTrigger value="rejected" data-testid="tab-rejected">Rejected Material</TabsTrigger>
        </TabsList>

        <TabsContent value="registers"><Registers /></TabsContent>
        <TabsContent value="pending"><PendingPOs /></TabsContent>
        <TabsContent value="dimension"><ByDimension /></TabsContent>
        <TabsContent value="rejected"><RejectedMaterial /></TabsContent>
      </Tabs>
    </div>
  );
}

function Registers() {
  const [kind, setKind] = useState("pr");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState({ rows: [], count: 0, total_value: 0 });

  const load = async () => {
    const params = new URLSearchParams();
    if (from) params.set("from_date", from);
    if (to) params.set("to_date", to);
    params.set("limit", "1000");
    try {
      const { data } = await api.get(`/procurement/reports/register/${kind}?${params}`);
      setData(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  useEffect(() => { load(); /* eslint-disable-line */ }, [kind]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3 flex-wrap">
        <CardTitle className="text-base flex-1">Register</CardTitle>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="border rounded-sm p-1 text-sm" data-testid="register-kind">
          {REGISTERS.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-36" data-testid="register-from" />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-36" data-testid="register-to" />
        <Button variant="outline" onClick={load}>Apply</Button>
        <Button onClick={() => downloadCsv(`${kind}-register.csv`, data.rows)}>
          <Download className="h-4 w-4 mr-1.5" /> CSV
        </Button>
      </CardHeader>
      <CardContent>
        <div className="flex gap-3 mb-3">
          <Badge variant="outline">Count: {data.count}</Badge>
          <Badge variant="outline">Total Value: ₹{Number(data.total_value || 0).toLocaleString("en-IN")}</Badge>
        </div>
        <SimpleTable rows={data.rows} preferKeys={["dept_doc_no", "pr_number", "rfq_number", "po_number", "grn_number", "status", "department", "project", "vendor", "amount", "total", "created_at"]} />
      </CardContent>
    </Card>
  );
}

function PendingPOs() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/procurement/reports/pending-pos")
      .then((r) => setRows(r.data?.rows || []))
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Pending Purchase Orders ({rows.length})</CardTitle>
        <Button onClick={() => downloadCsv("pending-pos.csv", rows)}><Download className="h-4 w-4 mr-1.5" /> CSV</Button>
      </CardHeader>
      <CardContent>
        <SimpleTable rows={rows} preferKeys={["po_number", "dept_doc_no", "vendor", "project", "status", "amount", "delay_days", "created_at"]}
          highlight={(r) => (r.delay_days != null && r.delay_days > 14) ? "bg-rose-50" : ""} />
      </CardContent>
    </Card>
  );
}

function ByDimension() {
  const [dim, setDim] = useState("department");
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get(`/procurement/reports/by-dimension?dim=${dim}`)
      .then((r) => setRows(r.data?.rows || []))
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, [dim]);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3 flex-wrap">
        <CardTitle className="text-base flex-1">Purchase Value</CardTitle>
        <select value={dim} onChange={(e) => setDim(e.target.value)} className="border rounded-sm p-1 text-sm" data-testid="dim-select">
          {DIM_TABS.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
        </select>
        <Button onClick={() => downloadCsv(`by-${dim}.csv`, rows)}><Download className="h-4 w-4 mr-1.5" /> CSV</Button>
      </CardHeader>
      <CardContent>
        <SimpleTable rows={rows} preferKeys={["label", "po_count", "total_value"]} />
      </CardContent>
    </Card>
  );
}

function RejectedMaterial() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/procurement/reports/rejected-material")
      .then((r) => setRows(r.data?.rows || []))
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, []);
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-rose-600" /> Rejected Material ({rows.length})
        </CardTitle>
        <Button onClick={() => downloadCsv("rejected-material.csv", rows)}><Download className="h-4 w-4 mr-1.5" /> CSV</Button>
      </CardHeader>
      <CardContent>
        <SimpleTable rows={rows} preferKeys={["grn_number", "vendor", "item", "received_qty", "rejected_qty", "reject_reason", "received_at"]} />
      </CardContent>
    </Card>
  );
}

function SimpleTable({ rows, preferKeys, highlight }) {
  if (!rows || rows.length === 0) {
    return <div className="p-8 text-center text-sm text-muted-foreground border rounded-sm">No data</div>;
  }
  const allKeys = Object.keys(rows[0]).filter((k) => !["_id", "items", "history", "chain"].includes(k));
  const ordered = [...preferKeys.filter((k) => allKeys.includes(k)), ...allKeys.filter((k) => !preferKeys.includes(k))].slice(0, 10);
  return (
    <div className="border rounded-sm overflow-x-auto max-h-[60vh]">
      <table className="w-full text-xs">
        <thead className="bg-slate-50 sticky top-0">
          <tr>{ordered.map((k) => <th key={k} className="text-left p-2 font-semibold">{k}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t hover:bg-slate-50 ${highlight ? highlight(r) : ""}`}>
              {ordered.map((k) => {
                const v = r[k];
                const display = v === null || v === undefined ? "—" : (typeof v === "object" ? JSON.stringify(v) : String(v));
                return <td key={k} className="p-2 align-top max-w-xs truncate" title={display}>{display}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
