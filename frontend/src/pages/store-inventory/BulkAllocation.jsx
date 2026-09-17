/**
 * Category-wise Bulk Allocation — matrix (item rows × project columns)
 * Strict stock check · approval gate before stock deduction.
 */
import { useEffect, useMemo, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Send, CheckCircle2, XCircle, ChevronDown, ChevronRight, Boxes } from "lucide-react";
import { fmtD } from "@/lib/datetime";

const APPROVER_ROLES = ["super_admin", "general_manager", "director", "dept_head"];

const STATUS_TONE = {
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-rose-100 text-rose-700",
};

export function BulkAllocationView() {
  const [tab, setTab] = useState("new");
  return (
    <div data-testid="bulk-alloc-page">
      <div className="mb-4">
        <h1 className="font-display text-xl font-bold">Category-wise Bulk Allocation</h1>
        <p className="text-sm text-slate-500">Issue materials of a category to multiple running projects in one shot. Requires approval before stock deduction.</p>
      </div>
      <div className="flex gap-1 mb-4 border-b">
        {[["new", "New Allocation (Matrix)"], ["requests", "Requests & Approvals"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`bulk-alloc-tab-${k}`}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${tab === k ? "border-blue-600 font-medium text-blue-700" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
            {l}
          </button>
        ))}
      </div>
      {tab === "new" ? <MatrixForm onSubmitted={() => setTab("requests")} /> : <RequestsList />}
    </div>
  );
}

function MatrixForm({ onSubmitted }) {
  const [categories, setCategories] = useState([]);
  const [projects, setProjects] = useState([]);
  const [category, setCategory] = useState("");
  const [items, setItems] = useState([]);
  const [selectedProjects, setSelectedProjects] = useState([]);
  const [qty, setQty] = useState({}); // { itemId: { projectId: number } }
  const [remarks, setRemarks] = useState("");
  const [loadingItems, setLoadingItems] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/inv/categories").then((r) => setCategories((r.data || []).filter((c) => c.active !== false))).catch(() => {});
    api.get("/bulk-alloc/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!category) { setItems([]); return; }
    setLoadingItems(true);
    api.get("/bulk-alloc/items", { params: { category } })
      .then((r) => { setItems(r.data || []); setQty({}); })
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setLoadingItems(false));
  }, [category]);

  const toggleProject = (p) => {
    setSelectedProjects((prev) =>
      prev.some((x) => x.id === p.id) ? prev.filter((x) => x.id !== p.id) : [...prev, p]);
  };
  const selectAllProjects = () => setSelectedProjects(selectedProjects.length === projects.length ? [] : [...projects]);

  const setCell = (itemId, projectId, val) =>
    setQty((prev) => ({ ...prev, [itemId]: { ...(prev[itemId] || {}), [projectId]: val } }));

  const rowTotal = (itemId) => Object.values(qty[itemId] || {}).reduce((s, v) => s + (Number(v) || 0), 0);

  const lines = useMemo(() =>
    items
      .map((it) => {
        const allocations = selectedProjects
          .map((p) => ({ project_id: p.id, project_code: p.code, project_name: p.name, qty: Number(qty[it.id]?.[p.id]) || 0 }))
          .filter((a) => a.qty > 0);
        return allocations.length ? { item_id: it.id, item_name: it.name, unit: it.unit || it.uom || "Nos", allocations } : null;
      })
      .filter(Boolean),
    [items, selectedProjects, qty]);

  const overStock = items.filter((it) => rowTotal(it.id) > Number(it.quantity || 0));
  const grandTotal = lines.reduce((s, l) => s + l.allocations.reduce((x, a) => x + a.qty, 0), 0);

  const submit = async () => {
    if (!lines.length) return toast.error("Enter at least one quantity");
    if (overStock.length) return toast.error(`Over stock: ${overStock.map((i) => i.name).join(", ")}`);
    setSubmitting(true);
    try {
      const r = await api.post("/bulk-alloc/requests", { category, remarks, lines });
      toast.success(`Request ${r.data.request_no} submitted for approval`);
      setQty({}); setRemarks("");
      onSubmitted?.();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="text-xs uppercase tracking-wider">1 · Category</Label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} data-testid="bulk-alloc-category"
            className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1">
            <option value="">— select category —</option>
            {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <div className="flex items-center justify-between">
            <Label className="text-xs uppercase tracking-wider">2 · Running Projects ({selectedProjects.length} selected)</Label>
            <button onClick={selectAllProjects} className="text-xs text-blue-700 hover:underline" data-testid="bulk-alloc-select-all-projects">
              {selectedProjects.length === projects.length ? "Clear all" : "Select all"}
            </button>
          </div>
          <div className="mt-1 border rounded-sm p-2 max-h-28 overflow-y-auto grid grid-cols-1 sm:grid-cols-2 gap-1">
            {projects.length === 0 && <div className="text-xs text-slate-500 col-span-2">No active/planned projects found</div>}
            {projects.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-xs cursor-pointer" data-testid={`bulk-alloc-project-${p.code}`}>
                <input type="checkbox" checked={selectedProjects.some((x) => x.id === p.id)} onChange={() => toggleProject(p)} className="h-3.5 w-3.5" />
                <span className="truncate">{p.code} · {p.name} <span className="text-slate-400">({p.status})</span></span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {category && selectedProjects.length > 0 && (
        <div className="border rounded-sm overflow-x-auto">
          {loadingItems ? (
            <div className="p-6 text-center text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Loading items…</div>
          ) : items.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-500">No items in this category</div>
          ) : (
            <table className="w-full text-sm" data-testid="bulk-alloc-matrix">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="text-left px-3 py-2 sticky left-0 bg-slate-50">Item</th>
                  <th className="text-right px-2 py-2">Stock</th>
                  {selectedProjects.map((p) => <th key={p.id} className="text-center px-2 py-2 min-w-[90px]" title={p.name}>{p.code}</th>)}
                  <th className="text-right px-3 py-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const total = rowTotal(it.id);
                  const over = total > Number(it.quantity || 0);
                  return (
                    <tr key={it.id} className={`border-t ${over ? "bg-rose-50" : ""}`}>
                      <td className="px-3 py-1.5 sticky left-0 bg-inherit">
                        <div className="font-medium">{it.name}</div>
                        <div className="text-[10px] text-slate-400">{it.code} · {it.unit || it.uom}</div>
                      </td>
                      <td className="text-right px-2 font-mono-data">{Number(it.quantity || 0)}</td>
                      {selectedProjects.map((p) => (
                        <td key={p.id} className="px-1 py-1">
                          <Input type="number" min="0" value={qty[it.id]?.[p.id] ?? ""} placeholder="0"
                            onChange={(e) => setCell(it.id, p.id, e.target.value)}
                            data-testid={`bulk-alloc-qty-${it.code}-${p.code}`}
                            className="h-7 text-center rounded-sm px-1" />
                        </td>
                      ))}
                      <td className={`text-right px-3 font-mono-data font-semibold ${over ? "text-rose-600" : ""}`}>
                        {total || ""}{over && <span className="block text-[10px]">exceeds stock</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {category && selectedProjects.length > 0 && items.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end justify-between">
          <div className="flex-1 max-w-md">
            <Label className="text-xs uppercase tracking-wider">Remarks</Label>
            <Input value={remarks} onChange={(e) => setRemarks(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="bulk-alloc-remarks" />
          </div>
          <div className="flex items-center gap-3">
            <div className="text-sm text-slate-600">{lines.length} items · <span className="font-semibold">{grandTotal}</span> total qty</div>
            <Button onClick={submit} disabled={submitting || !lines.length || overStock.length > 0} className="rounded-sm" data-testid="bulk-alloc-submit">
              {submitting ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Send className="h-4 w-4 mr-1.5" />}
              Submit for Approval
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function RequestsList() {
  const { user } = useAuth();
  const canApprove = APPROVER_ROLES.includes(user?.role);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [rejectFor, setRejectFor] = useState(null);
  const [reason, setReason] = useState("");
  const [acting, setActing] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/bulk-alloc/requests").then((r) => setRows(r.data || [])).catch((e) => toast.error(apiErrorMessage(e))).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const approve = async (req) => {
    if (!window.confirm(`Approve ${req.request_no}? Stock will be deducted and ${req.total_qty} qty issued.`)) return;
    setActing(true);
    try {
      await api.post(`/bulk-alloc/requests/${req.id}/approve`);
      toast.success(`${req.request_no} approved — allocations issued`);
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setActing(false); }
  };

  const reject = async () => {
    setActing(true);
    try {
      await api.post(`/bulk-alloc/requests/${rejectFor.id}/reject`, { reason });
      toast.success(`${rejectFor.request_no} rejected`);
      setRejectFor(null); setReason("");
      load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setActing(false); }
  };

  if (loading) return <div className="p-6 text-center text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Loading…</div>;
  if (!rows.length) return <div className="p-10 text-center text-sm text-slate-500"><Boxes className="h-8 w-8 mx-auto mb-2 text-slate-300" />No bulk allocation requests yet</div>;

  return (
    <div className="border rounded-sm overflow-x-auto" data-testid="bulk-alloc-requests">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
          <tr>
            <th className="w-8"></th>
            <th className="text-left px-3 py-2">Request</th>
            <th className="text-left px-3 py-2">Category</th>
            <th className="text-right px-3 py-2">Items</th>
            <th className="text-right px-3 py-2">Total Qty</th>
            <th className="text-left px-3 py-2">Projects</th>
            <th className="text-left px-3 py-2">Requested by</th>
            <th className="text-left px-3 py-2">Status</th>
            <th className="text-right px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <RequestRow key={r.id} r={r} expanded={expanded === r.id}
              onToggle={() => setExpanded(expanded === r.id ? null : r.id)}
              canApprove={canApprove} acting={acting}
              onApprove={() => approve(r)} onReject={() => setRejectFor(r)} />
          ))}
        </tbody>
      </table>

      <Dialog open={!!rejectFor} onOpenChange={(o) => !o && setRejectFor(null)}>
        <DialogContent className="max-w-sm rounded-sm">
          <DialogHeader><DialogTitle>Reject {rejectFor?.request_no}</DialogTitle></DialogHeader>
          <Label className="text-xs uppercase tracking-wider">Reason</Label>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-9 rounded-sm" data-testid="bulk-alloc-reject-reason" />
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setRejectFor(null)}>Cancel</Button>
            <Button variant="destructive" className="rounded-sm" onClick={reject} disabled={acting} data-testid="bulk-alloc-reject-confirm">Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RequestRow({ r, expanded, onToggle, canApprove, acting, onApprove, onReject }) {
  return (
    <>
      <tr className="border-t hover:bg-slate-50" data-testid={`bulk-alloc-row-${r.request_no}`}>
        <td className="px-2 text-center">
          <button onClick={onToggle} data-testid={`bulk-alloc-expand-${r.request_no}`}>
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </td>
        <td className="px-3 py-2 font-mono-data">{r.request_no}<div className="text-[10px] text-slate-400">{fmtD(r.created_at)}</div></td>
        <td className="px-3">{r.category}</td>
        <td className="px-3 text-right">{r.total_items}</td>
        <td className="px-3 text-right font-semibold">{r.total_qty}</td>
        <td className="px-3">{(r.project_ids || []).length}</td>
        <td className="px-3">{r.requested_by}</td>
        <td className="px-3">
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${STATUS_TONE[r.status] || "bg-slate-100"}`}>
            {(r.status || "").replaceAll("_", " ")}
          </span>
          {r.status !== "pending_approval" && r.decided_by && (
            <div className="text-[10px] text-slate-400 mt-0.5">by {r.decided_by}{r.decision_reason ? ` · ${r.decision_reason}` : ""}</div>
          )}
        </td>
        <td className="px-3 text-right">
          {r.status === "pending_approval" && canApprove && (
            <div className="inline-flex gap-1">
              <Button size="sm" className="h-7 rounded-sm bg-emerald-600 hover:bg-emerald-700" disabled={acting} onClick={onApprove} data-testid={`bulk-alloc-approve-${r.request_no}`}>
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Approve
              </Button>
              <Button size="sm" variant="outline" className="h-7 rounded-sm text-rose-600" disabled={acting} onClick={onReject} data-testid={`bulk-alloc-reject-${r.request_no}`}>
                <XCircle className="h-3.5 w-3.5 mr-1" /> Reject
              </Button>
            </div>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-t bg-slate-50/60">
          <td></td>
          <td colSpan={8} className="px-3 py-2">
            <table className="w-full text-xs">
              <thead className="text-slate-500 uppercase tracking-wider">
                <tr><th className="text-left py-1">Item</th><th className="text-left">Project</th><th className="text-right">Qty</th><th className="text-left pl-3">Unit</th></tr>
              </thead>
              <tbody>
                {(r.lines || []).flatMap((l) => (l.allocations || []).map((a, i) => (
                  <tr key={`${l.item_id}-${a.project_id}`} className="border-t border-slate-200">
                    <td className="py-1">{i === 0 ? l.item_name : ""}</td>
                    <td>{a.project_code || a.project_name}</td>
                    <td className="text-right font-mono-data">{a.qty}</td>
                    <td className="pl-3">{l.unit}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}
