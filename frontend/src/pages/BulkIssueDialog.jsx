/**
 * Bulk Issue — issue many in-stock items to one project / site / department / employee.
 * Category-wise filtering; only items that actually have stock are listed.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DepartmentSelect } from "@/components/DepartmentSelect";
import { ProjectSelect, SiteSelect } from "@/components/MasterSelect";
import { Layers, Search } from "lucide-react";

const KIND_BY_CATEGORY = (cat = "") => {
  const c = cat.toLowerCase();
  if (c.includes("tool") || c.includes("tackle")) return "tool";
  if (c.includes("consum")) return "consumable";
  return "material";
};

export default function BulkIssueDialog({ open, onOpenChange, inventory, categories, employees, onDone }) {
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState({});   // item_id → qty
  const [hdr, setHdr] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPicked({}); setQ(""); setCategory("");
    setHdr({
      allocated_to_type: "project", project_code: "", project_id: "", site_code: "", site_id: "",
      department: "", employee_id: "", employee_name: "",
      issue_date: new Date().toISOString().slice(0, 10), expected_return_date: "",
      returnable: true, remarks: "",
    });
  }, [open]);

  const inStock = useMemo(
    () => (inventory || []).filter((i) => Number(i.quantity || 0) > 0),
    [inventory]);

  const catOptions = useMemo(() => {
    const counts = {};
    inStock.forEach((i) => { const c = i.category || "Uncategorised"; counts[c] = (counts[c] || 0) + 1; });
    const fromMaster = (categories || []).map((c) => c.name).filter((n) => counts[n]);
    const all = Array.from(new Set([...fromMaster, ...Object.keys(counts)])).sort();
    return all.map((name) => ({ name, count: counts[name] || 0 }));
  }, [inStock, categories]);

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return inStock.filter((i) =>
      (!category || (i.category || "Uncategorised") === category) &&
      (!s || [i.name, i.code, i.category].some((v) => (v || "").toLowerCase().includes(s))));
  }, [inStock, category, q]);

  const selectedCount = Object.keys(picked).length;
  const toggle = (item, on) => setPicked((p) => {
    const n = { ...p };
    if (on) n[item.id] = n[item.id] || 1; else delete n[item.id];
    return n;
  });

  const submit = async () => {
    const lines = Object.entries(picked).map(([id, qty]) => {
      const it = inStock.find((x) => x.id === id);
      return {
        item_id: id, item_name: it?.name || "", category: it?.category || "",
        kind: KIND_BY_CATEGORY(it?.category), quantity: Number(qty) || 0, unit: it?.unit || it?.uom || "Nos",
      };
    });
    if (!lines.length) { toast.error("Select at least one item"); return; }
    const bad = lines.find((l) => l.quantity <= 0);
    if (bad) { toast.error(`${bad.item_name}: quantity must be greater than 0`); return; }
    if (hdr.allocated_to_type === "project" && !hdr.project_code) { toast.error("Select the project"); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/allocations/bulk", { ...hdr, lines });
      toast.success(`${data.bulk_issue_no} · ${data.count} item(s) issued`);
      onOpenChange(false);
      onDone?.();
    } catch (e) { toast.error(e.response?.data?.detail || "Bulk issue failed"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm max-h-[92vh] overflow-y-auto" data-testid="bulk-issue-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Layers className="h-4 w-4" /> Bulk Issue to Project</DialogTitle>
          <DialogDescription className="text-xs">
            Pick a category, choose the items you want and issue them all to one project, site, department or employee in a single action.
            Only items that currently have stock are listed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Category + search */}
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Kind / Category</Label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}
                className="h-9 w-64 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="bulk-category">
                <option value="">All categories ({inStock.length} in stock)</option>
                {catOptions.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.count})</option>)}
              </select>
            </div>
            <div className="relative">
              <Label className="text-[10px] uppercase tracking-wider">Search item</Label>
              <Search className="absolute left-2.5 top-[34px] h-3.5 w-3.5 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Item name or code"
                className="h-9 w-64 rounded-sm mt-1 pl-8" data-testid="bulk-search" />
            </div>
            <div className="ml-auto text-xs text-muted-foreground" data-testid="bulk-selected-count">
              {selectedCount} item(s) selected · {rows.length} shown
            </div>
          </div>

          {/* Item picker */}
          <div className="border border-border rounded-sm max-h-72 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-10"></TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Category</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider text-right">In Stock</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider w-32">Issue Qty</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8 text-sm" data-testid="bulk-no-items">
                    No items in stock for this category.
                  </TableCell></TableRow>
                )}
                {rows.map((i) => {
                  const on = picked[i.id] != null;
                  return (
                    <TableRow key={i.id} className={on ? "bg-secondary/50" : "hover:bg-muted/30"} data-testid={`bulk-item-${i.id}`}>
                      <TableCell>
                        <input type="checkbox" checked={on} onChange={(e) => toggle(i, e.target.checked)}
                          className="h-4 w-4" data-testid={`bulk-check-${i.id}`} />
                      </TableCell>
                      <TableCell className="text-sm">
                        {i.name}
                        {i.code && <div className="text-[10px] text-muted-foreground font-mono-data">{i.code}</div>}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{i.category || "Uncategorised"}</TableCell>
                      <TableCell className="text-right font-mono-data text-xs">{i.quantity} {i.unit || i.uom || ""}</TableCell>
                      <TableCell>
                        <Input type="number" min="0" max={i.quantity} disabled={!on}
                          value={on ? picked[i.id] : ""}
                          onChange={(e) => setPicked((p) => ({ ...p, [i.id]: e.target.value }))}
                          className="h-8 rounded-sm" data-testid={`bulk-qty-${i.id}`} />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {/* Common allocation header */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 border-t border-border pt-3">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Allocated to</Label>
              <select value={hdr.allocated_to_type} onChange={(e) => setHdr({ ...hdr, allocated_to_type: e.target.value })}
                className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="bulk-to-type">
                <option value="project">Project</option>
                <option value="site">Site</option>
                <option value="department">Department</option>
                <option value="employee">Employee</option>
              </select>
            </div>
            {hdr.allocated_to_type === "project" && (
              <div className="md:col-span-2">
                <ProjectSelect label="Project Code" value={hdr.project_code}
                  onChange={(v, row) => setHdr({ ...hdr, project_code: v, project_id: row?.id || "" })}
                  testid="bulk-project" />
              </div>
            )}
            {hdr.allocated_to_type === "site" && (
              <div className="md:col-span-2">
                <SiteSelect label="Site Code" value={hdr.site_code}
                  onChange={(v, row) => setHdr({ ...hdr, site_code: v, site_id: row?.id || "" })} testid="bulk-site" />
              </div>
            )}
            {hdr.allocated_to_type === "department" && (
              <div className="md:col-span-2">
                <DepartmentSelect label="Department" value={hdr.department}
                  onChange={(v) => setHdr({ ...hdr, department: v })} testid="bulk-dept" />
              </div>
            )}
            {hdr.allocated_to_type === "employee" && (
              <div className="md:col-span-2">
                <Label className="text-[10px] uppercase tracking-wider">Employee</Label>
                <select value={hdr.employee_id} onChange={(e) => {
                  const f = (employees || []).find((x) => x.id === e.target.value);
                  setHdr({ ...hdr, employee_id: e.target.value, employee_name: f ? f.name : "" });
                }} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="bulk-emp">
                  <option value="">— pick —</option>
                  {(employees || []).map((x) => <option key={x.id} value={x.id}>{x.name} · {x.designation || ""}</option>)}
                </select>
              </div>
            )}
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Issue Date</Label>
              <Input type="date" value={hdr.issue_date} onChange={(e) => setHdr({ ...hdr, issue_date: e.target.value })}
                className="h-9 rounded-sm mt-1" data-testid="bulk-date" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Expected Return</Label>
              <Input type="date" value={hdr.expected_return_date} disabled={!hdr.returnable}
                onChange={(e) => setHdr({ ...hdr, expected_return_date: e.target.value })}
                className="h-9 rounded-sm mt-1" data-testid="bulk-return-date" />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-wider">
                <input type="checkbox" checked={hdr.returnable} onChange={(e) => setHdr({ ...hdr, returnable: e.target.checked })}
                  className="h-4 w-4" data-testid="bulk-returnable" />
                Returnable
              </label>
            </div>
            <div className="md:col-span-3">
              <Label className="text-[10px] uppercase tracking-wider">Remarks (applies to all lines)</Label>
              <Input value={hdr.remarks} onChange={(e) => setHdr({ ...hdr, remarks: e.target.value })}
                className="h-9 rounded-sm mt-1" data-testid="bulk-remarks" />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button className="rounded-sm" disabled={saving || !selectedCount} onClick={submit} data-testid="bulk-issue-save">
            {saving ? "Issuing…" : `Issue ${selectedCount || ""} Item(s)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
