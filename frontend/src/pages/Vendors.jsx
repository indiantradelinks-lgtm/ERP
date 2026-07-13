import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Send, ShieldCheck, Ban, RotateCcw, Edit, Trash2, FileText, X, Upload, FileEdit, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import FileUploader from "@/components/FileUploader";

const ADMIN_EDIT_ROLES = new Set(["super_admin", "director", "general_manager", "purchase_officer"]);

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-300",
  pending_approval: "bg-amber-100 text-amber-800 border-amber-300",
  approved: "bg-green-100 text-green-800 border-green-300",
  rejected: "bg-red-100 text-red-800 border-red-300",
  blocked: "bg-rose-100 text-rose-800 border-rose-300",
  inactive: "bg-zinc-100 text-zinc-600 border-zinc-300",
};

const DOC_TYPES = ["PAN", "GST", "MSME", "ISO", "Trade License", "Insurance", "Other"];
const ADDR_TYPES = ["registered", "billing", "shipping", "works"];
const ACCOUNT_TYPES = ["Current", "Savings", "Cash-Credit"];
const MSME_LEVELS = ["none", "micro", "small", "medium"];

function emptyVendor() {
  return {
    name: "", contact: "", email: "", phone: "", pan: "", gst: "", rating: 0,
    categories: [], addresses: [], bank_accounts: [], msme: { status: "none" },
    documents: [], notes: "",
  };
}

export default function Vendors() {
  const { user } = useAuth() || {};
  const isAdminEditor = ADMIN_EDIT_ROLES.has(user?.role);
  const [vendors, setVendors] = useState([]);
  const [cats, setCats] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dlg, setDlg] = useState({ open: false, vendor: null });

  const load = async () => {
    try {
      const [v, c] = await Promise.all([api.get("/vendors"), api.get("/vendor-categories")]);
      setVendors(v.data || []);
      setCats(c.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const filtered = useMemo(() => {
    return (vendors || []).filter((v) => {
      if (statusFilter !== "all" && v.status !== statusFilter) return false;
      if (search) {
        const s = search.toLowerCase();
        return (v.name || "").toLowerCase().includes(s)
          || (v.vendor_code || "").toLowerCase().includes(s)
          || (v.gst || "").toLowerCase().includes(s)
          || (v.pan || "").toLowerCase().includes(s);
      }
      return true;
    });
  }, [vendors, search, statusFilter]);

  const openNew = () => setDlg({ open: true, vendor: emptyVendor() });
  const openEdit = async (v) => {
    // Fetch fresh single record (includes orphan_files attached via parent_type=vendors)
    try {
      const r = await api.get(`/vendors/${v.id}`);
      setDlg({ open: true, vendor: { ...emptyVendor(), ...r.data } });
    } catch {
      setDlg({ open: true, vendor: { ...emptyVendor(), ...v } });
    }
  };

  const removeVendor = async (v) => {
    if (!window.confirm(`Delete vendor "${v.name}"? This cannot be undone.`)) return;
    try { await api.delete(`/vendors/${v.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const submitForApproval = async (v) => {
    try {
      await api.post(`/vendors/${v.id}/submit`);
      toast.success("Submitted for approval");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Submit failed"); }
  };

  const changeStatus = async (v, status, reason) => {
    try {
      await api.post(`/vendors/${v.id}/status`, { status, reason: reason || "" });
      toast.success(`Status changed to ${status}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Status change failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="vendors-page">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wider text-blue-600">Module · Procurement</div>
          <h1 className="text-3xl font-bold tracking-tight">Vendor Master</h1>
          <p className="text-sm text-slate-600">Approved supplier base · compliance, ratings, lifecycle.</p>
        </div>
        <div className="flex gap-2 items-center">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40" data-testid="vendors-filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.keys(STATUS_TONE).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input placeholder="Code, name, GST, PAN" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-8 w-64" data-testid="vendors-search" />
          </div>
          <Button onClick={openNew} data-testid="vendors-new-btn"><Plus className="h-4 w-4 mr-1" /> New Vendor</Button>
        </div>
      </div>

      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Code</th>
              <th className="text-left px-3 py-2">Vendor</th>
              <th className="text-left px-3 py-2">Categories</th>
              <th className="text-left px-3 py-2">Contact</th>
              <th className="text-left px-3 py-2">GST / PAN</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((v) => (
              <tr key={v.id} className="border-t hover:bg-slate-50" data-testid={`vendor-row-${v.id}`}>
                <td className="px-3 py-2 font-mono text-xs">{v.vendor_code || v.code || "—"}</td>
                <td className="px-3 py-2">
                  <div className="font-medium">{v.name}</div>
                  <div className="text-xs text-slate-500">{v.email || ""}</div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {(v.categories || []).slice(0, 3).map((c) => <Badge key={c} variant="outline" className="text-xs">{c}</Badge>)}
                    {(v.categories || []).length > 3 && <span className="text-xs text-slate-500">+{v.categories.length - 3}</span>}
                  </div>
                </td>
                <td className="px-3 py-2 text-xs">{v.contact || "—"}<div className="text-slate-500">{v.phone || ""}</div></td>
                <td className="px-3 py-2 text-xs">
                  <div>{v.gst || "—"}</div>
                  <div className="text-slate-500">{v.pan || ""}</div>
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[v.status] || STATUS_TONE.draft}`} data-testid={`vendor-status-${v.id}`}>
                    {v.status || "draft"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    {(v.status === "draft" || v.status === "rejected") && (
                      <Button size="sm" variant="default" onClick={() => submitForApproval(v)} data-testid={`vendor-submit-${v.id}`}>
                        <Send className="h-3.5 w-3.5 mr-1" /> Submit
                      </Button>
                    )}
                    {v.status === "approved" && (
                      <>
                        <Button size="sm" variant="outline" onClick={async () => {
                          const reason = window.prompt("Reason to reopen this approved vendor for editing? (will require re-approval after save)") || "";
                          if (!reason.trim()) { toast.error("Reason is required"); return; }
                          await changeStatus(v, "draft", reason);
                        }} data-testid={`vendor-reopen-${v.id}`}>
                          <FileEdit className="h-3.5 w-3.5 mr-1" /> Reopen
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => changeStatus(v, "blocked", window.prompt("Reason to block?") || "")} data-testid={`vendor-block-${v.id}`}>
                          <Ban className="h-3.5 w-3.5 mr-1" /> Block
                        </Button>
                      </>
                    )}
                    {(v.status === "blocked" || v.status === "inactive") && (
                      <Button size="sm" variant="outline" onClick={() => changeStatus(v, "approved")} data-testid={`vendor-reactivate-${v.id}`}>
                        <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reactivate
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => openEdit(v)} data-testid={`vendor-edit-${v.id}`}>
                      <Edit className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => removeVendor(v)} data-testid={`vendor-delete-${v.id}`}>
                      <Trash2 className="h-3.5 w-3.5 text-red-600" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-slate-500 text-sm">No vendors match the filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {dlg.open && (
        <VendorDialog
          vendor={dlg.vendor}
          cats={cats}
          isAdminEditor={isAdminEditor}
          onClose={() => setDlg({ open: false, vendor: null })}
          onSaved={() => { load(); setDlg({ open: false, vendor: null }); }}
          onStatusChange={changeStatus}
        />
      )}
    </div>
  );
}


function VendorDialog({ vendor, cats, onClose, onSaved, onStatusChange, isAdminEditor }) {
  const [form, setForm] = useState(vendor);
  const [tab, setTab] = useState("basic");
  const isNew = !form.id;
  // Editable when:
  //  • new
  //  • status is draft / rejected
  //  • OR user is an admin role (super_admin/director/GM/purchase_officer) — backend allows in-place edit
  const isReadOnly = !isNew && form.status && form.status !== "draft" && form.status !== "rejected" && !isAdminEditor;

  const doStatus = async (newStatus, promptForReason) => {
    let reason = "";
    if (promptForReason) {
      reason = window.prompt(`Reason to change status to "${newStatus}"?`) || "";
      if (!reason.trim()) { toast.error("A reason is required for this transition"); return; }
    }
    await onStatusChange({ id: form.id, name: form.name }, newStatus, reason);
    onClose();
  };

  const save = async () => {
    try {
      const payload = { ...form };
      delete payload.id;
      delete payload.vendor_code;
      delete payload.status;
      delete payload.approval_id;
      delete payload.created_at;
      delete payload.created_by;
      delete payload.updated_at;
      delete payload.updated_by;
      if (isNew) {
        const r = await api.post("/vendors", payload);
        toast.success(`Vendor created (${r.data.vendor_code})`);
      } else {
        await api.put(`/vendors/${form.id}`, payload);
        toast.success("Vendor updated");
      }
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setNested = (key, idx, field, value) => {
    setForm((f) => {
      const arr = [...(f[key] || [])];
      arr[idx] = { ...arr[idx], [field]: value };
      return { ...f, [key]: arr };
    });
  };
  const pushTo = (key, item) => setForm((f) => ({ ...f, [key]: [...(f[key] || []), item] }));
  const removeAt = (key, idx) => setForm((f) => ({ ...f, [key]: (f[key] || []).filter((_, i) => i !== idx) }));

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isNew ? "New Vendor" : `Edit Vendor — ${form.vendor_code || ""}`}
            {form.status && (
              <span className={`ml-3 inline-block px-2 py-0.5 text-xs rounded border ${STATUS_TONE[form.status] || ""}`}>{form.status}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab} className="mt-2">
          <TabsList className="grid grid-cols-6 w-full">
            <TabsTrigger value="basic" data-testid="vendor-tab-basic">Basic</TabsTrigger>
            <TabsTrigger value="categories" data-testid="vendor-tab-categories">Categories</TabsTrigger>
            <TabsTrigger value="addresses" data-testid="vendor-tab-addresses">Addresses</TabsTrigger>
            <TabsTrigger value="banks" data-testid="vendor-tab-banks">Bank</TabsTrigger>
            <TabsTrigger value="msme" data-testid="vendor-tab-msme">MSME</TabsTrigger>
            <TabsTrigger value="documents" data-testid="vendor-tab-documents">Documents</TabsTrigger>
          </TabsList>

          <TabsContent value="basic" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Vendor Name *</Label><Input value={form.name || ""} onChange={(e) => set("name", e.target.value)} disabled={isReadOnly} data-testid="vendor-field-name" /></div>
              <div><Label>Contact Person</Label><Input value={form.contact || ""} onChange={(e) => set("contact", e.target.value)} disabled={isReadOnly} /></div>
              <div><Label>Email</Label><Input value={form.email || ""} onChange={(e) => set("email", e.target.value)} disabled={isReadOnly} /></div>
              <div><Label>Phone</Label><Input value={form.phone || ""} onChange={(e) => set("phone", e.target.value)} disabled={isReadOnly} /></div>
              <div><Label>PAN</Label><Input value={form.pan || ""} onChange={(e) => set("pan", e.target.value.toUpperCase())} disabled={isReadOnly} data-testid="vendor-field-pan" /></div>
              <div><Label>GSTIN</Label><Input value={form.gst || ""} onChange={(e) => set("gst", e.target.value.toUpperCase())} disabled={isReadOnly} data-testid="vendor-field-gst" /></div>
              <div><Label>Rating (0-5)</Label><Input type="number" step={0.1} min={0} max={5} value={form.rating || 0} onChange={(e) => set("rating", parseFloat(e.target.value || 0))} disabled={isReadOnly} /></div>
            </div>
            <div><Label>Notes</Label><Textarea rows={3} value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} disabled={isReadOnly} /></div>
          </TabsContent>

          <TabsContent value="categories" className="mt-4">
            <p className="text-sm text-slate-600 mb-3">Select all supply categories this vendor caters to (drives RFQ vendor suggestions).</p>
            <div className="grid grid-cols-3 gap-2" data-testid="vendor-categories-grid">
              {(cats || []).map((c) => {
                const sel = (form.categories || []).includes(c.code);
                return (
                  <label key={c.code} className={`flex items-center gap-2 border rounded px-2 py-1.5 cursor-pointer ${sel ? "bg-blue-50 border-blue-400" : ""}`}>
                    <Checkbox checked={sel} onCheckedChange={(v) => {
                      const next = new Set(form.categories || []);
                      v ? next.add(c.code) : next.delete(c.code);
                      set("categories", Array.from(next));
                    }} disabled={isReadOnly} data-testid={`vendor-cat-${c.code}`} />
                    <div className="text-sm">
                      <div className="font-medium">{c.code}</div>
                      <div className="text-xs text-slate-500">{c.name}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="addresses" className="mt-4 space-y-3">
            {(form.addresses || []).map((a, i) => (
              <div key={i} className="border rounded p-3 grid grid-cols-2 gap-2 relative" data-testid={`vendor-address-${i}`}>
                <Button size="sm" variant="ghost" className="absolute top-1 right-1" onClick={() => removeAt("addresses", i)} disabled={isReadOnly}><X className="h-3.5 w-3.5" /></Button>
                <div><Label>Type</Label>
                  <Select value={a.type || "registered"} onValueChange={(v) => setNested("addresses", i, "type", v)} disabled={isReadOnly}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{ADDR_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2 pt-6"><Checkbox checked={a.is_default || false} onCheckedChange={(v) => setNested("addresses", i, "is_default", !!v)} disabled={isReadOnly} /><Label>Default</Label></div>
                <div className="col-span-2"><Label>Line 1</Label><Input value={a.line1 || ""} onChange={(e) => setNested("addresses", i, "line1", e.target.value)} disabled={isReadOnly} /></div>
                <div className="col-span-2"><Label>Line 2</Label><Input value={a.line2 || ""} onChange={(e) => setNested("addresses", i, "line2", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>City</Label><Input value={a.city || ""} onChange={(e) => setNested("addresses", i, "city", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>State</Label><Input value={a.state || ""} onChange={(e) => setNested("addresses", i, "state", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>PIN</Label><Input value={a.pin || ""} onChange={(e) => setNested("addresses", i, "pin", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>GSTIN at this address</Label><Input value={a.gst || ""} onChange={(e) => setNested("addresses", i, "gst", e.target.value.toUpperCase())} disabled={isReadOnly} /></div>
              </div>
            ))}
            <Button variant="outline" onClick={() => pushTo("addresses", { type: "registered", country: "India", is_default: (form.addresses || []).length === 0 })} disabled={isReadOnly} data-testid="vendor-add-address">
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Address
            </Button>
          </TabsContent>

          <TabsContent value="banks" className="mt-4 space-y-3">
            {(form.bank_accounts || []).map((b, i) => (
              <div key={i} className="border rounded p-3 grid grid-cols-2 gap-2 relative" data-testid={`vendor-bank-${i}`}>
                <Button size="sm" variant="ghost" className="absolute top-1 right-1" onClick={() => removeAt("bank_accounts", i)} disabled={isReadOnly}><X className="h-3.5 w-3.5" /></Button>
                <div><Label>Bank Name</Label><Input value={b.bank_name || ""} onChange={(e) => setNested("bank_accounts", i, "bank_name", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>Branch</Label><Input value={b.branch || ""} onChange={(e) => setNested("bank_accounts", i, "branch", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>Account Number</Label><Input value={b.account_no || ""} onChange={(e) => setNested("bank_accounts", i, "account_no", e.target.value)} disabled={isReadOnly} /></div>
                <div><Label>IFSC</Label><Input value={b.ifsc || ""} onChange={(e) => setNested("bank_accounts", i, "ifsc", e.target.value.toUpperCase())} disabled={isReadOnly} /></div>
                <div><Label>Account Type</Label>
                  <Select value={b.account_type || "Current"} onValueChange={(v) => setNested("bank_accounts", i, "account_type", v)} disabled={isReadOnly}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{ACCOUNT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2 pt-6"><Checkbox checked={b.is_default || false} onCheckedChange={(v) => setNested("bank_accounts", i, "is_default", !!v)} disabled={isReadOnly} /><Label>Default</Label></div>
              </div>
            ))}
            <Button variant="outline" onClick={() => pushTo("bank_accounts", { account_type: "Current", is_default: (form.bank_accounts || []).length === 0 })} disabled={isReadOnly} data-testid="vendor-add-bank">
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Bank Account
            </Button>
          </TabsContent>

          <TabsContent value="msme" className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>MSME Status</Label>
                <Select value={form.msme?.status || "none"} onValueChange={(v) => set("msme", { ...(form.msme || {}), status: v })} disabled={isReadOnly}>
                  <SelectTrigger data-testid="vendor-msme-status"><SelectValue /></SelectTrigger>
                  <SelectContent>{MSME_LEVELS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Udyam Number</Label><Input value={form.msme?.udyam_number || ""} onChange={(e) => set("msme", { ...(form.msme || {}), udyam_number: e.target.value })} disabled={isReadOnly || (form.msme?.status === "none")} data-testid="vendor-msme-udyam" /></div>
              <div><Label>Certificate Expiry</Label><Input type="date" value={form.msme?.certificate_expiry || ""} onChange={(e) => set("msme", { ...(form.msme || {}), certificate_expiry: e.target.value })} disabled={isReadOnly || (form.msme?.status === "none")} /></div>
            </div>
            <p className="text-xs text-slate-500">MSME-registered vendors get prompt payment treatment per the MSMED Act (45-day rule).</p>
          </TabsContent>

          <TabsContent value="documents" className="mt-4 space-y-3">
            <div className="grid grid-cols-1 gap-2">
              {(form.documents || []).map((d, i) => {
                const downloadUrl = d.file_id ? `${process.env.REACT_APP_BACKEND_URL}/api/files/${d.file_id}/download` : null;
                return (
                  <div key={i} className="border rounded p-2 grid grid-cols-12 gap-2 items-center" data-testid={`vendor-doc-${i}`}>
                    <Select value={d.type || "Other"} onValueChange={(v) => setNested("documents", i, "type", v)} disabled={isReadOnly}>
                      <SelectTrigger className="col-span-2"><SelectValue /></SelectTrigger>
                      <SelectContent>{DOC_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                    <Input className="col-span-4" placeholder="Name / number" value={d.name || ""} onChange={(e) => setNested("documents", i, "name", e.target.value)} disabled={isReadOnly} />
                    <Input className="col-span-3" type="date" placeholder="Expiry" value={d.expiry || ""} onChange={(e) => setNested("documents", i, "expiry", e.target.value)} disabled={isReadOnly} />
                    <div className="col-span-2 flex gap-1 items-center">
                      {downloadUrl ? (
                        <>
                          <a
                            href={downloadUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="h-7 px-2 grid place-items-center rounded-sm border bg-white hover:bg-blue-50 text-blue-700 text-xs flex-1"
                            title="Preview / open"
                            data-testid={`vendor-doc-${i}-preview`}
                          >
                            Preview
                          </a>
                          <a
                            href={downloadUrl}
                            download={d.name || "file"}
                            className="h-7 w-7 grid place-items-center rounded-sm border bg-white hover:bg-slate-50 text-slate-700"
                            title="Download"
                            data-testid={`vendor-doc-${i}-download`}
                          >
                            <FileDown className="h-3.5 w-3.5" />
                          </a>
                        </>
                      ) : <span className="text-xs text-amber-600">no file</span>}
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => removeAt("documents", i)} disabled={isReadOnly}><X className="h-3.5 w-3.5" /></Button>
                  </div>
                );
              })}
              {(form.documents || []).length === 0 && (
                <p className="text-xs text-slate-500 italic">No documents attached yet. Upload below to attach PAN / GST / MSME / ISO etc.</p>
              )}
            </div>
            {/* Orphan files attached at parent_type=vendors but not yet linked into documents[] */}
            {(form.orphan_files || []).length > 0 && (
              <div className="border border-amber-300 bg-amber-50 rounded p-2 space-y-2">
                <div className="text-xs font-medium text-amber-800">⚠️ Unlinked files on this vendor — preview/download below, or click "Link" to add a typed entry.</div>
                {form.orphan_files.map((f) => {
                  const url = `${process.env.REACT_APP_BACKEND_URL}/api/files/${f.id}/download`;
                  return (
                    <div key={f.id} className="flex items-center gap-2 text-xs" data-testid={`vendor-doc-orphan-${f.id}`}>
                      <span className="flex-1 truncate font-medium">{f.original_filename}</span>
                      <span className="text-slate-500 text-[10px]">{(f.size / 1024).toFixed(1)} KB</span>
                      <a href={url} target="_blank" rel="noreferrer" className="h-6 px-2 grid place-items-center rounded-sm border bg-white text-blue-700 hover:bg-blue-50" data-testid={`vendor-doc-orphan-${f.id}-preview`}>Preview</a>
                      <a href={url} download={f.original_filename} className="h-6 w-6 grid place-items-center rounded-sm border bg-white"><FileDown className="h-3 w-3" /></a>
                      {!isReadOnly && (
                        <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => {
                          const t = window.prompt(`Type for ${f.original_filename}? (${DOC_TYPES.join(", ")})`, "Other") || "Other";
                          pushTo("documents", { type: t, name: f.original_filename, file_id: f.id, uploaded_at: f.created_at });
                          // remove from orphans locally
                          set("orphan_files", form.orphan_files.filter((x) => x.id !== f.id));
                          toast.success(`Linked ${f.original_filename} as ${t}`);
                        }} data-testid={`vendor-doc-orphan-${f.id}-link`}>Link</Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {form.id && !isReadOnly && (
              <div>
                <p className="text-xs text-slate-600 mb-2">Upload a file, then add a typed entry referencing its file_id (or use the Upload prompt below).</p>
                <FileUploader
                  folder="documents"
                  parent_type="vendors"
                  parent_id={form.id}
                  onUploaded={(file) => {
                    const t = window.prompt(`Type for ${file.name}? (${DOC_TYPES.join(", ")})`, "Other") || "Other";
                    pushTo("documents", { type: t, name: file.name, file_id: file.id, uploaded_at: new Date().toISOString() });
                    toast.success(`Linked ${file.name} as ${t}`);
                  }}
                  testidPrefix="vendor-doc-uploader"
                />
              </div>
            )}
            {!form.id && <p className="text-xs text-amber-700">Save the vendor first, then add documents.</p>}
          </TabsContent>
        </Tabs>

        <DialogFooter className="mt-4 flex-col sm:flex-row gap-2 sm:gap-2">
          {!isReadOnly && (
            <div className="flex flex-wrap gap-2 items-center">
              <Button onClick={save} data-testid="vendor-save-btn">
                <ShieldCheck className="h-4 w-4 mr-1" /> Save {isNew ? "Draft" : "Changes"}
              </Button>
              {isAdminEditor && !isNew && form.status && form.status !== "draft" && form.status !== "rejected" && (
                <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 px-2 py-1 rounded">
                  Admin in-place edit — changes save without re-approval. Use <b>Reopen for Edit</b> on the row if you want a fresh approval cycle.
                </span>
              )}
            </div>
          )}
          {isReadOnly && (
            <div className="flex-1 w-full">
              <div className="text-xs text-amber-700 mb-2">
                Locked at status <b className="uppercase">{form.status}</b>.
                {form.status === "approved" && " Editing approved vendors is blocked — use the status overrides below to reopen, block, or inactivate."}
                {form.status === "blocked" && " Block lifted by Reactivate. Inactivate to retire permanently."}
                {form.status === "inactive" && " Reactivate to bring this vendor back online."}
                {form.status === "pending_approval" && " This vendor is currently in the approval queue — wait for the chain to complete or ask an approver to reject so it returns to draft."}
              </div>
              {/* Approved → Reopen / Block / Inactivate */}
              {form.status === "approved" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => doStatus("draft", true)} data-testid="vendor-dialog-reopen">
                    <FileEdit className="h-4 w-4 mr-1" /> Reopen for Edit
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => doStatus("blocked", true)} data-testid="vendor-dialog-block">
                    <Ban className="h-4 w-4 mr-1" /> Block
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => doStatus("inactive", false)} data-testid="vendor-dialog-inactivate">
                    Inactivate
                  </Button>
                </div>
              )}
              {/* Blocked → Reactivate / Inactivate */}
              {form.status === "blocked" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => doStatus("approved", false)} data-testid="vendor-dialog-reactivate">
                    <RotateCcw className="h-4 w-4 mr-1" /> Reactivate
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => doStatus("inactive", false)} data-testid="vendor-dialog-inactivate">
                    Inactivate
                  </Button>
                </div>
              )}
              {/* Inactive → Reactivate */}
              {form.status === "inactive" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => doStatus("approved", false)} data-testid="vendor-dialog-reactivate">
                    <RotateCcw className="h-4 w-4 mr-1" /> Reactivate
                  </Button>
                </div>
              )}
            </div>
          )}
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
