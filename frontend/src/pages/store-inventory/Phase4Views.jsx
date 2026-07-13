/**
 * Store & Inventory · Phase 4 views
 * ==================================
 * PPE Issue + Expiry / Damage-Loss / Scrap / Employee Clearance /
 * Recovery / Transit Exceptions / Tool register.
 * All endpoints under /api/inv4/*.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, RefreshCcw, CheckCircle2, XCircle } from "lucide-react";
import { ProjectSelect } from "@/components/MasterSelect";

const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const today = () => new Date().toISOString().slice(0, 10);

/* ════════════════ Generic small list+create card ════════════════ */
function ReportCard({ title, endpoint, columns, testid, summary }) {
  const [data, setData] = useState({ rows: [] });
  const load = async () => {
    try { const r = await api.get(endpoint); setData(Array.isArray(r.data) ? { rows: r.data } : r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Card data-testid={testid}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title} <span className="text-xs text-slate-400">({(data.rows || []).length}{summary ? ` · ${summary(data)}` : ""})</span></CardTitle>
        <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              {columns.map(c => <th key={c.key} className={`text-${c.align || "left"} px-2 py-1`}>{c.label}</th>)}
            </tr></thead>
            <tbody>
              {(data.rows || []).map((r, i) => (
                <tr key={r.id || r.allocation_id || i} className="border-t hover:bg-slate-50">
                  {columns.map(c => <td key={c.key} className={`text-${c.align || "left"} px-2 py-1 ${c.cls || ""}`}>{c.render ? c.render(r) : r[c.key] ?? "—"}</td>)}
                </tr>
              ))}
              {!data.rows?.length && <tr><td colSpan={columns.length} className="text-center py-6 text-slate-400">No records.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ════════════════ 1. PPE Issue ════════════════ */
export function PPEIssueView() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    employee_id: "", employee_name: "", project_code: "", site_code: "",
    item_id: "", quantity: 1, size: "", issue_type: "new",
    expiry_date: "", inspection_due_date: "", remarks: "",
  });

  const load = async () => {
    try {
      const [r, i, e] = await Promise.all([
        api.get("/inv4/ppe-issues"),
        api.get("/inventory"),
        api.get("/employees").catch(() => ({ data: [] })),
      ]);
      setRows(r.data); setItems(i.data); setEmployees(e.data);
    } catch (er) { toast.error(er.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.employee_id || !form.item_id || Number(form.quantity) <= 0) {
      toast.error("Employee, item and qty are required"); return;
    }
    setBusy(true);
    try {
      const r = await api.post("/inv4/ppe-issues", {
        ...form,
        quantity: Number(form.quantity),
        expiry_date: form.expiry_date || null,
        inspection_due_date: form.inspection_due_date || null,
      });
      toast.success(`PPE issue ${r.data.issue_no} created`);
      setShowForm(false);
      setForm({ employee_id: "", employee_name: "", project_code: "", site_code: "",
                 item_id: "", quantity: 1, size: "", issue_type: "new",
                 expiry_date: "", inspection_due_date: "", remarks: "" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Issue failed"); }
    finally { setBusy(false); }
  };

  return (
    <Card data-testid="ppe-issue-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">PPE Issue Register ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="ppe-issue-new"><Plus className="h-3.5 w-3.5 mr-1" />Issue PPE</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="ppe-issue-form">
            <div className="grid grid-cols-3 gap-2">
              <div><Label className="text-xs">Employee *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.employee_id}
                        onChange={e => { const emp = employees.find(x => x.id === e.target.value); setForm({ ...form, employee_id: e.target.value, employee_name: emp?.name || "" }); }} data-testid="ppe-emp">
                  <option value="">—</option>
                  {employees.map(emp => <option key={emp.id} value={emp.id}>{emp.code} · {emp.name}</option>)}
                </select></div>
              <div><Label className="text-xs">PPE Item *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.item_id} onChange={e => setForm({ ...form, item_id: e.target.value })} data-testid="ppe-item">
                  <option value="">—</option>{items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name} (avail {it.quantity})</option>)}
                </select></div>
              <div><Label className="text-xs">Qty</Label><Input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} data-testid="ppe-qty" /></div>
              <div><Label className="text-xs">Size</Label><Input value={form.size} onChange={e => setForm({ ...form, size: e.target.value })} /></div>
              <div><Label className="text-xs">Type</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.issue_type} onChange={e => setForm({ ...form, issue_type: e.target.value })}>
                  <option value="new">New</option><option value="replacement">Replacement</option>
                  <option value="returnable">Returnable</option><option value="non_returnable">Non-returnable</option>
                </select></div>
              <div><Label className="text-xs">Project Code</Label><ProjectSelect label="" valueKey="code" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} /></div>
              <div><Label className="text-xs">Expiry Date</Label><Input type="date" value={form.expiry_date} onChange={e => setForm({ ...form, expiry_date: e.target.value })} /></div>
              <div><Label className="text-xs">Inspection Due</Label><Input type="date" value={form.inspection_due_date} onChange={e => setForm({ ...form, inspection_due_date: e.target.value })} /></div>
              <div><Label className="text-xs">Remarks</Label><Input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} /></div>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="ppe-save">Issue</Button>
            </div>
          </div>
        )}
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">Issue No</th><th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">Employee</th><th className="text-left px-2 py-1">Item</th>
              <th className="text-right px-2 py-1">Qty</th><th className="text-left px-2 py-1">Type</th>
              <th className="text-left px-2 py-1">Expiry</th><th className="text-right px-2 py-1">Value</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.issue_no}</td>
                  <td className="px-2 py-1 font-mono">{r.issue_date}</td>
                  <td className="px-2 py-1">{r.employee_name || r.employee_id}</td>
                  <td className="px-2 py-1">{r.item_name}{r.size && <span className="text-[10px] text-slate-500"> · {r.size}</span>}</td>
                  <td className="px-2 py-1 text-right">{r.quantity}</td>
                  <td className="px-2 py-1"><span className="px-1 py-0.5 rounded text-[10px] bg-slate-100">{r.issue_type}</span></td>
                  <td className="px-2 py-1 font-mono">{r.expiry_date || "—"}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.value)}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No PPE issues yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

export const PPEExpiryRegisterView = () => (
  <ReportCard
    title="PPE Expiry Register" endpoint="/inv4/ppe-expiry-register?within_days=90" testid="ppe-expiry-view"
    summary={d => `as of ${d.as_of}`}
    columns={[
      { key: "issue_no", label: "Issue No", cls: "font-mono" },
      { key: "employee_name", label: "Employee" },
      { key: "item_name", label: "Item" },
      { key: "expiry_date", label: "Expiry", cls: "font-mono" },
      { key: "days_to_expiry", label: "Days", align: "right",
        render: r => <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.expired ? "bg-rose-100 text-rose-800" : (r.days_to_expiry || 0) < 30 ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{r.expired ? "EXPIRED" : `${r.days_to_expiry ?? "—"}d`}</span> },
      { key: "issue_type", label: "Type" },
    ]} />
);

/* ════════════════ Damage / Loss ════════════════ */
export function DamageLossView() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    date: today(), item_id: "", quantity: 1, reason: "", recoverable: false,
    recovery_amount: 0, project_code: "", employee_id: "", employee_name: "",
    attachment_url: "", remarks: "", kind: "damage",
  });

  const load = async () => {
    try {
      const [r, i] = await Promise.all([api.get("/inv4/damage-loss"), api.get("/inventory")]);
      setRows(r.data); setItems(i.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.item_id || !form.reason.trim() || !form.attachment_url.trim()) {
      toast.error("Item, reason and attachment URL are required"); return;
    }
    if (Number(form.quantity) <= 0) { toast.error("Quantity must be > 0"); return; }
    setBusy(true);
    try {
      const r = await api.post("/inv4/damage-loss", {
        ...form, quantity: Number(form.quantity),
        recovery_amount: Number(form.recovery_amount) || 0,
      });
      toast.success(`${r.data.dl_number} submitted${r.data.needs_finance_approval ? " — needs Finance approval" : ""}`);
      setShowForm(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const approve = async (id) => {
    try { await api.post(`/inv4/damage-loss/${id}/approve`); toast.success("Approved"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
  };
  const reject = async (id) => {
    const reason = prompt("Reason for rejection?"); if (!reason) return;
    try { await api.post(`/inv4/damage-loss/${id}/reject`, { reason }); toast.success("Rejected"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Reject failed"); }
  };

  return (
    <Card data-testid="damage-loss-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Damage / Loss Register ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="dl-new"><Plus className="h-3.5 w-3.5 mr-1" />Report Damage/Loss</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="dl-form">
            <div className="grid grid-cols-3 gap-2">
              <div><Label className="text-xs">Kind</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}>
                  <option value="damage">Damage</option><option value="loss">Loss</option>
                </select></div>
              <div><Label className="text-xs">Date</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>
              <div><Label className="text-xs">Item *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.item_id} onChange={e => setForm({ ...form, item_id: e.target.value })} data-testid="dl-item">
                  <option value="">—</option>{items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name}</option>)}
                </select></div>
              <div><Label className="text-xs">Quantity *</Label><Input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} data-testid="dl-qty" /></div>
              <div><Label className="text-xs">Project Code</Label><ProjectSelect label="" valueKey="code" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} /></div>
              <div><Label className="text-xs">Employee Responsible</Label><Input value={form.employee_id} onChange={e => setForm({ ...form, employee_id: e.target.value, employee_name: e.target.value })} /></div>
              <div className="col-span-3"><Label className="text-xs">Reason *</Label><Textarea rows={2} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} data-testid="dl-reason" /></div>
              <div className="col-span-2"><Label className="text-xs">Attachment URL * (photo/document)</Label><Input value={form.attachment_url} onChange={e => setForm({ ...form, attachment_url: e.target.value })} data-testid="dl-attach" /></div>
              <div>
                <label className="flex items-center gap-1 text-xs mt-5"><input type="checkbox" checked={form.recoverable} onChange={e => setForm({ ...form, recoverable: e.target.checked })} /> Recoverable</label>
              </div>
              {form.recoverable && <div><Label className="text-xs">Recovery Amount (₹)</Label><Input type="number" value={form.recovery_amount} onChange={e => setForm({ ...form, recovery_amount: e.target.value })} /></div>}
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="dl-save">Submit</Button>
            </div>
          </div>
        )}
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">DL No</th><th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">Kind</th><th className="text-left px-2 py-1">Item</th>
              <th className="text-right px-2 py-1">Qty</th><th className="text-right px-2 py-1">Value</th>
              <th className="text-left px-2 py-1">Reason</th><th className="text-center px-2 py-1">Status</th>
              <th></th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.dl_number}</td>
                  <td className="px-2 py-1 font-mono">{r.date}</td>
                  <td className="px-2 py-1"><span className={`px-1 py-0.5 rounded text-[10px] ${r.kind === "loss" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{r.kind}</span></td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-right">{r.quantity}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.value)}{r.needs_finance_approval && <span className="ml-1 text-rose-600">⚠</span>}</td>
                  <td className="px-2 py-1 text-[10px]">{(r.reason || "").slice(0, 40)}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      r.status === "approved" ? "bg-emerald-100 text-emerald-800" :
                      r.status === "rejected" ? "bg-rose-100 text-rose-800" :
                      "bg-violet-100 text-violet-800"}`}>{r.status}</span>
                  </td>
                  <td className="px-2 py-1 text-right">
                    {r.status === "submitted" && (
                      <>
                        <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => approve(r.id)} data-testid={`dl-approve-${r.id}`}>✓</Button>
                        <Button size="sm" variant="ghost" className="h-6 px-2 text-rose-600" onClick={() => reject(r.id)}>✗</Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={9} className="text-center py-6 text-slate-400">No damage/loss entries.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ════════════════ Scrap ════════════════ */
export function ScrapView() {
  const [rows, setRows] = useState([]);
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ date: today(), item_id: "", quantity: 1, reason: "", attachment_url: "", remarks: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [r, i] = await Promise.all([api.get("/inv4/scrap-entries"), api.get("/inventory")]);
      setRows(r.data); setItems(i.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.item_id || !form.reason || Number(form.quantity) <= 0) {
      toast.error("Item, qty>0 and reason required"); return;
    }
    setBusy(true);
    try {
      const r = await api.post("/inv4/scrap-entries", { ...form, quantity: Number(form.quantity) });
      toast.success(`${r.data.scrap_no} submitted`); setShowForm(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  const approve = async (id) => {
    try { await api.post(`/inv4/scrap-entries/${id}/approve`); toast.success("Approved & moved to scrap stock"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
  };

  return (
    <Card data-testid="scrap-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Scrap Entries ({rows.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="scrap-new"><Plus className="h-3.5 w-3.5 mr-1" />New Scrap</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="scrap-form">
            <div className="grid grid-cols-3 gap-2">
              <div><Label className="text-xs">Item *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.item_id} onChange={e => setForm({ ...form, item_id: e.target.value })} data-testid="scrap-item">
                  <option value="">—</option>{items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name}</option>)}
                </select></div>
              <div><Label className="text-xs">Quantity *</Label><Input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} /></div>
              <div><Label className="text-xs">Date</Label><Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} /></div>
              <div className="col-span-3"><Label className="text-xs">Reason *</Label><Input value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></div>
              <div className="col-span-2"><Label className="text-xs">Attachment URL (photo)</Label><Input value={form.attachment_url} onChange={e => setForm({ ...form, attachment_url: e.target.value })} /></div>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="scrap-save">Submit</Button>
            </div>
          </div>
        )}
        <div className="border rounded-md overflow-hidden max-h-[500px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">No</th><th className="text-left px-2 py-1">Date</th>
              <th className="text-left px-2 py-1">Item</th><th className="text-right px-2 py-1">Qty</th>
              <th className="text-right px-2 py-1">Value</th><th className="text-left px-2 py-1">Reason</th>
              <th className="text-center px-2 py-1">Status</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.scrap_no}</td>
                  <td className="px-2 py-1 font-mono">{r.date}</td>
                  <td className="px-2 py-1">{r.item_name}</td>
                  <td className="px-2 py-1 text-right">{r.quantity}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.value)}</td>
                  <td className="px-2 py-1 text-[10px]">{r.reason}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.status === "approved" ? "bg-emerald-100 text-emerald-800" : "bg-violet-100 text-violet-800"}`}>{r.status}</span>
                  </td>
                  <td className="px-2 py-1 text-right">{r.status === "submitted" && <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => approve(r.id)} data-testid={`scrap-approve-${r.id}`}>Approve</Button>}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No scrap entries.</td></tr>}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ════════════════ Employee Inventory Clearance ════════════════ */
export function EmployeeClearanceView() {
  const [empId, setEmpId] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!empId.trim()) { toast.error("Enter employee ID"); return; }
    setBusy(true);
    try {
      const r = await api.get(`/inv4/employee-clearance/${encodeURIComponent(empId.trim())}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Check failed"); }
    finally { setBusy(false); }
  };
  return (
    <Card data-testid="emp-clearance-view">
      <CardHeader className="pb-2"><CardTitle className="text-base">Employee Inventory Clearance</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 items-end">
          <div className="flex-1"><Label className="text-xs">Employee ID</Label><Input value={empId} onChange={e => setEmpId(e.target.value)} data-testid="emp-clearance-id" /></div>
          <Button onClick={run} disabled={busy} data-testid="emp-clearance-run">Check Clearance</Button>
        </div>
        {data && (
          <div className={`p-4 border rounded-md ${data.can_clear ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`} data-testid="emp-clearance-result">
            <div className="flex items-center gap-2 mb-2">
              {data.can_clear ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-rose-600" />}
              <span className="font-semibold">{data.can_clear ? "Cleared — no inventory blockers" : `${data.total_blockers} blocker(s) · ${fmt(data.outstanding_value)} outstanding`}</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              {Object.entries(data.pending_by_kind || {}).map(([k, v]) => v.length > 0 && (
                <div key={k} className="p-2 border rounded bg-white">
                  <div className="font-semibold uppercase text-[10px] text-slate-500">{k} · {v.length}</div>
                  {v.slice(0, 5).map((it, i) => <div key={i} className="text-[11px]">{it.item_name} <span className="text-slate-400">({it.outstanding_qty})</span></div>)}
                </div>
              ))}
              {data.pending_ppe?.length > 0 && (
                <div className="p-2 border rounded bg-white">
                  <div className="font-semibold uppercase text-[10px] text-slate-500">PPE · {data.pending_ppe.length}</div>
                  {data.pending_ppe.slice(0, 5).map(p => <div key={p.id} className="text-[11px]">{p.item_name}</div>)}
                </div>
              )}
              {data.pending_recoveries?.length > 0 && (
                <div className="p-2 border rounded bg-white">
                  <div className="font-semibold uppercase text-[10px] text-slate-500">Recoveries · {data.pending_recoveries.length}</div>
                  <div className="text-[11px]">Total: {fmt(data.recovery_amount)}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ════════════════ Recovery / Transit Exception / Tool Register ════════════════ */
export const RecoveryRegisterView = () => (
  <ReportCard title="Recovery Register" endpoint="/inv4/recoveries" testid="recovery-view"
    summary={d => `${fmt(d.total_pending)} pending`}
    columns={[
      { key: "source_no", label: "Source", cls: "font-mono" },
      { key: "source_type", label: "Type" },
      { key: "employee_name", label: "Employee" },
      { key: "project_code", label: "Project" },
      { key: "item_name", label: "Item" },
      { key: "amount", label: "Amount", align: "right", render: r => fmt(r.amount), cls: "tabular-nums font-semibold" },
      { key: "status", label: "Status",
        render: r => <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.status === "recovered" ? "bg-emerald-100 text-emerald-800" : r.status === "waived" ? "bg-slate-100" : "bg-amber-100 text-amber-800"}`}>{r.status}</span> },
    ]} />
);

export const TransitExceptionView = () => (
  <ReportCard title="Transit Exception Register" endpoint="/inv4/transit-exceptions" testid="transit-exception-view"
    summary={d => `${fmt(d.total_shortage_value + d.total_damaged_value)} exception value`}
    columns={[
      { key: "transfer_no", label: "Transfer No", cls: "font-mono" },
      { key: "from_store_name", label: "From" },
      { key: "to_store_name", label: "To" },
      { key: "vehicle_number", label: "Vehicle" },
      { key: "shortage_value", label: "Shortage Value", align: "right", render: r => fmt(r.shortage_value), cls: "tabular-nums text-rose-700" },
      { key: "damaged_value", label: "Damaged Value", align: "right", render: r => fmt(r.damaged_value), cls: "tabular-nums text-amber-700" },
      { key: "exception_value", label: "Total", align: "right", render: r => fmt(r.exception_value), cls: "tabular-nums font-semibold" },
    ]} />
);

export const ToolRegisterView = () => (
  <ReportCard title="Tool Issue Register" endpoint="/inv4/tool-issue-register" testid="tool-register-view"
    summary={d => `${d.pending_count} pending · ${fmt(d.pending_value)}`}
    columns={[
      { key: "allocation_no", label: "Issue No", cls: "font-mono" },
      { key: "item_name", label: "Tool" },
      { key: "employee_name", label: "Employee" },
      { key: "project_code", label: "Project" },
      { key: "quantity", label: "Issued", align: "right" },
      { key: "returned_qty", label: "Returned", align: "right" },
      { key: "issue_date", label: "Issue Date", cls: "font-mono" },
      { key: "status", label: "Status",
        render: r => <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.status === "returned" ? "bg-emerald-100 text-emerald-800" : r.status === "issued" ? "bg-blue-100 text-blue-800" : "bg-amber-100 text-amber-800"}`}>{r.status}</span> },
    ]} />
);
