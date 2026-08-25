import { useCallback, useEffect, useState } from "react";
import { ListPlus, Pencil, Trash2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const DEPTS = ["stores", "admin", "logistics", "hr"];

function OptionDialog({ kind, initial, expenseTypes, onClose, onSaved }) {
  const isNew = !initial.key;
  const [f, setF] = useState({ label: initial.label || "", dept: initial.dept || "admin",
    payment: initial.payment ?? true, stockable: initial.stockable ?? false,
    expense_type: initial.expense_type || "misc", account: initial.account || "5900", active: initial.active ?? true });
  const save = async () => {
    if (!f.label.trim()) { toast.error("Label required"); return; }
    try {
      if (isNew) await api.post(`/admin/request-options/${kind}`, f);
      else await api.put(`/admin/request-options/${kind}/${initial.key}`, f);
      toast.success("Saved — dropdowns updated for all users");
      onSaved();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md" data-testid="option-dialog">
        <DialogHeader><DialogTitle>{isNew ? "Add" : "Edit"} {kind === "request_type" ? "Request Type" : kind === "service_type" ? "Service Type" : "Expense Type"}{initial.key ? ` — ${initial.key}` : ""}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label className="text-[10px] uppercase tracking-wider">Label *</Label>
            <Input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} className="h-9 mt-1" data-testid="option-label" /></div>
          {kind === "request_type" ? (
            <>
              <div><Label className="text-[10px] uppercase tracking-wider">Routing Department</Label>
                <select value={f.dept} onChange={(e) => setF({ ...f, dept: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="option-dept">
                  {DEPTS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select></div>
              <div><Label className="text-[10px] uppercase tracking-wider">Default Expense Type</Label>
                <select value={f.expense_type} onChange={(e) => setF({ ...f, expense_type: e.target.value })}
                  className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid="option-expense-type">
                  {expenseTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select></div>
              <div className="flex gap-5 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={f.payment} onChange={(e) => setF({ ...f, payment: e.target.checked })} /> Payment request</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={f.stockable} onChange={(e) => setF({ ...f, stockable: e.target.checked })} /> Stockable (store check)</label>
              </div>
            </>
          ) : kind === "expense_type" ? (
            <div><Label className="text-[10px] uppercase tracking-wider">GL Account Code</Label>
              <Input value={f.account} onChange={(e) => setF({ ...f, account: e.target.value })} className="h-9 mt-1" data-testid="option-account" /></div>
          ) : null}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Active (visible in dropdowns)</label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} data-testid="option-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OptionsTable({ kind, rows, expenseTypes, onChanged }) {
  const [editing, setEditing] = useState(null);
  const remove = async (r) => {
    if (!window.confirm(r.builtin ? `Hide built-in option "${r.label}" from all dropdowns?` : `Delete "${r.label}"?`)) return;
    try {
      await api.delete(`/admin/request-options/${kind}/${r.key}`);
      toast.success(r.builtin ? "Hidden from dropdowns" : "Deleted");
      onChanged();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };
  const reactivate = async (r) => {
    try { await api.put(`/admin/request-options/${kind}/${r.key}`, { label: r.label, active: true }); onChanged(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center">
        <CardTitle className="text-base flex-1">{kind === "request_type" ? "Request Types (Routing)" : kind === "service_type" ? "Service Types" : "Expense Types"} <Badge variant="outline" className="ml-2">{rows.length}</Badge></CardTitle>
        <Button size="sm" onClick={() => setEditing({})} data-testid={`add-${kind}`}><ListPlus className="h-3.5 w-3.5 mr-1" /> Add</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Label</TableHead><TableHead>Key</TableHead>
            {kind === "request_type" ? <><TableHead>Routing Dept</TableHead><TableHead>Payment</TableHead><TableHead>Default Expense</TableHead></> : kind === "expense_type" ? <TableHead>GL Account</TableHead> : null}
            <TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.key} className={r.active === false ? "opacity-50" : ""} data-testid={`option-row-${kind}-${r.key}`}>
                <TableCell className="font-semibold text-sm">{r.label} {r.builtin && <Badge variant="outline" className="ml-1 text-[9px]">built-in</Badge>}</TableCell>
                <TableCell className="font-mono-data text-xs">{r.key}</TableCell>
                {kind === "request_type" ? (
                  <>
                    <TableCell className="text-xs uppercase">{r.dept}</TableCell>
                    <TableCell className="text-xs">{r.payment ? "Yes" : "No"}</TableCell>
                    <TableCell className="text-xs">{r.expense_type || "—"}</TableCell>
                  </>
                ) : kind === "expense_type" ? <TableCell className="font-mono-data text-xs">{r.account}</TableCell> : null}
                <TableCell><Badge variant="outline" className={`text-[10px] ${r.active === false ? "border-slate-300 text-slate-500" : "border-emerald-300 text-emerald-800 bg-emerald-50"}`}>{r.active === false ? "Hidden" : "Active"}</Badge></TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(r)} data-testid={`edit-${kind}-${r.key}`}><Pencil className="h-3 w-3" /></Button>
                  {r.active === false
                    ? <Button size="sm" variant="ghost" onClick={() => reactivate(r)} title="Re-activate" data-testid={`restore-${kind}-${r.key}`}><RotateCcw className="h-3 w-3" /></Button>
                    : <Button size="sm" variant="ghost" className="text-destructive" onClick={() => remove(r)} data-testid={`delete-${kind}-${r.key}`}><Trash2 className="h-3 w-3" /></Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      {editing !== null && <OptionDialog kind={kind} initial={editing} expenseTypes={expenseTypes} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />}
    </Card>
  );
}

export default function RequestOptions() {
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try { setData((await api.get("/admin/request-options")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="space-y-5" data-testid="request-options-page">
      <div>
        <h1 className="font-display font-black text-3xl tracking-tight">Request &amp; Expense Type Master</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Centrally manage the <b>Request Type (Routing)</b>, <b>Expense Type</b> and <b>Service Type</b> dropdowns used across the
          Service / Payment Request form and Billing reports. Changes reflect immediately for all users. Built-in options can be renamed or hidden; custom options can be added freely.
        </p>
      </div>
      {data && <OptionsTable kind="request_type" rows={data.request_types} expenseTypes={data.expense_types.filter((t) => t.active !== false)} onChanged={load} />}
      {data && <OptionsTable kind="expense_type" rows={data.expense_types} expenseTypes={[]} onChanged={load} />}
      {data && <OptionsTable kind="service_type" rows={data.service_types || []} expenseTypes={[]} onChanged={load} />}
    </div>
  );
}
