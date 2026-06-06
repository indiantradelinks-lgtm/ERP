import { useEffect, useMemo, useState } from "react";
import {
  Trash2, Search, AlertTriangle, RefreshCcw, Archive, RotateCcw,
  ShieldAlert, Database, FileWarning, Filter, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { toast } from "sonner";

const TIER_TONE = {
  safe: "bg-emerald-100 text-emerald-900 border-emerald-300",
  caution: "bg-amber-100 text-amber-900 border-amber-300",
  dangerous: "bg-red-100 text-red-900 border-red-300",
};

const STATUS_OPTIONS = [
  "draft", "pending", "submitted", "approved", "rejected", "cancelled",
  "closed", "issued", "received", "open",
];

function previewLabel(row) {
  return (
    row.pr_number || row.po_number || row.quote_number || row.invoice_number ||
    row.bill_number || row.order_no || row.rfq_number || row.code || row.name || row.title || row.id || "—"
  );
}

function summaryFields(row) {
  const candidates = [
    ["Client", row.client || row.customer],
    ["Project", row.project_code || row.project_id],
    ["Vendor", row.vendor],
    ["Status", row.status],
    ["Amount", row.total ?? row.amount ?? row.value ?? row.contract_value],
    ["Date", row.created_at || row.date],
  ];
  return candidates.filter(([, v]) => v !== undefined && v !== null && v !== "");
}

export default function DataCleanup() {
  const [collections, setCollections] = useState([]);
  const [archiveCount, setArchiveCount] = useState(0);
  const [ttlDays, setTtlDays] = useState(30);
  const [selectedColl, setSelectedColl] = useState("");
  const [tab, setTab] = useState("browse");

  // Browse / filter state
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [olderThan, setOlderThan] = useState("");
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [skip] = useState(0);
  const [limit] = useState(100);

  // Orphans
  const [orphans, setOrphans] = useState([]);

  // Archive
  const [archive, setArchive] = useState([]);
  const [archFilterColl, setArchFilterColl] = useState("");

  // Delete dialog
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [reason, setReason] = useState("");
  const [softMode, setSoftMode] = useState(true); // true = archive (soft), false = hard purge

  // Detail view
  const [detail, setDetail] = useState(null);

  const loadCollections = async () => {
    try {
      const r = await api.get("/admin/data-cleanup/collections");
      setCollections(r.data.collections || []);
      setArchiveCount(r.data.archive_count || 0);
      setTtlDays(r.data.archive_ttl_days || 30);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load collection list");
    }
  };

  useEffect(() => { loadCollections(); }, []);

  const meta = useMemo(
    () => collections.find((c) => c.collection === selectedColl) || null,
    [collections, selectedColl]
  );

  const loadRows = async () => {
    if (!selectedColl) return;
    setLoading(true);
    try {
      const params = { skip, limit };
      if (q) params.q = q;
      if (status) params.status = status;
      if (olderThan) params.older_than_days = Number(olderThan);
      const r = await api.get(`/admin/data-cleanup/${selectedColl}`, { params });
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
      setSelected(new Set());
    } catch (e) {
      toast.error(e.response?.data?.detail || "Browse failed");
    } finally {
      setLoading(false);
    }
  };

  const loadOrphans = async () => {
    if (!selectedColl) return;
    setLoading(true);
    try {
      const r = await api.get(`/admin/data-cleanup/${selectedColl}/orphans`);
      setOrphans(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Orphan scan failed");
    } finally {
      setLoading(false);
    }
  };

  const loadArchive = async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (archFilterColl) params.collection = archFilterColl;
      const r = await api.get("/admin/data-cleanup/archive/list", { params });
      setArchive(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Archive list failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "browse") loadRows();
    else if (tab === "orphans") loadOrphans();
    else if (tab === "archive") loadArchive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedColl, tab, archFilterColl]);

  const toggleRow = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const toggleAll = (list) => {
    if (selected.size === list.length && list.length > 0) setSelected(new Set());
    else setSelected(new Set(list.map((r) => r.id)));
  };

  const openConfirm = () => {
    if (!selected.size) { toast.error("No rows selected"); return; }
    setConfirmText("");
    setReason("");
    setConfirmOpen(true);
  };

  const performDelete = async () => {
    if (confirmText !== "DELETE") {
      toast.error("Type DELETE exactly to confirm");
      return;
    }
    try {
      const ids = Array.from(selected);
      const r = await api.post(`/admin/data-cleanup/${selectedColl}/delete`, {
        ids, confirm: "DELETE", reason: reason || null, archive: softMode,
      });
      toast.success(
        softMode
          ? `Archived & deleted ${r.data.deleted} row(s) — recoverable for ${ttlDays} days`
          : `Permanently deleted ${r.data.deleted} row(s)`
      );
      setConfirmOpen(false);
      setSelected(new Set());
      // Refresh current view
      if (tab === "orphans") loadOrphans();
      else loadRows();
      loadCollections();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  const restoreArchive = async (archiveIds) => {
    if (!archiveIds.length) return;
    try {
      const r = await api.post("/admin/data-cleanup/archive/restore", { archive_ids: archiveIds });
      toast.success(`Restored ${r.data.restored} row(s)`);
      loadArchive();
      loadCollections();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Restore failed");
    }
  };

  const purgeArchive = async () => {
    if (!window.confirm(`Permanently purge ALL ${archive.length} archived rows? This cannot be undone.`)) return;
    try {
      const r = await api.delete("/admin/data-cleanup/archive/purge?older_than_days=0");
      toast.success(`Purged ${r.data.purged} archived row(s)`);
      loadArchive();
      loadCollections();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Purge failed");
    }
  };

  const activeList = tab === "orphans" ? orphans : rows;

  return (
    <div className="space-y-6" data-testid="data-cleanup-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5 flex items-center gap-2">
          <ShieldAlert className="h-3 w-3" /> Super Admin · Danger Zone
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Data Cleanup</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Identify garbage / test / mistaken records and remove them in a controlled, auditable way.
          Soft-deletes are kept in a 30-day archive and can be restored. Hard purges are permanent.
        </p>
      </div>

      {/* Top picker */}
      <div className="bg-card border border-border rounded-sm p-4 flex flex-wrap items-center gap-3">
        <Database className="h-4 w-4 text-primary" />
        <Label className="text-[11px] uppercase tracking-wider">Collection</Label>
        <Select value={selectedColl} onValueChange={setSelectedColl}>
          <SelectTrigger className="h-9 w-[320px] rounded-sm" data-testid="cleanup-collection-select">
            <SelectValue placeholder="Pick a collection to inspect…" />
          </SelectTrigger>
          <SelectContent>
            {collections.map((c) => (
              <SelectItem key={c.collection} value={c.collection}>
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm border ${TIER_TONE[c.tier]}`}>
                    {c.tier}
                  </span>
                  <span>{c.label}</span>
                  <span className="text-muted-foreground text-xs">({c.row_count})</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {meta && (
          <Badge variant="outline" className={`rounded-sm border ${TIER_TONE[meta.tier]}`}>
            {meta.tier.toUpperCase()} — {meta.row_count} rows
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <Archive className="h-3.5 w-3.5" />
          Archive: <span className="font-bold">{archiveCount}</span> rows (TTL {ttlDays}d)
          <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={loadCollections} data-testid="cleanup-refresh">
            <RefreshCcw className="h-3 w-3 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="browse" data-testid="cleanup-tab-browse">Browse & Delete</TabsTrigger>
          <TabsTrigger value="orphans" data-testid="cleanup-tab-orphans">Orphan Scan</TabsTrigger>
          <TabsTrigger value="archive" data-testid="cleanup-tab-archive">
            Archive ({archiveCount})
          </TabsTrigger>
        </TabsList>

        {/* ───────── Browse ───────── */}
        <TabsContent value="browse" className="space-y-3 mt-4">
          {!selectedColl ? (
            <EmptyState text="Pick a collection above to start browsing." />
          ) : (
            <>
              <div className="bg-card border border-border rounded-sm p-3 flex flex-wrap items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-9 h-9 rounded-sm" placeholder="Keyword (e.g. test, demo, name, code…)"
                    value={q} onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && loadRows()}
                    data-testid="cleanup-search"
                  />
                </div>
                <Select value={status || "__none"} onValueChange={(v) => setStatus(v === "__none" ? "" : v)}>
                  <SelectTrigger className="h-9 w-44 rounded-sm" data-testid="cleanup-status-filter">
                    <SelectValue placeholder="Status filter…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">Any status</SelectItem>
                    {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-1.5">
                  <Label className="text-[11px] uppercase tracking-wider">Older than</Label>
                  <Input
                    className="h-9 w-20 rounded-sm" type="number" min={0} placeholder="days"
                    value={olderThan} onChange={(e) => setOlderThan(e.target.value)}
                    data-testid="cleanup-age-filter"
                  />
                  <span className="text-[11px] text-muted-foreground">days</span>
                </div>
                <Button className="h-9 rounded-sm" onClick={loadRows} data-testid="cleanup-apply-filters">
                  Apply
                </Button>
                {(q || status || olderThan) && (
                  <Button variant="ghost" className="h-9 rounded-sm" onClick={() => { setQ(""); setStatus(""); setOlderThan(""); setTimeout(loadRows, 0); }}>
                    <X className="h-3 w-3 mr-1" /> Reset
                  </Button>
                )}
                <span className="ml-auto text-[11px] text-muted-foreground">
                  Showing {rows.length} of {total}
                </span>
              </div>

              {meta?.tier === "dangerous" && (
                <DangerCallout label={meta.label} />
              )}

              <RowsTable
                rows={activeList}
                loading={loading}
                selected={selected}
                onToggle={toggleRow}
                onToggleAll={() => toggleAll(activeList)}
                onDetail={setDetail}
              />

              <ActionBar
                count={selected.size}
                onDelete={openConfirm}
                softMode={softMode}
                setSoftMode={setSoftMode}
              />
            </>
          )}
        </TabsContent>

        {/* ───────── Orphans ───────── */}
        <TabsContent value="orphans" className="space-y-3 mt-4">
          {!selectedColl ? (
            <EmptyState text="Pick a collection above to scan for orphaned rows (parent reference is missing)." />
          ) : (
            <>
              <div className="bg-amber-50 border border-amber-300 text-amber-900 rounded-sm p-3 text-[12px] flex gap-2 items-start">
                <FileWarning className="h-4 w-4 mt-0.5" />
                <div>
                  Rows here reference a parent record (e.g. a deleted project) that no longer exists.
                  They are typically safe to delete after verification.
                </div>
              </div>
              <RowsTable
                rows={orphans}
                loading={loading}
                selected={selected}
                onToggle={toggleRow}
                onToggleAll={() => toggleAll(orphans)}
                onDetail={setDetail}
                extraColumn={{ header: "Missing Parent", render: (r) => (
                  <span className="text-[11px] font-mono text-amber-800">
                    {r._orphan_field} → {r._orphan_parent} ({String(r._orphan_value).slice(0, 8)}…)
                  </span>
                )}}
              />
              <ActionBar
                count={selected.size}
                onDelete={openConfirm}
                softMode={softMode}
                setSoftMode={setSoftMode}
              />
            </>
          )}
        </TabsContent>

        {/* ───────── Archive ───────── */}
        <TabsContent value="archive" className="space-y-3 mt-4">
          <div className="bg-card border border-border rounded-sm p-3 flex flex-wrap items-center gap-2">
            <Archive className="h-4 w-4 text-muted-foreground" />
            <Label className="text-[11px] uppercase tracking-wider">Filter by collection</Label>
            <Select value={archFilterColl || "__all"} onValueChange={(v) => setArchFilterColl(v === "__all" ? "" : v)}>
              <SelectTrigger className="h-9 w-56 rounded-sm" data-testid="archive-filter-coll">
                <SelectValue placeholder="All collections" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all">All collections</SelectItem>
                {collections.map((c) => <SelectItem key={c.collection} value={c.collection}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <span className="text-[11px] text-muted-foreground">{archive.length} archived row(s)</span>
            <Button variant="outline" className="ml-auto h-9 rounded-sm text-destructive border-destructive/40" onClick={purgeArchive} data-testid="archive-purge-all" disabled={!archive.length}>
              <Trash2 className="h-3 w-3 mr-1.5" /> Purge All
            </Button>
          </div>
          <ArchiveTable rows={archive} onRestore={(ids) => restoreArchive(ids)} onDetail={setDetail} />
        </TabsContent>
      </Tabs>

      {/* Confirm dialog */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2 text-red-700">
              <AlertTriangle className="h-5 w-5" /> Confirm Deletion
            </DialogTitle>
            <DialogDescription>
              You are about to {softMode ? "archive & delete" : "PERMANENTLY purge"}{" "}
              <span className="font-bold">{selected.size}</span> row(s) from{" "}
              <span className="font-mono">{meta?.label}</span>.
              {softMode
                ? ` These can be restored from the Archive tab within ${ttlDays} days.`
                : " There is NO undo. The records will not enter the archive."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex items-center gap-2 bg-secondary/40 border border-border rounded-sm p-2">
              <Checkbox
                id="soft-mode"
                checked={softMode}
                onCheckedChange={(v) => setSoftMode(!!v)}
                data-testid="cleanup-soft-toggle"
              />
              <Label htmlFor="soft-mode" className="text-xs cursor-pointer">
                Archive copy first (recommended). Uncheck to hard-purge with no recovery.
              </Label>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Reason (optional)</Label>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. seed/test data from initial setup"
                className="rounded-sm mt-1 min-h-[60px]"
                data-testid="cleanup-reason"
              />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider text-red-700">
                Type <span className="font-mono">DELETE</span> to confirm
              </Label>
              <Input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className="rounded-sm mt-1 h-9 font-mono"
                placeholder="DELETE"
                data-testid="cleanup-confirm-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              className="rounded-sm bg-red-700 hover:bg-red-800"
              onClick={performDelete}
              disabled={confirmText !== "DELETE"}
              data-testid="cleanup-confirm-delete"
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {softMode ? "Archive & Delete" : "Hard Purge"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-2xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Record Preview</DialogTitle>
            <DialogDescription className="font-mono text-[11px]">
              {detail?.id}
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto text-[11px] bg-secondary/40 rounded-sm p-3 border border-border">
            {detail ? JSON.stringify(detail, null, 2) : ""}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EmptyState({ text }) {
  return (
    <div className="bg-card border border-dashed border-border rounded-sm p-10 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function DangerCallout({ label }) {
  return (
    <div className="bg-red-50 border border-red-300 text-red-900 rounded-sm p-3 text-[12px] flex gap-2 items-start">
      <ShieldAlert className="h-4 w-4 mt-0.5" />
      <div>
        <span className="font-bold uppercase tracking-wider">Dangerous collection — {label}.</span>{" "}
        Deletions here may cascade to dependent records (PRs, POs, RA Bills, etc.). Use the Orphan
        Scan to validate downstream first, and prefer soft-delete (archive) unless you are absolutely sure.
      </div>
    </div>
  );
}

function RowsTable({ rows, loading, selected, onToggle, onToggleAll, onDetail, extraColumn }) {
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.id));
  return (
    <div className="bg-card border border-border rounded-sm overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <Checkbox checked={allChecked} onCheckedChange={onToggleAll} data-testid="cleanup-toggle-all" />
            </TableHead>
            <TableHead>Identifier</TableHead>
            <TableHead>Summary</TableHead>
            {extraColumn && <TableHead>{extraColumn.header}</TableHead>}
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading && (
            <TableRow><TableCell colSpan={extraColumn ? 5 : 4} className="text-center py-8 text-muted-foreground">Loading…</TableCell></TableRow>
          )}
          {!loading && rows.length === 0 && (
            <TableRow><TableCell colSpan={extraColumn ? 5 : 4} className="text-center py-10 text-muted-foreground">No records match.</TableCell></TableRow>
          )}
          {rows.map((r) => (
            <TableRow key={r.id} data-testid={`cleanup-row-${r.id}`}>
              <TableCell>
                <Checkbox
                  checked={selected.has(r.id)}
                  onCheckedChange={() => onToggle(r.id)}
                  data-testid={`cleanup-row-check-${r.id}`}
                />
              </TableCell>
              <TableCell className="font-mono text-[11px]">
                <div className="font-bold text-sm">{previewLabel(r)}</div>
                <div className="text-muted-foreground">{r.id}</div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1.5 max-w-md">
                  {summaryFields(r).slice(0, 4).map(([k, v], i) => (
                    <span key={i} className="text-[11px] bg-secondary/40 rounded-sm px-1.5 py-0.5 border border-border">
                      <span className="text-muted-foreground">{k}:</span> {String(v).slice(0, 30)}
                    </span>
                  ))}
                </div>
              </TableCell>
              {extraColumn && <TableCell>{extraColumn.render(r)}</TableCell>}
              <TableCell className="text-right">
                <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onDetail(r)} data-testid={`cleanup-preview-${r.id}`}>
                  Preview
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ActionBar({ count, onDelete, softMode, setSoftMode }) {
  return (
    <div className="sticky bottom-0 bg-card border border-border rounded-sm p-3 flex items-center gap-3 shadow-md">
      <span className="text-sm">
        <span className="font-bold">{count}</span> selected
      </span>
      <div className="flex items-center gap-2 ml-2">
        <Checkbox
          id="bar-soft"
          checked={softMode}
          onCheckedChange={(v) => setSoftMode(!!v)}
          data-testid="cleanup-soft-toggle-bar"
        />
        <Label htmlFor="bar-soft" className="text-xs cursor-pointer">
          Archive copy (soft delete)
        </Label>
      </div>
      <Button
        className="ml-auto rounded-sm bg-red-700 hover:bg-red-800"
        onClick={onDelete}
        disabled={count === 0}
        data-testid="cleanup-open-confirm"
      >
        <Trash2 className="h-4 w-4 mr-1.5" />
        {softMode ? "Archive & Delete" : "Hard Purge"} Selected
      </Button>
    </div>
  );
}

function ArchiveTable({ rows, onRestore, onDetail }) {
  const [sel, setSel] = useState(new Set());
  const toggle = (id) => {
    const n = new Set(sel);
    n.has(id) ? n.delete(id) : n.add(id);
    setSel(n);
  };
  const toggleAll = () => {
    if (sel.size === rows.length && rows.length > 0) setSel(new Set());
    else setSel(new Set(rows.map((r) => r.id)));
  };
  const allChecked = rows.length > 0 && rows.every((r) => sel.has(r.id));
  return (
    <div className="space-y-3">
      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <Checkbox checked={allChecked} onCheckedChange={toggleAll} data-testid="archive-toggle-all" />
              </TableHead>
              <TableHead>Collection</TableHead>
              <TableHead>Doc</TableHead>
              <TableHead>Deleted At</TableHead>
              <TableHead>By</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">Archive is empty.</TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`archive-row-${r.id}`}>
                <TableCell>
                  <Checkbox checked={sel.has(r.id)} onCheckedChange={() => toggle(r.id)} data-testid={`archive-check-${r.id}`} />
                </TableCell>
                <TableCell className="font-mono text-[11px]">{r.collection}</TableCell>
                <TableCell>
                  <div className="font-bold text-sm">{previewLabel(r.doc || {})}</div>
                  <div className="text-muted-foreground font-mono text-[10px]">{r.doc_id}</div>
                </TableCell>
                <TableCell className="text-[11px]">{(r.deleted_at || "").slice(0, 19).replace("T", " ")}</TableCell>
                <TableCell className="text-[11px]">{r.deleted_by}</TableCell>
                <TableCell className="text-[11px] max-w-xs truncate">{r.reason || "—"}</TableCell>
                <TableCell className="text-right">
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onDetail(r.doc)} data-testid={`archive-preview-${r.id}`}>
                      Preview
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => onRestore([r.id])} data-testid={`archive-restore-${r.id}`}>
                      <RotateCcw className="h-3 w-3 mr-1" /> Restore
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {sel.size > 0 && (
        <div className="sticky bottom-0 bg-card border border-border rounded-sm p-3 flex items-center gap-3">
          <span className="text-sm"><span className="font-bold">{sel.size}</span> selected</span>
          <Button className="ml-auto rounded-sm" onClick={() => { onRestore(Array.from(sel)); setSel(new Set()); }} data-testid="archive-bulk-restore">
            <RotateCcw className="h-4 w-4 mr-1.5" /> Restore Selected
          </Button>
        </div>
      )}
    </div>
  );
}
