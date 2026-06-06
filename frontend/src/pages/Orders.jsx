import { useEffect, useState } from "react";
import { Search, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Orders() {
  const { can } = useAuth();
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [deleteFor, setDeleteFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.get("/orders").then((r) => setRows(r.data)).catch((e) => toast.error(e.response?.data?.detail || "Failed"));

  useEffect(() => { load(); }, []);

  const canDelete = can?.("quotations", "delete") ?? true;

  const filtered = rows.filter((r) =>
    !q || [r.order_no, r.customer, r.enquiry_no, r.project_code].some((v) => String(v ?? "").toLowerCase().includes(q.toLowerCase()))
  );

  const confirmDelete = async () => {
    if (!deleteFor) return;
    setBusy(true);
    try {
      await api.delete(`/orders/${deleteFor.id}`);
      toast.success(`Order ${deleteFor.order_no} deleted`);
      setDeleteFor(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="orders-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Sales · Orders</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Sales Orders</h1>
        <p className="text-sm text-muted-foreground mt-1">Confirmed orders auto-generated from Won enquiries (ORD-YYYY-####).</p>
      </div>
      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="orders-search" />
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">Order #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">From Enquiry</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Customer</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Customer PO</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Contract Value</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Project</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                {canDelete && <TableHead className="text-[10px] uppercase tracking-wider text-right">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={canDelete ? 8 : 7} className="text-center text-sm text-muted-foreground py-10">No orders yet.</TableCell></TableRow>
              )}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`order-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm font-semibold">{r.order_no}</TableCell>
                  <TableCell className="font-mono-data text-xs text-muted-foreground">{r.enquiry_no}</TableCell>
                  <TableCell className="text-sm">{r.customer}</TableCell>
                  <TableCell className="text-sm font-mono-data">{r.customer_po || "—"}</TableCell>
                  <TableCell className="text-sm tabular">₹ {Number(r.contract_value || 0).toLocaleString("en-IN")}</TableCell>
                  <TableCell>{r.project_code ? <StatusBadge text={r.project_code} tone="primary" /> : "—"}</TableCell>
                  <TableCell><StatusBadge text={r.status || "active"} tone="success" /></TableCell>
                  {canDelete && (
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        onClick={() => setDeleteFor(r)}
                        title="Delete this order"
                        data-testid={`order-delete-${r.id}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={!!deleteFor} onOpenChange={(o) => !o && setDeleteFor(null)}>
        <DialogContent data-testid="order-delete-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Delete Sales Order?</DialogTitle>
            <DialogDescription>
              This will permanently remove order <code className="font-mono bg-muted/40 px-1 rounded-sm">{deleteFor?.order_no}</code> for <strong>{deleteFor?.customer}</strong>. The action is audit-logged but cannot be undone from the UI.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteFor(null)} data-testid="order-delete-cancel">Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={busy} data-testid="order-delete-confirm">
              <Trash2 className="h-3.5 w-3.5 mr-1.5" /> {busy ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
