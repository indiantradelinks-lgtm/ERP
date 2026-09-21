/**
 * Store & Inventory · Phase 3 views
 * ==================================
 * Material Request workflow + 2-step Transfer + Site/Project stock + Returnables.
 * All endpoints under /api/inv3/*.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Trash2, RefreshCcw, Send, CheckCircle2, XCircle, Truck,
  AlertTriangle } from "lucide-react";
import { ProjectSelect, SiteSelect } from "@/components/MasterSelect";

const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/* ═══════════════════ 1. Material Request ═══════════════════ */
export function MaterialRequestView() {
  const { rows, pagination, search, setSearch, reload } = usePagedList("/inv3/material-requests", {}, {
    viewKey: "inv3_material_requests", errorLabel: "material requests", searchKeys: "mr_no,request_no,project_code,project_name,site_name,requested_by,status,priority",
  });
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    project_code: "", site_code: "", priority: "normal", reason: "", remarks: "",
    required_date: "",
    lines: [{ item_id: "", required_qty: "", purpose: "" }],
  });
  const [issueFor, setIssueFor] = useState(null);
  const [issueLines, setIssueLines] = useState([]);
  const [issueRet, setIssueRet] = useState(false);

  const load = async () => {
    reload();
    try { const i = await api.get("/inventory"); setItems(i.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { api.get("/inventory").then((i) => setItems(i.data)).catch(() => {}); }, []);

  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, { item_id: "", required_qty: "", purpose: "" }] }));
  const removeLine = (i) => setForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));
  const updateLine = (i, k, v) => setForm(f => ({ ...f, lines: f.lines.map((l, idx) => idx === i ? { ...l, [k]: v } : l) }));

  const submit = async () => {
    if (!form.project_code.trim()) { toast.error("Project code is mandatory"); return; }
    if (!form.lines.length || form.lines.some(l => !l.item_id || Number(l.required_qty) <= 0)) {
      toast.error("Each line needs an item and qty > 0"); return;
    }
    setBusy(true);
    try {
      const r = await api.post("/inv3/material-requests", {
        ...form,
        lines: form.lines.map(l => ({
          item_id: l.item_id, required_qty: Number(l.required_qty),
          purpose: l.purpose || null,
        })),
      });
      toast.success(`MR ${r.data.mr_number} created`);
      setShowForm(false);
      setForm({ project_code: "", site_code: "", priority: "normal", reason: "", remarks: "", required_date: "",
                 lines: [{ item_id: "", required_qty: "", purpose: "" }] });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Create failed");
    } finally { setBusy(false); }
  };

  const approve = async (id) => {
    try {
      await api.post(`/inv3/material-requests/${id}/approve`, {});
      toast.success("Approved"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Approve failed"); }
  };
  const reject = async (id) => {
    const reason = prompt("Reason for rejection?");
    if (!reason) return;
    try {
      await api.post(`/inv3/material-requests/${id}/reject`, { reason });
      toast.success("Rejected"); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Reject failed"); }
  };

  const openIssue = (mr) => {
    setIssueFor(mr);
    setIssueLines(mr.lines.map(ln => ({
      item_id: ln.item_id, item_name: ln.item_name,
      balance: Number(ln.approved_qty || 0) - Number(ln.issued_qty || 0),
      issue_qty: Math.max(0, Number(ln.approved_qty || 0) - Number(ln.issued_qty || 0)),
    })));
    setIssueRet(false);
  };

  const doIssue = async () => {
    const lines = issueLines.filter(l => Number(l.issue_qty) > 0)
      .map(l => ({ item_id: l.item_id, issue_qty: Number(l.issue_qty) }));
    if (!lines.length) { toast.error("Set issue qty > 0 on at least one line"); return; }
    try {
      const r = await api.post(`/inv3/material-requests/${issueFor.id}/issue`, { lines, returnable: issueRet });
      toast.success(`${r.data.allocations_created} allocation(s) created · status ${r.data.new_status}`);
      setIssueFor(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Issue failed"); }
  };

  return (
    <Card data-testid="mr-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Material Requests <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="mr-new"><Plus className="h-3.5 w-3.5 mr-1" />New MR</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="mr-form">
            <div className="grid grid-cols-4 gap-2">
              <div><Label className="text-xs">Project Code *</Label><ProjectSelect label="" valueKey="code" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="mr-project" /></div>
              <div><Label className="text-xs">Site Code</Label><SiteSelect label="" valueKey="site_code" value={form.site_code} onChange={(v) => setForm({ ...form, site_code: v })} /></div>
              <div><Label className="text-xs">Priority</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} data-testid="mr-priority">
                  <option value="normal">Normal</option><option value="urgent">Urgent</option><option value="emergency">Emergency</option>
                </select></div>
              <div><Label className="text-xs">Required Date</Label><Input type="date" value={form.required_date} onChange={e => setForm({ ...form, required_date: e.target.value })} /></div>
            </div>
            <div><Label className="text-xs">Reason</Label><Input value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <Label className="text-xs">Lines</Label>
                <Button size="sm" variant="outline" onClick={addLine}><Plus className="h-3 w-3 mr-1" />Add</Button>
              </div>
              <table className="w-full text-xs border rounded">
                <thead className="bg-white"><tr>
                  <th className="text-left px-1 py-1">Item</th><th className="text-right px-1 py-1">Qty</th>
                  <th className="text-left px-1 py-1">Purpose</th><th></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-1 py-1">
                        <select className="w-full h-7 px-1 border rounded text-xs" value={l.item_id} onChange={e => updateLine(i, "item_id", e.target.value)} data-testid={`mr-line-${i}-item`}>
                          <option value="">—</option>
                          {items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name} (avail {it.quantity})</option>)}
                        </select>
                      </td>
                      <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.required_qty} onChange={e => updateLine(i, "required_qty", e.target.value)} data-testid={`mr-line-${i}-qty`} /></td>
                      <td className="px-1 py-1"><Input className="h-7" value={l.purpose} onChange={e => updateLine(i, "purpose", e.target.value)} /></td>
                      <td className="px-1 py-1"><Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => removeLine(i)}><Trash2 className="h-3 w-3 text-rose-600" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="mr-save">Submit MR</Button>
            </div>
          </div>
        )}

        {issueFor && (
          <div className="border rounded-md p-3 bg-blue-50 space-y-2" data-testid="mr-issue-form">
            <div className="text-sm font-semibold">Issue from {issueFor.mr_number} · {issueFor.project_code}</div>
            <table className="w-full text-xs border rounded">
              <thead className="bg-white"><tr>
                <th className="text-left px-1 py-1">Item</th>
                <th className="text-right px-1 py-1">Approved Balance</th>
                <th className="text-right px-1 py-1">Issue Qty</th>
              </tr></thead>
              <tbody>
                {issueLines.map((l, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-1 py-1">{l.item_name}</td>
                    <td className="px-1 py-1 text-right tabular-nums">{l.balance}</td>
                    <td className="px-1 py-1 w-24">
                      <Input className="h-7 text-right" type="number" value={l.issue_qty}
                              onChange={e => setIssueLines(ls => ls.map((x, idx) => idx === i ? { ...x, issue_qty: e.target.value } : x))}
                              data-testid={`mr-issue-line-${i}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={issueRet} onChange={e => setIssueRet(e.target.checked)} />
              Mark as returnable (will appear in Pending Returnable register)
            </label>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setIssueFor(null)}>Cancel</Button>
              <Button size="sm" onClick={doIssue} data-testid="mr-issue-confirm"><Send className="h-3.5 w-3.5 mr-1" />Issue Material</Button>
            </div>
          </div>
        )}

        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">MR No</th>
              <th className="text-left px-2 py-1">Project</th>
              <th className="text-left px-2 py-1">Priority</th>
              <th className="text-right px-2 py-1">Lines</th>
              <th className="text-right px-2 py-1">Approved Value</th>
              <th className="text-center px-2 py-1">Status</th>
              <th className="text-left px-2 py-1">By</th>
              <th className="text-right px-2 py-1">Actions</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50" data-testid={`mr-row-${r.id}`}>
                  <td className="px-2 py-1 font-mono">{r.mr_number}</td>
                  <td className="px-2 py-1">{r.project_code}{r.site_code && <span className="text-[10px] text-slate-500"> · {r.site_code}</span>}</td>
                  <td className="px-2 py-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      r.priority === "emergency" ? "bg-rose-100 text-rose-800" :
                      r.priority === "urgent" ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{r.priority}</span>
                  </td>
                  <td className="px-2 py-1 text-right">{r.line_count}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.total_approved_value || r.total_required_value)}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      r.status === "issued" ? "bg-emerald-100 text-emerald-800" :
                      r.status === "approved" ? "bg-blue-100 text-blue-800" :
                      r.status === "partially_issued" ? "bg-amber-100 text-amber-800" :
                      r.status === "rejected" ? "bg-rose-100 text-rose-800" :
                      r.status === "submitted" ? "bg-violet-100 text-violet-800" :
                      "bg-slate-100"}`}>{r.status}</span>
                  </td>
                  <td className="px-2 py-1 text-[10px]">{r.requested_by_name}</td>
                  <td className="px-2 py-1 text-right whitespace-nowrap">
                    {r.status === "submitted" && (
                      <>
                        <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => approve(r.id)} data-testid={`mr-approve-${r.id}`}>✓</Button>
                        <Button size="sm" variant="ghost" className="h-6 px-2 text-rose-600" onClick={() => reject(r.id)}>✗</Button>
                      </>
                    )}
                    {(r.status === "approved" || r.status === "partially_issued") && (
                      <Button size="sm" variant="outline" className="h-6 px-2" onClick={() => openIssue(r)} data-testid={`mr-issue-${r.id}`}>Issue</Button>
                    )}
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No material requests yet. Click "New MR".</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pt-2 flex items-center gap-2">
          <Input className="h-8 w-52" placeholder="Search MR #, project…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="mr-search" />
          <TableViewsMenu pagination={pagination} testidPrefix="mr" />
          <div className="flex-1"><TablePager pagination={pagination} testidPrefix="mr" /></div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 2. Material Transfer ═══════════════════ */
export function MaterialTransferView() {
  const { rows, pagination, search, setSearch, reload } = usePagedList("/inv3/transfers", {}, {
    viewKey: "inv3_transfers", errorLabel: "transfers", searchKeys: "transfer_no,from_store_name,to_store_name,project_code,status",
  });
  const [stores, setStores] = useState([]);
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    from_store_id: "", to_store_id: "", project_code: "", vehicle_number: "", transporter_name: "",
    expected_arrival: "", remarks: "",
    lines: [{ item_id: "", quantity: "" }],
  });
  const [receiveFor, setReceiveFor] = useState(null);
  const [receiveLines, setReceiveLines] = useState([]);
  const [receiveRemarks, setReceiveRemarks] = useState("");
  const [receiveAttach, setReceiveAttach] = useState("");

  const loadAux = async () => {
    try {
      const [s, i] = await Promise.all([api.get("/inv/stores"), api.get("/inventory")]);
      setStores(s.data); setItems(i.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  const load = () => { reload(); loadAux(); };
  useEffect(() => { loadAux(); }, []);

  const submit = async () => {
    if (!form.from_store_id || !form.to_store_id) { toast.error("Pick source and destination"); return; }
    if (form.from_store_id === form.to_store_id) { toast.error("Source and destination must differ"); return; }
    if (!form.lines.length || form.lines.some(l => !l.item_id || Number(l.quantity) <= 0)) {
      toast.error("Each line needs an item and qty > 0"); return;
    }
    setBusy(true);
    try {
      const r = await api.post("/inv3/transfers", {
        ...form,
        lines: form.lines.map(l => ({ item_id: l.item_id, quantity: Number(l.quantity) })),
      });
      toast.success(`Transfer ${r.data.transfer_no} dispatched`);
      setShowForm(false);
      setForm({ from_store_id: "", to_store_id: "", project_code: "", vehicle_number: "", transporter_name: "",
                 expected_arrival: "", remarks: "", lines: [{ item_id: "", quantity: "" }] });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Dispatch failed"); }
    finally { setBusy(false); }
  };

  const openReceive = (t) => {
    setReceiveFor(t);
    setReceiveLines(t.lines.map(ln => ({
      item_id: ln.item_id, item_name: ln.item_name, dispatched: ln.quantity,
      received_qty: ln.quantity, shortage_qty: 0, damaged_qty: 0, damage_notes: "",
    })));
    setReceiveRemarks(""); setReceiveAttach("");
  };

  const doReceive = async () => {
    try {
      await api.post(`/inv3/transfers/${receiveFor.id}/receive`, {
        lines: receiveLines.map(l => ({
          item_id: l.item_id, received_qty: Number(l.received_qty || 0),
          shortage_qty: Number(l.shortage_qty || 0), damaged_qty: Number(l.damaged_qty || 0),
          damage_notes: l.damage_notes || null,
        })),
        received_remarks: receiveRemarks || null,
        damage_attachment_url: receiveAttach || null,
      });
      toast.success("Transfer received");
      setReceiveFor(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Receive failed"); }
  };

  return (
    <Card data-testid="transfer-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Material Transfers <span className="text-xs text-slate-400">({rows.length})</span></CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="trf-new"><Plus className="h-3.5 w-3.5 mr-1" />New Transfer</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <div className="border rounded-md p-3 bg-slate-50 space-y-2" data-testid="trf-form">
            <div className="grid grid-cols-4 gap-2">
              <div><Label className="text-xs">From Store *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.from_store_id} onChange={e => setForm({ ...form, from_store_id: e.target.value })} data-testid="trf-from">
                  <option value="">—</option>{stores.map(s => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
                </select></div>
              <div><Label className="text-xs">To Store *</Label>
                <select className="w-full h-9 px-2 border rounded-md text-sm" value={form.to_store_id} onChange={e => setForm({ ...form, to_store_id: e.target.value })} data-testid="trf-to">
                  <option value="">—</option>{stores.map(s => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
                </select></div>
              <div><Label className="text-xs">Project Code</Label><ProjectSelect label="" valueKey="code" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} /></div>
              <div><Label className="text-xs">Vehicle No</Label><Input value={form.vehicle_number} onChange={e => setForm({ ...form, vehicle_number: e.target.value })} /></div>
              <div><Label className="text-xs">Transporter</Label><Input value={form.transporter_name} onChange={e => setForm({ ...form, transporter_name: e.target.value })} /></div>
              <div><Label className="text-xs">Expected Arrival</Label><Input type="date" value={form.expected_arrival} onChange={e => setForm({ ...form, expected_arrival: e.target.value })} /></div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <Label className="text-xs">Lines</Label>
                <Button size="sm" variant="outline" onClick={() => setForm(f => ({ ...f, lines: [...f.lines, { item_id: "", quantity: "" }] }))}><Plus className="h-3 w-3 mr-1" />Add</Button>
              </div>
              <table className="w-full text-xs border rounded">
                <thead className="bg-white"><tr><th className="text-left px-1 py-1">Item</th><th className="text-right px-1 py-1">Qty</th><th></th></tr></thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-1 py-1">
                        <select className="w-full h-7 px-1 border rounded text-xs" value={l.item_id} onChange={e => setForm(f => ({ ...f, lines: f.lines.map((x, j) => j === i ? { ...x, item_id: e.target.value } : x) }))} data-testid={`trf-line-${i}-item`}>
                          <option value="">—</option>{items.map(it => <option key={it.id} value={it.id}>{it.code} · {it.name} (avail {it.quantity})</option>)}
                        </select>
                      </td>
                      <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.quantity} onChange={e => setForm(f => ({ ...f, lines: f.lines.map((x, j) => j === i ? { ...x, quantity: e.target.value } : x) }))} data-testid={`trf-line-${i}-qty`} /></td>
                      <td className="px-1 py-1"><Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setForm(f => ({ ...f, lines: f.lines.filter((_, j) => j !== i) }))}><Trash2 className="h-3 w-3 text-rose-600" /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy} data-testid="trf-save"><Truck className="h-3.5 w-3.5 mr-1" />Dispatch</Button>
            </div>
          </div>
        )}

        {receiveFor && (
          <div className="border rounded-md p-3 bg-emerald-50 space-y-2" data-testid="trf-receive-form">
            <div className="text-sm font-semibold">Receive {receiveFor.transfer_no} · From {receiveFor.from_store_name} → {receiveFor.to_store_name}</div>
            <table className="w-full text-xs border rounded bg-white">
              <thead><tr>
                <th className="text-left px-1 py-1">Item</th>
                <th className="text-right px-1 py-1">Dispatched</th>
                <th className="text-right px-1 py-1">Received</th>
                <th className="text-right px-1 py-1">Shortage</th>
                <th className="text-right px-1 py-1">Damaged</th>
                <th className="text-left px-1 py-1">Damage Notes</th>
              </tr></thead>
              <tbody>
                {receiveLines.map((l, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-1 py-1">{l.item_name}</td>
                    <td className="px-1 py-1 text-right tabular-nums">{l.dispatched}</td>
                    <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.received_qty} onChange={e => setReceiveLines(ls => ls.map((x, j) => j === i ? { ...x, received_qty: e.target.value } : x))} data-testid={`trf-recv-${i}-qty`} /></td>
                    <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.shortage_qty} onChange={e => setReceiveLines(ls => ls.map((x, j) => j === i ? { ...x, shortage_qty: e.target.value } : x))} /></td>
                    <td className="px-1 py-1 w-20"><Input className="h-7 text-right" type="number" value={l.damaged_qty} onChange={e => setReceiveLines(ls => ls.map((x, j) => j === i ? { ...x, damaged_qty: e.target.value } : x))} /></td>
                    <td className="px-1 py-1"><Input className="h-7" value={l.damage_notes} onChange={e => setReceiveLines(ls => ls.map((x, j) => j === i ? { ...x, damage_notes: e.target.value } : x))} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grid grid-cols-2 gap-2">
              <div><Label className="text-xs">Received Remarks</Label><Input value={receiveRemarks} onChange={e => setReceiveRemarks(e.target.value)} /></div>
              <div><Label className="text-xs">Damage Attachment URL (required if shortage/damage)</Label><Input value={receiveAttach} onChange={e => setReceiveAttach(e.target.value)} /></div>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setReceiveFor(null)}>Cancel</Button>
              <Button size="sm" onClick={doReceive} data-testid="trf-receive-confirm"><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Confirm Receipt</Button>
            </div>
          </div>
        )}

        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              <th className="text-left px-2 py-1">Transfer No</th>
              <th className="text-left px-2 py-1">From → To</th>
              <th className="text-left px-2 py-1">Project</th>
              <th className="text-right px-2 py-1">Lines</th>
              <th className="text-right px-2 py-1">Value</th>
              <th className="text-center px-2 py-1">Status</th>
              <th className="text-left px-2 py-1">Vehicle</th>
              <th></th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-2 py-1 font-mono">{r.transfer_no}</td>
                  <td className="px-2 py-1"><span className="text-[10px]">{r.from_store_name} → {r.to_store_name}</span></td>
                  <td className="px-2 py-1">{r.project_code || "—"}</td>
                  <td className="px-2 py-1 text-right">{r.line_count}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(r.total_value)}</td>
                  <td className="px-2 py-1 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      r.status === "received" ? "bg-emerald-100 text-emerald-800" :
                      r.status === "received_with_exception" ? "bg-amber-100 text-amber-800" :
                      r.status === "in_transit" ? "bg-blue-100 text-blue-800" :
                      "bg-slate-100"}`}>{r.status?.replace("_", " ")}</span>
                  </td>
                  <td className="px-2 py-1 text-[10px]">{r.vehicle_number || "—"}</td>
                  <td className="px-2 py-1 text-right">
                    {r.status === "in_transit" && <Button size="sm" variant="outline" className="h-6 px-2" onClick={() => openReceive(r)} data-testid={`trf-receive-${r.id}`}>Receive</Button>}
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="text-center py-6 text-slate-400">No transfers yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pt-2 flex items-center gap-2">
          <Input className="h-8 w-52" placeholder="Search transfer #, store…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="xfer-search" />
          <TableViewsMenu pagination={pagination} testidPrefix="xfer" />
          <div className="flex-1"><TablePager pagination={pagination} testidPrefix="xfer" /></div>
        </div>
      </CardContent>
    </Card>
  );
}

/* ═══════════════════ 3-7. Read-only reports ═══════════════════ */
function ReportShell({ title, endpoint, columns, testid, rowKey = "id", emptyText = "No records." }) {
  const { rows, pagination, search, setSearch, meta, reload: load } = usePagedList(endpoint, {}, {
    viewKey: `inv3_report_${endpoint.split("/").pop()}`, errorLabel: title,
    searchKeys: columns.map((c) => c.key).filter((k) => k && !k.startsWith("_")).join(","),
  });
  const data = { rows, ...meta };
  return (
    <Card data-testid={testid}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{title} <span className="text-xs text-slate-400">({data.count ?? pagination.total}{data.total_value !== undefined ? ` · ${fmt(data.total_value)}` : ""})</span></CardTitle>
        <div className="flex items-center gap-2">
          <Input className="h-8 w-44" placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid={`${testid}-search`} />
          <TableViewsMenu pagination={pagination} testidPrefix={testid} />
          <Button size="sm" variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5 mr-1" />Refresh</Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="border rounded-md overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0"><tr>
              {columns.map(c => <th key={c.key} className={`text-${c.align || "left"} px-2 py-1`}>{c.label}</th>)}
            </tr></thead>
            <tbody>
              {(data.rows || []).map((r, i) => (
                <tr key={r[rowKey] || i} className="border-t hover:bg-slate-50">
                  {columns.map(c => <td key={c.key} className={`text-${c.align || "left"} px-2 py-1 ${c.cls || ""}`}>{c.render ? c.render(r) : r[c.key] ?? "—"}</td>)}
                </tr>
              ))}
              {!data.rows?.length && <tr><td colSpan={columns.length} className="text-center py-6 text-slate-400">{emptyText}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pt-2"><TablePager pagination={pagination} testidPrefix={testid} /></div>
      </CardContent>
    </Card>
  );
}

export const InTransitStockView = () => (
  <ReportShell title="In-Transit Stock" endpoint="/inv3/in-transit-stock" testid="in-transit-view"
    columns={[
      { key: "transfer_no", label: "Transfer No", cls: "font-mono" },
      { key: "from_store_name", label: "From" },
      { key: "to_store_name", label: "To" },
      { key: "project_code", label: "Project" },
      { key: "line_count", label: "Lines", align: "right" },
      { key: "total_value", label: "Value", align: "right", render: r => fmt(r.total_value), cls: "tabular-nums" },
      { key: "age_days", label: "Age (d)", align: "right",
        render: r => <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.age_days > 5 ? "bg-rose-100 text-rose-800" : r.age_days > 2 ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{r.age_days}</span> },
      { key: "vehicle_number", label: "Vehicle" },
    ]}
    emptyText="No materials currently in transit." />
);

export const SiteStockView = () => (
  <ReportShell title="Site-wise Stock" endpoint="/inv3/site-stock" testid="site-stock-view" rowKey="site_id"
    columns={[
      { key: "site_code", label: "Site Code", cls: "font-mono" },
      { key: "site_location", label: "Location" },
      { key: "project_code", label: "Project" },
      { key: "client_name", label: "Client" },
      { key: "item_count", label: "Items", align: "right" },
      { key: "total_value", label: "Stock Value", align: "right", render: r => fmt(r.total_value), cls: "tabular-nums font-semibold" },
    ]}
    emptyText="No site stores configured. Create one under Masters → Site Stores." />
);

export const ProjectStockView = () => (
  <ReportShell title="Project-wise Stock (outstanding allocations)" endpoint="/inv3/project-stock" testid="project-stock-view" rowKey="project_code"
    columns={[
      { key: "project_code", label: "Project", cls: "font-mono" },
      { key: "alloc_count", label: "Allocations", align: "right" },
      { key: "item_count", label: "Items", align: "right" },
      { key: "total_value", label: "Outstanding Value", align: "right", render: r => fmt(r.total_value), cls: "tabular-nums font-semibold" },
    ]}
    emptyText="No outstanding project allocations." />
);

export const ProjectConsumptionView = () => (
  <ReportShell title="Project-wise Material Consumption" endpoint="/inv3/project-consumption" testid="project-consumption-view" rowKey="project_code"
    columns={[
      { key: "project_code", label: "Project", cls: "font-mono" },
      { key: "txn_count", label: "Issue Txns", align: "right" },
      { key: "item_count", label: "Distinct Items", align: "right" },
      { key: "total_value", label: "Consumed Value", align: "right", render: r => fmt(r.total_value), cls: "tabular-nums font-semibold" },
    ]}
    emptyText="No project consumption recorded yet." />
);

export const PendingReturnableView = () => (
  <ReportShell title="Pending Returnable Material" endpoint="/inv3/pending-returnable" testid="returnable-view" rowKey="allocation_id"
    columns={[
      { key: "allocation_no", label: "Alloc No", cls: "font-mono" },
      { key: "item_name", label: "Item" },
      { key: "project_code", label: "Project" },
      { key: "site_code", label: "Site" },
      { key: "employee_name", label: "Issued To" },
      { key: "outstanding_qty", label: "Out Qty", align: "right" },
      { key: "outstanding_value", label: "Value", align: "right", render: r => fmt(r.outstanding_value), cls: "tabular-nums" },
      { key: "days_out", label: "Days Out", align: "right",
        render: r => <span className={`px-1.5 py-0.5 rounded text-[10px] ${r.overdue ? "bg-rose-100 text-rose-800" : r.days_out > 30 ? "bg-amber-100 text-amber-800" : "bg-slate-100"}`}>{r.days_out}d{r.overdue ? " ⚠" : ""}</span> },
      { key: "expected_return_date", label: "Expected Return" },
    ]}
    emptyText="No pending returnable materials. All clear!" />
);

/* ═══════════════════ Project Closure Check ═══════════════════ */
export function ProjectClosureCheckView() {
  const [proj, setProj] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!proj.trim()) { toast.error("Enter a project code"); return; }
    setBusy(true);
    try {
      const r = await api.get(`/inv3/project-closure-check/${encodeURIComponent(proj.trim())}`);
      setData(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Check failed");
    } finally { setBusy(false); }
  };

  return (
    <Card data-testid="closure-check-view">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Project Closure — Material Check</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 items-end">
          <div className="flex-1"><Label className="text-xs">Project Code</Label><ProjectSelect label="" valueKey="code" value={proj} onChange={(v) => setProj(v)} testid="closure-project" /></div>
          <Button onClick={run} disabled={busy} data-testid="closure-run">Run Check</Button>
        </div>
        {data && (
          <div className={`p-4 border rounded-md ${data.can_close ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`} data-testid="closure-result">
            <div className="flex items-center gap-2 mb-2">
              {data.can_close ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-rose-600" />}
              <span className="font-semibold">{data.can_close ? "Safe to close" : "Cannot close — blockers present"}</span>
            </div>
            <div className="grid grid-cols-4 gap-3 text-xs mb-3">
              <div><div className="text-slate-500">Pending Returnable</div><div className="font-bold">{data.pending_returnable_count} · {fmt(data.pending_returnable_value)}</div></div>
              <div><div className="text-slate-500">In-Transit</div><div className="font-bold">{data.in_transit_count}</div></div>
              <div><div className="text-slate-500">Pending MRs</div><div className="font-bold">{data.pending_mr_count}</div></div>
              <div><div className="text-slate-500">Project Stock Value</div><div className="font-bold">{fmt(data.project_stock_value)}</div></div>
            </div>
            {data.blockers?.length > 0 && (
              <ul className="text-sm space-y-1">
                {data.blockers.map((b, i) => <li key={i} className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5 text-rose-600" /> {b}</li>)}
              </ul>
            )}
            {data.pending_returnable_items?.length > 0 && (
              <details className="mt-3"><summary className="text-xs cursor-pointer text-slate-600">Pending returnable items ({data.pending_returnable_items.length})</summary>
                <table className="w-full text-xs mt-1 border rounded bg-white">
                  <thead><tr><th className="text-left px-2 py-1">Alloc No</th><th className="text-left px-2 py-1">Item</th><th className="text-right px-2 py-1">Qty</th><th className="text-right px-2 py-1">Value</th></tr></thead>
                  <tbody>{data.pending_returnable_items.map(it => (
                    <tr key={it.allocation_no} className="border-t"><td className="px-2 py-1 font-mono">{it.allocation_no}</td><td className="px-2 py-1">{it.item_name}</td><td className="px-2 py-1 text-right">{it.outstanding_qty}</td><td className="px-2 py-1 text-right">{fmt(it.value)}</td></tr>
                  ))}</tbody>
                </table>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
