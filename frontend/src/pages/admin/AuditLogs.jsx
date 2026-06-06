import { useEffect, useState } from "react";
import { Search, FileSearch } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const ACTION_TONE = {
  create: "success",
  update: "primary",
  delete: "danger",
  login: "info",
  upsert: "primary",
  reset: "warning",
};

export default function AuditLogs() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ resource: "", action: "", q: "" });
  const [detail, setDetail] = useState(null);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.resource) params.set("resource", filter.resource);
      if (filter.action) params.set("action", filter.action);
      params.set("limit", "200");
      const { data } = await api.get(`/admin/audit-logs?${params.toString()}`);
      setRows(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load audit logs");
    }
  };
  useEffect(() => { load(); }, [filter.resource, filter.action]);

  const filtered = rows.filter((r) => {
    if (!filter.q) return true;
    const q = filter.q.toLowerCase();
    return [r.actor_name, r.actor_role, r.resource, r.action, r.record_id].some((v) => String(v ?? "").toLowerCase().includes(q));
  });

  return (
    <div className="space-y-6" data-testid="admin-audit">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Super Admin · Audit</div>
        <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
          <FileSearch className="h-7 w-7 text-primary" /> Audit Trail
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Every create / update / delete across the system is journalled with actor, IP and before/after payloads.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search actor / record…" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} data-testid="audit-search" />
          </div>
          <Input className="h-9 rounded-sm w-44" placeholder="Filter resource" value={filter.resource} onChange={(e) => setFilter({ ...filter, resource: e.target.value })} data-testid="audit-filter-resource" />
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm" value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })} data-testid="audit-filter-action">
            <option value="">All actions</option>
            <option value="create">Create</option>
            <option value="update">Update</option>
            <option value="delete">Delete</option>
            <option value="upsert">Upsert</option>
            <option value="reset">Reset</option>
            <option value="login">Login</option>
          </select>
          <div className="ml-auto text-xs text-muted-foreground"><span className="text-foreground font-semibold">{filtered.length}</span> of {rows.length} events</div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Actor</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Action</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Resource</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Record</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-10">No events match the filters.</TableCell></TableRow>
              )}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30 cursor-pointer" onClick={() => setDetail(r)} data-testid={`audit-row-${r.id}`}>
                  <TableCell className="font-mono-data text-xs whitespace-nowrap">{(r.ts || "").slice(0, 19).replace("T", " ")}</TableCell>
                  <TableCell className="text-sm"><div className="font-semibold">{r.actor_name || "—"}</div><div className="text-[10px] uppercase tracking-wider text-muted-foreground">{(r.actor_role || "").replaceAll("_", " ")}</div></TableCell>
                  <TableCell><StatusBadge text={r.action} tone={ACTION_TONE[r.action] || "neutral"} /></TableCell>
                  <TableCell className="font-mono-data text-xs">{r.resource}</TableCell>
                  <TableCell className="font-mono-data text-[11px] text-muted-foreground">{(r.record_id || "").slice(0, 12)}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.ip || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-3xl rounded-sm" data-testid="audit-detail">
          <DialogHeader>
            <DialogTitle className="font-display">Audit Event</DialogTitle>
            <DialogDescription className="sr-only">Before/after payload for this audit event.</DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><span className="text-muted-foreground">Actor</span><div className="font-semibold">{detail.actor_name}</div></div>
                <div><span className="text-muted-foreground">Role</span><div className="font-semibold">{(detail.actor_role || "").replaceAll("_", " ")}</div></div>
                <div><span className="text-muted-foreground">Resource</span><div className="font-mono-data">{detail.resource}</div></div>
                <div><span className="text-muted-foreground">Record</span><div className="font-mono-data">{detail.record_id}</div></div>
                <div><span className="text-muted-foreground">Action</span><div><StatusBadge text={detail.action} tone={ACTION_TONE[detail.action] || "neutral"} /></div></div>
                <div><span className="text-muted-foreground">IP</span><div className="font-mono-data">{detail.ip || "—"}</div></div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Before</div>
                  <pre className="bg-muted p-2 rounded-sm text-[11px] max-h-72 overflow-auto">{JSON.stringify(detail.before, null, 2)}</pre>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">After</div>
                  <pre className="bg-muted p-2 rounded-sm text-[11px] max-h-72 overflow-auto">{JSON.stringify(detail.after, null, 2)}</pre>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
