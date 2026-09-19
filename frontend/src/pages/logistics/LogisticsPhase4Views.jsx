/**
 * Logistics Phase 4 Completion — 5 new views:
 *   FinanceApprovalInbox, VendorPayable, AccountsPostingStatus,
 *   ProjectWiseCost, VehicleWiseCost.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Landmark, Receipt, Building2, Truck, DollarSign, RefreshCcw, CheckCircle2 } from "lucide-react";
import { fmtDT } from "@/lib/datetime";
import { lookupGet } from "@/lib/lookups";

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

// ------------------------------------------------------------
// Finance Approval Inbox
// ------------------------------------------------------------
export function FinanceApprovalInbox() {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("pending");
  const load = async () => {
    try { const r = await api.get(`/logistics/finance-approvals?status=${status}`); setRows(r.data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [status]);  // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (id, action) => {
    try {
      await api.post(`/approvals/${id}/action`, { action, comment: `${action} via logistics inbox` });
      toast.success(action);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || `${action} failed`); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="finance-approvals-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Landmark className="h-6 w-6 text-amber-600" /> Finance Approval Inbox
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            High-value (≥₹50,000) logistics costs routed to Finance for approval before Accounts posting.
          </p>
        </div>
        <div className="flex gap-2">
          <select className="border rounded h-10 px-2 text-sm" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="fa-status">
            {["pending", "approved", "rejected", "all"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Title</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Requested By</th>
              <th className="text-left px-3 py-2">At</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-slate-400">No approvals.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`fa-row-${r.id}`}>
                <td className="px-3 py-2">
                  <div className="font-semibold">{r.title}</div>
                  <div className="text-xs text-slate-500">{r.summary}</div>
                </td>
                <td className="px-3 py-2 text-xs">{(r.type || "").replace("logistics_", "")}</td>
                <td className="px-3 py-2 text-xs">{r.requested_by}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{fmtDT(r.created_at)}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${r.status === "approved" ? "bg-emerald-100 text-emerald-800" : r.status === "rejected" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`}>{r.status}</span>
                </td>
                <td className="px-3 py-2 text-right space-x-1">
                  {r.status === "pending" && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => act(r.id, "approve")} data-testid={`fa-approve-${r.id}`}>Approve</Button>
                      <Button size="sm" variant="destructive" onClick={() => act(r.id, "reject")} data-testid={`fa-reject-${r.id}`}>Reject</Button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Vendor Payable
// ------------------------------------------------------------
export function VendorPayable() {
  const [data, setData] = useState(null);
  const load = async () => {
    try { const r = await api.get("/logistics/vendor-payable"); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);
  const totalOutstanding = useMemo(() => (data?.vendors || []).reduce((s, v) => s + (v.outstanding || 0), 0), [data]);

  return (
    <div className="p-6 space-y-4" data-testid="vendor-payable-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Receipt className="h-6 w-6 text-amber-600" /> Transport Vendor Payable
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Approved & posted vendor bills grouped by vendor · outstanding vs paid.
          </p>
        </div>
        <div className="flex gap-3 items-center">
          <div className="border rounded-sm px-3 py-1 bg-red-50/40 border-red-200">
            <div className="text-[10px] uppercase text-red-700 font-bold tracking-wider">Total Outstanding</div>
            <div className="text-xl font-black text-red-700">{inr(totalOutstanding)}</div>
          </div>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Vendor</th>
              <th className="text-right px-3 py-2">Bills</th>
              <th className="text-right px-3 py-2">Total Payable</th>
              <th className="text-right px-3 py-2">Paid</th>
              <th className="text-right px-3 py-2">Outstanding</th>
            </tr>
          </thead>
          <tbody>
            {!data?.vendors?.length && <tr><td colSpan={5} className="text-center py-8 text-slate-400">No approved vendor bills yet.</td></tr>}
            {(data?.vendors || []).map((v) => (
              <tr key={v.vendor_id} className="border-t hover:bg-slate-50/40" data-testid={`vp-row-${v.vendor_id}`}>
                <td className="px-3 py-2 font-semibold">{v.vendor_name}</td>
                <td className="px-3 py-2 text-right">{v.bill_count}</td>
                <td className="px-3 py-2 text-right">{inr(v.total_payable)}</td>
                <td className="px-3 py-2 text-right text-emerald-700">{inr(v.total_paid)}</td>
                <td className="px-3 py-2 text-right text-red-700 font-semibold">{inr(v.outstanding)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Accounts Posting Status
// ------------------------------------------------------------
export function AccountsPostingStatus() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("unposted"); // unposted | posted | all
  const load = async () => {
    try {
      const r = await api.get("/logistics/cost-allocations");
      let data = r.data || [];
      if (filter === "unposted") data = data.filter((c) => !c.posted_to_accounts);
      else if (filter === "posted") data = data.filter((c) => c.posted_to_accounts);
      setRows(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [filter]);  // eslint-disable-line react-hooks/exhaustive-deps

  const post = async (id) => {
    try { await api.post(`/logistics/cost-allocations/${id}/post-to-accounts`); toast.success("Posted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Post failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="accounts-posting-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Building2 className="h-6 w-6 text-amber-600" /> Accounts Posting Status
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Approved cost allocations awaiting posting to Accounts. High-value requires Finance approval first.
          </p>
        </div>
        <div className="flex gap-2">
          <select className="border rounded h-10 px-2 text-sm" value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="ap-filter">
            <option value="unposted">Unposted</option>
            <option value="posted">Posted</option>
            <option value="all">All</option>
          </select>
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      <div className="border rounded-sm bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Source</th>
              <th className="text-left px-3 py-2">Category</th>
              <th className="text-right px-3 py-2">Amount</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-center px-3 py-2">High Value</th>
              <th className="text-center px-3 py-2">Posted</th>
              <th className="text-right px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No allocations in this view.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`ap-row-${r.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.source_no}</td>
                <td className="px-3 py-2 capitalize">{r.category?.replace(/_/g, " ")}</td>
                <td className="px-3 py-2 text-right">{inr(r.amount)}</td>
                <td className="px-3 py-2">{r.project_code || "—"}</td>
                <td className="px-3 py-2 text-center">{r.high_value ? "⚠" : ""}</td>
                <td className="px-3 py-2 text-center">{r.posted_to_accounts ? "✔" : "—"}</td>
                <td className="px-3 py-2 text-right">
                  {!r.posted_to_accounts && (
                    <Button size="sm" variant="outline" onClick={() => post(r.id)} data-testid={`ap-post-${r.id}`}>
                      <CheckCircle2 className="h-3 w-3 mr-1" /> Post
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Project-wise Cost
// ------------------------------------------------------------
export function ProjectWiseCost() {
  const [code, setCode] = useState("");
  const [projects, setProjects] = useState([]);
  const [data, setData] = useState(null);

  useEffect(() => {
    lookupGet("/projects").then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  const load = async () => {
    if (!code) return;
    try { const r = await api.get(`/logistics/cost-by-project/${encodeURIComponent(code)}`); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { if (code) load(); }, [code]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="p-6 space-y-4" data-testid="cost-by-project-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <DollarSign className="h-6 w-6 text-amber-600" /> Project-wise Logistics Cost
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">Drill into freight / fuel / expense / maintenance costs booked against a project.</p>
      </div>

      <div className="flex gap-2 items-end max-w-md">
        <div className="flex-1">
          <label className="text-[10px] uppercase font-bold text-slate-500">Project</label>
          <select className="w-full border rounded h-10 px-2 text-sm" value={code} onChange={(e) => setCode(e.target.value)} data-testid="pbp-project">
            <option value="">— Select —</option>
            {projects.map((p) => <option key={p.id} value={p.code}>{p.code} · {p.name}</option>)}
          </select>
        </div>
      </div>

      {data && (
        <>
          <div className="border rounded-sm bg-red-50/40 border-red-200 p-3 max-w-md">
            <div className="text-[10px] uppercase text-red-700 font-bold tracking-wider">Total Cost · {data.project_code}</div>
            <div className="text-3xl font-black text-red-700">{inr(data.total)}</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="border rounded-sm bg-card overflow-hidden">
              <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">By Category</div>
              <table className="w-full text-sm">
                <tbody>
                  {data.by_category.map((c) => (
                    <tr key={c.category} className="border-t"><td className="px-3 py-1.5 capitalize">{c.category?.replace(/_/g, " ")}</td><td className="px-3 py-1.5 text-right">{inr(c.amount)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border rounded-sm bg-card overflow-hidden">
              <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">Recent Entries</div>
              <table className="w-full text-xs">
                <tbody>
                  {(data.rows || []).slice(0, 20).map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="px-3 py-1.5 font-mono">{r.source_no}</td>
                      <td className="px-3 py-1.5">{r.category}</td>
                      <td className="px-3 py-1.5 text-right">{inr(r.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Vehicle-wise Cost
// ------------------------------------------------------------
export function VehicleWiseCost() {
  const [vid, setVid] = useState("");
  const [vehicles, setVehicles] = useState([]);
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/logistics/vehicles").then((r) => setVehicles(r.data || [])).catch(() => {});
  }, []);
  const load = async () => {
    if (!vid) return;
    try { const r = await api.get(`/logistics/cost-by-vehicle/${vid}`); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { if (vid) load(); }, [vid]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="p-6 space-y-4" data-testid="cost-by-vehicle-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-1.5">Module · Logistics · Phase 4</div>
        <h1 className="font-display font-black text-2xl flex items-center gap-2">
          <Truck className="h-6 w-6 text-amber-600" /> Vehicle-wise Logistics Cost
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">TCO analysis per vehicle — fuel + expenses + maintenance + freight allocations.</p>
      </div>

      <div className="max-w-md">
        <label className="text-[10px] uppercase font-bold text-slate-500">Vehicle</label>
        <select className="w-full border rounded h-10 px-2 text-sm" value={vid} onChange={(e) => setVid(e.target.value)} data-testid="vbv-vehicle">
          <option value="">— Select —</option>
          {vehicles.map((v) => <option key={v.id} value={v.id}>{v.vehicle_number || v.reg_number} — {v.vehicle_type || v.type}</option>)}
        </select>
      </div>

      {data && (
        <>
          <div className="border rounded-sm bg-red-50/40 border-red-200 p-3 max-w-md">
            <div className="text-[10px] uppercase text-red-700 font-bold tracking-wider">
              Total Cost · {data.vehicle?.vehicle_number || vid}
            </div>
            <div className="text-3xl font-black text-red-700">{inr(data.total)}</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="border rounded-sm bg-card overflow-hidden">
              <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">By Category</div>
              <table className="w-full text-sm">
                <tbody>
                  {data.by_category.map((c) => (
                    <tr key={c.category} className="border-t"><td className="px-3 py-1.5 capitalize">{c.category?.replace(/_/g, " ")}</td><td className="px-3 py-1.5 text-right">{inr(c.amount)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border rounded-sm bg-card overflow-hidden">
              <div className="px-3 py-2 border-b bg-slate-50 text-xs font-bold uppercase tracking-wider">Recent Entries</div>
              <table className="w-full text-xs">
                <tbody>
                  {(data.rows || []).slice(0, 20).map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="px-3 py-1.5 font-mono">{r.source_no}</td>
                      <td className="px-3 py-1.5">{r.category}</td>
                      <td className="px-3 py-1.5 text-right">{inr(r.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
