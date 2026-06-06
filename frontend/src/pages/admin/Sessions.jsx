import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function Sessions() {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    api.get("/admin/login-activity?limit=200")
      .then((r) => setRows(r.data))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load sessions"));
  }, []);

  return (
    <div className="space-y-6" data-testid="admin-sessions">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Super Admin · Sessions</div>
        <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
          <Activity className="h-7 w-7 text-primary" /> Session Monitor
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Recent successful sign-ins, IPs and user-agent fingerprints. Tokens are JWT-based with 8h sliding expiry.</p>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">User</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Role</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">IP</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">User Agent</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-10">No sign-ins recorded yet.</TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`sessions-row-${r.id}`}>
                <TableCell className="font-mono-data text-xs whitespace-nowrap">{(r.at || "").slice(0, 19).replace("T", " ")}</TableCell>
                <TableCell className="text-sm"><div className="font-semibold">{r.name || r.email}</div><div className="text-[11px] text-muted-foreground">{r.email}</div></TableCell>
                <TableCell><StatusBadge text={(r.role || "").replaceAll("_", " ")} tone={r.role === "super_admin" ? "primary" : "neutral"} /></TableCell>
                <TableCell className="font-mono-data text-xs">{r.ip || "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground max-w-md truncate" title={r.user_agent}>{r.user_agent || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
