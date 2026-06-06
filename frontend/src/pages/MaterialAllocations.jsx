import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Boxes, Trash2, Undo2, ArrowUpRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { DepartmentSelect } from "@/components/DepartmentSelect";

const STATUS_TONE = { issued: "warning", returned: "success", partially_returned: "info", written_off: "danger" };
const KIND_TONE = { material: "primary", tool: "info", consumable: "warning", asset: "success" };

const blankForm = () => ({
  kind: "material",
  item_id: "",
  item_name: "",
  quantity: 1,
  unit: "Nos",
  allocated_to_type: "project",
  project_code: "",
  site_code: "",
  department: "",
  employee_id: "",
  employee_name: "",
  issue_date: new Date().toISOString().slice(0, 10),
  expected_return_date: "",
  returnable: true,
  condition_on_issue: "",
  remarks: "",
});

export default function MaterialAllocations() {
  const [rows, setRows] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [assets, setAssets] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [returnDlg, setReturnDlg] = useState(null);
  const [form, setForm] = useState(blankForm());

  const load = async () => {
    try {
      const url = statusFilter ? `/allocations?status=${statusFilter}` : "/allocations";
      const [a, inv, as, emp] = await Promise.all([
        api.get(url),
        api.get("/inventory").catch(() => ({ data: [] })),
        api.get("/assets").catch(() => ({ data: [] })),
        api.get("/employees").catch(() => ({ data: [] })),
      ]);
      setRows(a.data || []);
      setInventory(inv.data || []);
      setAssets(as.data || []);
      setEmployees(emp.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const save = async () => {
    if (!form.item_name) { toast.error("Item name required"); return; }
    if (form.quantity <= 0) { toast.error("Quantity must be > 0"); return; }
    try {
      const payload = { ...form, quantity: Number(form.quantity) || 0 };
      const { data } = await api.post("/allocations", payload);
      toast.success(`${data.allocation_no} issued`);
      setOpen(false);
      setForm(blankForm());
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Issue failed"); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.allocation_no}? Stock will be reversed.`)) return;
    try { await api.delete(`/allocations/${r.id}`); toast.success("Reversed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) =>
      [r.allocation_no, r.item_name, r.kind, r.project_code, r.site_code, r.employee_name, r.department, r.status]
        .some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="allocations-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Boxes className="h-3 w-3" /> Procurement · Material & Asset Allocation
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Material / Asset Allocations</h1>
        <p className="text-sm text-muted-foreground mt-1">Issue materials, tools, consumables and assets to projects, sites, departments or employees. Track returns with full audit.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search ALC #, item, project, employee…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="alloc-search" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-xs" data-testid="alloc-status-filter">
            <option value="">All statuses</option>
            <option value="issued">Issued</option>
            <option value="partially_returned">Partially returned</option>
            <option value="returned">Returned</option>
            <option value="written_off">Written off</option>
          </select>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => setOpen(true)} data-testid="alloc-add">
              <Plus className="h-4 w-4 mr-1" /> Issue
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">ALC #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Kind</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Qty · Returned</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Allocated to</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Issue · Return Due</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-right w-44">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10 text-sm">No allocations yet.</TableCell></TableRow>}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`alloc-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm font-bold">{r.allocation_no}</TableCell>
                  <TableCell><StatusBadge text={r.kind} tone={KIND_TONE[r.kind] || "neutral"} /></TableCell>
                  <TableCell className="text-sm">
                    {r.item_name}
                    <div className="text-[10px] text-muted-foreground">{r.unit}</div>
                  </TableCell>
                  <TableCell className="font-mono-data text-xs tabular">
                    {r.quantity}
                    {r.returnable && <span className="text-success"> · {r.returned_qty || 0} ret.</span>}
                    {!r.returnable && <span className="text-muted-foreground ml-1"> (non-ret)</span>}
                  </TableCell>
                  <TableCell className="text-xs">
                    <span className="font-semibold capitalize">{r.allocated_to_type}</span><br />
                    <span className="text-muted-foreground">{r.employee_name || r.project_code || r.site_code || r.department || "—"}</span>
                  </TableCell>
                  <TableCell className="font-mono-data text-[10px]">
                    {r.issue_date}{r.expected_return_date && <div>↩ {r.expected_return_date}</div>}
                  </TableCell>
                  <TableCell><StatusBadge text={(r.status || "").replaceAll("_", " ")} tone={STATUS_TONE[r.status] || "neutral"} /></TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      {r.returnable && r.status !== "returned" && r.status !== "written_off" && (
                        <Button size="sm" className="h-7 rounded-sm" onClick={() => setReturnDlg(r)} data-testid={`alloc-return-${r.id}`}>
                          <Undo2 className="h-3 w-3 mr-1" /> Return
                        </Button>
                      )}
                      {r.status === "issued" && (
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => remove(r)} data-testid={`alloc-delete-${r.id}`}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Issue dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl rounded-sm max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Issue Material / Asset</DialogTitle>
            <DialogDescription className="sr-only">Allocate stock or asset to a project, site, department or employee.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 py-2">
            <div>
              <Label className="text-xs uppercase tracking-wider">Kind</Label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, item_id: "", item_name: "" })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="alloc-kind">
                <option value="material">Material</option>
                <option value="tool">Tool</option>
                <option value="consumable">Consumable</option>
                <option value="asset">Asset</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs uppercase tracking-wider">Pick from {form.kind === "asset" ? "Asset Master" : "Inventory"} (optional)</Label>
              <select
                value={form.item_id}
                onChange={(e) => {
                  const id = e.target.value;
                  const list = form.kind === "asset" ? assets : inventory;
                  const found = list.find((x) => x.id === id);
                  setForm({ ...form, item_id: id, item_name: found ? (found.name || found.item_name || "") : form.item_name, unit: found?.unit || form.unit });
                }}
                className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="alloc-item-select">
                <option value="">— free text below —</option>
                {(form.kind === "asset" ? assets : inventory).map((x) => (
                  <option key={x.id} value={x.id}>{x.name || x.item_name} {x.quantity != null ? `(stock ${x.quantity} ${x.unit || ""})` : ""}</option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Item Name *</Label>
              <Input value={form.item_name} onChange={(e) => setForm({ ...form, item_name: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-item-name" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Quantity</Label>
              <Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-qty" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Unit</Label>
              <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-unit" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Allocated to</Label>
              <select value={form.allocated_to_type} onChange={(e) => setForm({ ...form, allocated_to_type: e.target.value })} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="alloc-to-type">
                <option value="project">Project</option>
                <option value="site">Site</option>
                <option value="department">Department</option>
                <option value="employee">Employee</option>
              </select>
            </div>
            {form.allocated_to_type === "project" && (
              <div className="md:col-span-2">
                <Label className="text-xs uppercase tracking-wider">Project Code</Label>
                <Input value={form.project_code} onChange={(e) => setForm({ ...form, project_code: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-project" />
              </div>
            )}
            {form.allocated_to_type === "site" && (
              <div className="md:col-span-2">
                <Label className="text-xs uppercase tracking-wider">Site Code</Label>
                <Input value={form.site_code} onChange={(e) => setForm({ ...form, site_code: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-site" />
              </div>
            )}
            {form.allocated_to_type === "department" && (
              <div className="md:col-span-2">
                <DepartmentSelect label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} testid="alloc-dept" />
              </div>
            )}
            {form.allocated_to_type === "employee" && (
              <div className="md:col-span-2">
                <Label className="text-xs uppercase tracking-wider">Employee</Label>
                <select value={form.employee_id} onChange={(e) => {
                  const id = e.target.value;
                  const f = employees.find((x) => x.id === id);
                  setForm({ ...form, employee_id: id, employee_name: f ? f.name : "" });
                }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="alloc-emp">
                  <option value="">— pick —</option>
                  {employees.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.designation || ""}</option>)}
                </select>
              </div>
            )}
            <div>
              <Label className="text-xs uppercase tracking-wider">Issue Date</Label>
              <Input type="date" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-date" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Expected Return</Label>
              <Input type="date" value={form.expected_return_date} onChange={(e) => setForm({ ...form, expected_return_date: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-return-date" disabled={!form.returnable} />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-xs uppercase tracking-wider">
                <input type="checkbox" checked={form.returnable} onChange={(e) => setForm({ ...form, returnable: e.target.checked })} className="h-4 w-4" data-testid="alloc-returnable" />
                Returnable
              </label>
            </div>
            <div className="md:col-span-3">
              <Label className="text-xs uppercase tracking-wider">Condition on Issue</Label>
              <Input value={form.condition_on_issue} onChange={(e) => setForm({ ...form, condition_on_issue: e.target.value })} className="h-9 rounded-sm mt-1" data-testid="alloc-condition" />
            </div>
            <div className="md:col-span-3">
              <Label className="text-xs uppercase tracking-wider">Remarks</Label>
              <textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} className="w-full min-h-[50px] rounded-sm border border-input bg-background p-2 text-sm mt-1" data-testid="alloc-remarks" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="alloc-save"><ArrowUpRight className="h-3.5 w-3.5 mr-1" /> Issue</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Return dialog */}
      {returnDlg && <ReturnDialog alloc={returnDlg} onClose={() => { setReturnDlg(null); load(); }} />}
    </div>
  );
}

function ReturnDialog({ alloc, onClose }) {
  const remaining = Number(alloc.quantity || 0) - Number(alloc.returned_qty || 0);
  const [qty, setQty] = useState(remaining);
  const [cond, setCond] = useState("");
  const [remarks, setRemarks] = useState("");

  const submit = async () => {
    try {
      await api.post(`/allocations/${alloc.id}/return`, { returned_qty: Number(qty) || 0, condition_on_return: cond, remarks });
      toast.success("Return recorded");
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Return failed"); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">Return · {alloc.allocation_no}</DialogTitle>
          <DialogDescription className="sr-only">Record returned quantity and condition.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="text-xs text-muted-foreground">Outstanding: <span className="font-bold text-foreground">{remaining} {alloc.unit}</span></div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Returned Qty</Label>
            <Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="return-qty" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Condition on Return</Label>
            <Input value={cond} onChange={(e) => setCond(e.target.value)} className="h-9 rounded-sm mt-1" placeholder="e.g., good / damaged / lost" data-testid="return-condition" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Remarks</Label>
            <Input value={remarks} onChange={(e) => setRemarks(e.target.value)} className="h-9 rounded-sm mt-1" data-testid="return-remarks" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={submit} data-testid="return-save"><Undo2 className="h-3.5 w-3.5 mr-1" /> Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
