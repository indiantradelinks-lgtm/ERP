import { useEffect, useState } from "react";
import { CopyX, Search, MousePointerClick, KeySquare } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import { api } from "@/lib/api";

const KIND = {
  business_key: { label: "Duplicate record", tone: "danger" },
  rapid_resubmit: { label: "Repeat submit", tone: "warning" },
};

export default function DuplicateBlocks() {
  const [filter, setFilter] = useState({ kind: "", module: "" });
  const [summary, setSummary] = useState({ total: 0, last_7_days: 0, business_key: 0, rapid_resubmit: 0, by_module: [] });
  const { rows, pagination, search, setSearch } = usePagedList("/admin/duplicates/blocks", filter, {
    errorLabel: "duplicate attempts", defaultSort: { by: "at", dir: "desc" },
  });

  useEffect(() => {
    api.get("/admin/duplicates/blocks/summary").then((r) => setSummary(r.data)).catch(() => {});
  }, [rows.length]);

  const tiles = [
    { label: "Blocked — all time", value: summary.total, icon: CopyX },
    { label: "Last 7 days", value: summary.last_7_days, icon: Search },
    { label: "Duplicate records", value: summary.business_key, icon: KeySquare },
    { label: "Repeat submits", value: summary.rapid_resubmit, icon: MousePointerClick },
  ];

  return (
    <div className="space-y-6" data-testid="admin-duplicate-blocks">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Super Admin · Data Integrity</div>
        <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
          <CopyX className="h-7 w-7 text-primary" /> Blocked Duplicates
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Every duplicate the ERP refused to save — repeated clicks, resubmits after an error, and entries that matched a record already in the system.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="bg-card border border-border rounded-sm p-4" data-testid={`dup-tile-${t.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{t.label}</div>
              <t.icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="font-display font-black text-2xl mt-1">{(t.value || 0).toLocaleString("en-IN")}</div>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search user / module / record…" value={search}
                   onChange={(e) => setSearch(e.target.value)} data-testid="dup-search" />
          </div>
          <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm" value={filter.kind}
                  onChange={(e) => setFilter({ ...filter, kind: e.target.value })} data-testid="dup-filter-kind">
            <option value="">All types</option>
            <option value="business_key">Duplicate record</option>
            <option value="rapid_resubmit">Repeat submit</option>
          </select>
          <Input className="h-9 rounded-sm w-56" placeholder="Filter module" value={filter.module}
                 onChange={(e) => setFilter({ ...filter, module: e.target.value })} data-testid="dup-filter-module" />
          <div className="ml-auto text-xs text-muted-foreground">
            <span className="text-foreground font-semibold">{pagination.total.toLocaleString("en-IN")}</span> attempts blocked
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">User</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Type</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Module</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Matched record</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Reason shown to user</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-10">
                  No duplicate attempts recorded — nothing has been blocked yet.
                </TableCell></TableRow>
              )}
              {rows.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`dup-row-${r.id}`}>
                  <TableCell className="font-mono-data text-xs whitespace-nowrap">{(r.at || "").slice(0, 19).replace("T", " ")}</TableCell>
                  <TableCell className="text-sm">
                    <div className="font-semibold">{r.user_name || "—"}</div>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{(r.user_role || "").replaceAll("_", " ")}</div>
                  </TableCell>
                  <TableCell><StatusBadge text={(KIND[r.kind] || {}).label || r.kind} tone={(KIND[r.kind] || {}).tone || "neutral"} /></TableCell>
                  <TableCell className="font-mono-data text-xs">{r.module || "—"}</TableCell>
                  <TableCell className="font-mono-data text-xs font-semibold">{r.existing_no || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-xl">{r.message}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="px-4 py-2 border-t border-border"><TablePager pagination={pagination} testidPrefix="dup" /></div>
      </div>
    </div>
  );
}
