import { ChevronRight, ChevronDown, Plus, Pencil, Trash2, Building2, MapPin, Users, X, Search, Download, Upload, FolderArchive, RefreshCw, ClipboardCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import ClientDocsDialog from "@/components/ClientDocsDialog";
import LeafletPinEditor from "@/components/LeafletPinEditor";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";

const CONTACT_DEPTS = ["Purchase", "Accounts", "Technical", "User", "Stores", "Safety", "Project", "Management"];
const CATEGORIES = ["Strategic", "Standard", "Government", "Public Sector", "Private", "Retail"];
const STATUSES = ["active", "on_hold", "inactive", "pending_approval", "rejected"];
const STATUS_TONE = { active: "success", on_hold: "warning", inactive: "neutral", pending_approval: "warning", rejected: "danger" };

/**
 * Tree-view client management — parent client → sites → contacts.
 * Read-only auto codes. Cascading add buttons. Inline search.
 */
export default function Clients() {
  const navigate = useNavigate();
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(new Set());
  const [query, setQuery] = useState("");
  const [clientDialog, setClientDialog] = useState(null);   // {client?} for edit, {} for new
  const [siteDialog, setSiteDialog] = useState(null);       // {clientId, site?}
  const [contactDialog, setContactDialog] = useState(null); // {siteId, contact?}
  const [docsDialog, setDocsDialog] = useState(null);       // {parentType, parentId, title}
  const importInput = useRef(null);

  const reload = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/clients-tree?include_inactive=true");
      setTree(data || []);
    } catch (e) { toast.error("Failed to load clients"); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); }, []);

  const downloadCsv = async () => {
    try {
      const res = await api.get("/clients/export.csv", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = "clients.csv"; a.click();
      window.URL.revokeObjectURL(url);
      toast.success("CSV downloaded");
    } catch (e) { toast.error("Export failed"); }
  };

  const importCsv = async (file) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/clients/import.csv", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Created ${data.summary.created} · Skipped ${data.summary.skipped}`);
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    if (importInput.current) importInput.current.value = "";
  };

  const resubmit = async (client) => {
    if (!window.confirm(`Resubmit ${client.customer_code} for onboarding approval?`)) return;
    try {
      const { data } = await api.post(`/clients/${client.id}/resubmit`);
      toast.success(`Resubmitted — approval ${data.approval_id.slice(0, 8)} created`);
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Resubmit failed"); }
  };

  const filtered = filterTree(tree, query);
  const totalClients = tree.length;
  const totalSites = tree.reduce((s, c) => s + (c.sites?.length || 0), 0);
  const totalContacts = tree.reduce((s, c) => s + (c.sites?.reduce((ss, st) => ss + (st.contacts?.length || 0), 0) || 0), 0);

  return (
    <div className="space-y-6" data-testid="clients-tree">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <Building2 className="h-3 w-3" /> Sales · Customer Master
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight">Clients & Sites</h1>
          <p className="text-sm text-muted-foreground mt-1">Parent client → sites → contacts. Auto-generated codes are system-controlled.</p>
        </div>
        <div className="flex gap-2">
          <input
            ref={importInput}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => importCsv(e.target.files?.[0])}
            data-testid="clients-import-file"
          />
          <Button variant="outline" className="rounded-sm" onClick={() => navigate("/app/client-map")} data-testid="clients-map-btn">
            <MapPin className="h-4 w-4 mr-1.5" /> Map
          </Button>
          <Button variant="outline" className="rounded-sm" onClick={() => importInput.current?.click()} data-testid="clients-import">
            <Upload className="h-4 w-4 mr-1.5" /> Import CSV
          </Button>
          <Button variant="outline" className="rounded-sm" onClick={downloadCsv} data-testid="clients-export">
            <Download className="h-4 w-4 mr-1.5" /> Export CSV
          </Button>
          <Button className="rounded-sm" onClick={() => setClientDialog({})} data-testid="clients-add">
            <Plus className="h-4 w-4 mr-1.5" /> New Client
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="clients-kpis">
        <KPI label="Clients" value={totalClients} icon={Building2} />
        <KPI label="Sites" value={totalSites} icon={MapPin} />
        <KPI label="Contacts" value={totalContacts} icon={Users} />
        <KPI label="Active" value={tree.filter((c) => c.status === "active").length} icon={Building2} tone="success" />
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="relative flex-1 max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by code, GST, city, contact, mobile…"
            className="rounded-sm pl-9"
            data-testid="clients-search"
          />
        </div>
        <Button variant="outline" className="rounded-sm" onClick={() => setExpanded(new Set(tree.map((c) => c.id)))} data-testid="clients-expand-all">
          Expand All
        </Button>
        <Button variant="outline" className="rounded-sm" onClick={() => setExpanded(new Set())} data-testid="clients-collapse-all">
          Collapse All
        </Button>
      </div>

      <div className="bg-card border border-border rounded-sm" data-testid="clients-list">
        {loading && <div className="p-6 text-sm text-muted-foreground">Loading clients…</div>}
        {!loading && filtered.length === 0 && (
          <div className="p-10 text-center text-sm text-muted-foreground">No clients match.</div>
        )}
        {filtered.map((c) => (
          <ClientNode
            key={c.id}
            client={c}
            isOpen={expanded.has(c.id)}
            onToggle={() => setExpanded((s) => { const n = new Set(s); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n; })}
            onEdit={() => setClientDialog({ client: c })}
            onAddSite={() => setSiteDialog({ clientId: c.id })}
            onOpenDocs={() => setDocsDialog({ parentType: "clients", parentId: c.id, title: `${c.customer_code} · ${c.name}` })}
            onResubmit={() => resubmit(c)}
            onOpenApproval={() => c.approval_id && navigate(`/app/approvals?id=${c.approval_id}`)}
            onEditSite={(site) => setSiteDialog({ clientId: c.id, site })}
            onOpenSiteDocs={(site) => setDocsDialog({ parentType: "client_sites", parentId: site.id, title: `${site.site_code} · ${site.name}` })}
            onDeleteSite={async (site) => {
              if (!window.confirm(`Delete site ${site.site_code}? All ${site.contacts?.length || 0} contacts will be removed.`)) return;
              try { await api.delete(`/sites/${site.id}`); toast.success("Site deleted"); reload(); }
              catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
            }}
            onAddContact={(siteId) => setContactDialog({ siteId })}
            onEditContact={(siteId, contact) => setContactDialog({ siteId, contact })}
            onDeleteContact={async (contact) => {
              if (!window.confirm(`Remove ${contact.name}?`)) return;
              try { await api.delete(`/contacts/${contact.id}`); toast.success("Contact removed"); reload(); }
              catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
            }}
          />
        ))}
      </div>

      {clientDialog && <ClientDialog initial={clientDialog.client} onClose={() => setClientDialog(null)} onSaved={reload} />}
      {siteDialog && <SiteDialog initial={siteDialog.site} clientId={siteDialog.clientId} onClose={() => setSiteDialog(null)} onSaved={reload} />}
      {contactDialog && <ContactDialog initial={contactDialog.contact} siteId={contactDialog.siteId} onClose={() => setContactDialog(null)} onSaved={reload} />}
      {docsDialog && <ClientDocsDialog parentType={docsDialog.parentType} parentId={docsDialog.parentId} title={docsDialog.title} onClose={() => setDocsDialog(null)} />}
    </div>
  );
}

// ---------- helpers ----------
function filterTree(tree, q) {
  if (!q.trim()) return tree;
  const pat = q.toLowerCase();
  const match = (s) => (s || "").toString().toLowerCase().includes(pat);
  return tree.filter((c) => {
    if (match(c.customer_code) || match(c.name) || match(c.pan) || match(c.cin) || match(c.main_email) || match(c.main_phone)) return true;
    return (c.sites || []).some((s) => match(s.site_code) || match(s.gst) || match(s.city) || match(s.state) || match(s.plant_name)
      || (s.contacts || []).some((ct) => match(ct.name) || match(ct.mobile) || match(ct.email) || match(ct.designation)));
  });
}

function KPI({ label, value, icon: Icon, tone = "neutral" }) {
  const c = { primary: "text-primary", success: "text-success", danger: "text-destructive", neutral: "text-foreground" }[tone];
  return (
    <div className="bg-card border border-border rounded-sm p-4 flex items-center gap-3">
      <div className={cn("h-10 w-10 grid place-items-center rounded-sm bg-muted/60", c)}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className={cn("font-display font-black text-3xl tabular leading-none mt-0.5", c)}>{value}</div>
      </div>
    </div>
  );
}

function ClientNode({ client, isOpen, onToggle, onEdit, onAddSite, onOpenDocs, onResubmit, onOpenApproval, onEditSite, onOpenSiteDocs, onDeleteSite, onAddContact, onEditContact, onDeleteContact }) {
  const isPending = client.status === "pending_approval";
  const isRejected = client.status === "rejected";
  return (
    <div className="border-b border-border last:border-b-0" data-testid={`client-node-${client.id}`}>
      <div className="flex items-center gap-3 p-4 hover:bg-muted/30">
        <button onClick={onToggle} className="text-muted-foreground hover:text-foreground" data-testid={`client-toggle-${client.id}`}>
          {isOpen ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>
        <Building2 className="h-5 w-5 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono-data text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded-sm font-bold">{client.customer_code || "—"}</span>
            <span className="font-display font-bold">{client.name}</span>
            <StatusBadge text={(client.status || "active").replaceAll("_", " ")} tone={STATUS_TONE[client.status] || "neutral"} />
            {client.category && <span className="text-[10px] uppercase tracking-wider text-muted-foreground">· {client.category}</span>}
            {client.approval_id && (
              <button
                type="button"
                onClick={onOpenApproval}
                className="text-[10px] font-bold uppercase tracking-wider text-chart-3 hover:underline flex items-center gap-1"
                data-testid={`client-approval-${client.id}`}
              >
                <ClipboardCheck className="h-3 w-3" /> View approval
              </button>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {client.sites?.length || 0} site{client.sites?.length !== 1 ? "s" : ""}
            {client.pan && <span> · PAN {client.pan}</span>}
            {client.main_contact && <span> · {client.main_contact}</span>}
            {isRejected && client.reject_reason && <span className="text-destructive"> · {client.reject_reason}</span>}
          </div>
          {isPending && (
            <div className="mt-1 text-[10px] font-bold uppercase tracking-wider text-warning flex items-center gap-1" data-testid={`client-pending-${client.id}`}>
              <ClipboardCheck className="h-3 w-3" /> Awaiting onboarding approval — pipeline activities limited.
            </div>
          )}
        </div>
        <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={onOpenDocs} data-testid={`client-docs-${client.id}`}>
          <FolderArchive className="h-3.5 w-3.5 mr-1" /> Docs
        </Button>
        {isRejected && (
          <Button size="sm" className="h-8 rounded-sm" onClick={onResubmit} data-testid={`client-resubmit-${client.id}`}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> Resubmit
          </Button>
        )}
        <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={onEdit} data-testid={`client-edit-${client.id}`}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button size="sm" className="h-8 rounded-sm" onClick={onAddSite} data-testid={`client-addsite-${client.id}`}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Site
        </Button>
      </div>
      {isOpen && (
        <div className="bg-muted/20 px-4 pb-4 pl-12">
          {(client.sites || []).length === 0 && <div className="text-xs text-muted-foreground py-3">No sites yet — click "+ Site" to add the first one.</div>}
          {(client.sites || []).map((s) => (
            <SiteNode
              key={s.id}
              site={s}
              onEdit={() => onEditSite(s)}
              onOpenDocs={() => onOpenSiteDocs(s)}
              onDelete={() => onDeleteSite(s)}
              onAddContact={() => onAddContact(s.id)}
              onEditContact={(c) => onEditContact(s.id, c)}
              onDeleteContact={onDeleteContact}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SiteNode({ site, onEdit, onOpenDocs, onDelete, onAddContact, onEditContact, onDeleteContact }) {
  return (
    <div className="bg-card border border-border rounded-sm mt-3" data-testid={`site-node-${site.id}`}>
      <div className="flex items-center gap-3 p-3 border-b border-border">
        <MapPin className={cn("h-4 w-4", site.geo_lat && site.geo_lng ? "text-success" : "text-chart-3")} />
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono-data text-[11px] bg-chart-3/10 text-chart-3 px-1.5 py-0.5 rounded-sm font-bold">{site.site_code}</span>
            <span className="font-display font-bold text-sm">{site.name}</span>
            <StatusBadge text={site.status || "active"} tone={STATUS_TONE[site.status] || "neutral"} />
            {site.geo_lat && site.geo_lng && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-success flex items-center gap-0.5"><MapPin className="h-2.5 w-2.5" /> geo</span>
            )}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {site.city || "—"}, {site.state || "—"} · GST {site.gst || "—"}
            {site.payment_terms && <span> · {site.payment_terms}</span>}
            {site.credit_limit > 0 && <span> · Credit ₹ {Number(site.credit_limit).toLocaleString("en-IN")}</span>}
          </div>
        </div>
        <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={onOpenDocs} data-testid={`site-docs-${site.id}`}>
          <FolderArchive className="h-3 w-3" />
        </Button>
        <Button variant="outline" size="sm" className="h-7 rounded-sm" onClick={onEdit} data-testid={`site-edit-${site.id}`}>
          <Pencil className="h-3 w-3" />
        </Button>
        <Button variant="outline" size="sm" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={onDelete} data-testid={`site-delete-${site.id}`}>
          <Trash2 className="h-3 w-3" />
        </Button>
        <Button size="sm" className="h-7 rounded-sm" onClick={onAddContact} data-testid={`site-addcontact-${site.id}`}>
          <Plus className="h-3 w-3 mr-1" /> Contact
        </Button>
      </div>
      {(site.contacts || []).length > 0 && (
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Designation</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Department</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Mobile</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Email</TableHead>
              <TableHead className="w-20"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {site.contacts.map((c) => (
              <TableRow key={c.id} className="hover:bg-muted/30" data-testid={`contact-row-${c.id}`}>
                <TableCell className="text-sm font-semibold">{c.name}</TableCell>
                <TableCell className="text-sm">{c.designation || "—"}</TableCell>
                <TableCell><StatusBadge text={c.department || "—"} tone="info" /></TableCell>
                <TableCell className="font-mono-data text-xs">{c.mobile || "—"}</TableCell>
                <TableCell className="text-xs">{c.email || "—"}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => onEditContact(c)} data-testid={`contact-edit-${c.id}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => onDeleteContact(c)} data-testid={`contact-delete-${c.id}`}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function ClientDialog({ initial, onClose, onSaved }) {
  const isEdit = !!initial;
  const [form, setForm] = useState({
    name: initial?.name || "",
    category: initial?.category || "",
    pan: initial?.pan || "",
    cin: initial?.cin || "",
    corporate_address: initial?.corporate_address || "",
    main_contact: initial?.main_contact || "",
    main_email: initial?.main_email || "",
    main_phone: initial?.main_phone || "",
    credit_limit: initial?.credit_limit || 0,
    status: initial?.status || "active",
  });
  const save = async () => {
    try {
      if (isEdit) await api.put(`/clients/${initial.id}`, form);
      else await api.post("/clients", form);
      toast.success(isEdit ? "Client updated" : "Client created — code auto-assigned");
      onSaved(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">{isEdit ? `Edit ${initial.customer_code}` : "New Client"}</DialogTitle>
          <DialogDescription className="sr-only">Parent client master record.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2">
          {isEdit && <Field label="Customer Code (read-only)" value={initial.customer_code} disabled />}
          <Field label="Client Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} full={!isEdit} testId="client-field-name" />
          <SelectField label="Category" value={form.category} options={CATEGORIES} onChange={(v) => setForm({ ...form, category: v })} testId="client-field-category" />
          <Field label="PAN" value={form.pan} onChange={(v) => setForm({ ...form, pan: v })} testId="client-field-pan" />
          <Field label="CIN" value={form.cin} onChange={(v) => setForm({ ...form, cin: v })} testId="client-field-cin" />
          <TextareaField label="Corporate Office Address" value={form.corporate_address} onChange={(v) => setForm({ ...form, corporate_address: v })} full testId="client-field-corporate_address" />
          <Field label="Main Contact" value={form.main_contact} onChange={(v) => setForm({ ...form, main_contact: v })} testId="client-field-main_contact" />
          <Field label="Main Phone" value={form.main_phone} onChange={(v) => setForm({ ...form, main_phone: v })} testId="client-field-main_phone" />
          <Field label="Main Email" value={form.main_email} onChange={(v) => setForm({ ...form, main_email: v })} testId="client-field-main_email" />
          <Field label="Credit Limit (₹)" type="number" value={form.credit_limit} onChange={(v) => setForm({ ...form, credit_limit: v })} />
          <SelectField label="Status" value={form.status} options={STATUSES} onChange={(v) => setForm({ ...form, status: v })} />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={save} data-testid="client-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SiteDialog({ initial, clientId, onClose, onSaved }) {
  const isEdit = !!initial;
  const [form, setForm] = useState({
    name: initial?.name || "", city: initial?.city || "", state: initial?.state || "",
    state_code: initial?.state_code || "", gst: initial?.gst || "", pan: initial?.pan || "",
    billing_address: initial?.billing_address || "", shipping_address: initial?.shipping_address || "",
    plant_name: initial?.plant_name || "", payment_terms: initial?.payment_terms || "",
    credit_limit: initial?.credit_limit || 0, geo_lat: initial?.geo_lat || "", geo_lng: initial?.geo_lng || "",
    status: initial?.status || "active",
  });
  const save = async () => {
    try {
      if (isEdit) await api.put(`/sites/${initial.id}`, form);
      else await api.post(`/clients/${clientId}/sites`, form);
      toast.success(isEdit ? "Site updated" : "Site created — code auto-assigned");
      onSaved(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">{isEdit ? `Edit ${initial.site_code}` : "New Site"}</DialogTitle>
          <DialogDescription className="sr-only">Sub-location under parent client.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2 max-h-[60vh] overflow-y-auto">
          {isEdit && <Field label="Site Code (read-only)" value={initial.site_code} disabled />}
          <Field label="Site Name (auto if blank)" value={form.name} onChange={(v) => setForm({ ...form, name: v })} full={!isEdit} testId="site-field-name" />
          <Field label="City" value={form.city} onChange={(v) => setForm({ ...form, city: v })} testId="site-field-city" />
          <Field label="State" value={form.state} onChange={(v) => setForm({ ...form, state: v })} testId="site-field-state" />
          <Field label="State Code (GST)" value={form.state_code} onChange={(v) => setForm({ ...form, state_code: v })} />
          <Field label="GSTIN" value={form.gst} onChange={(v) => setForm({ ...form, gst: v.toUpperCase() })} testId="site-field-gst" />
          <Field label="PAN" value={form.pan} onChange={(v) => setForm({ ...form, pan: v.toUpperCase() })} />
          <Field label="Plant / Factory Name" value={form.plant_name} onChange={(v) => setForm({ ...form, plant_name: v })} />
          <TextareaField label="Billing Address" value={form.billing_address} onChange={(v) => setForm({ ...form, billing_address: v })} full />
          <TextareaField label="Shipping Address" value={form.shipping_address} onChange={(v) => setForm({ ...form, shipping_address: v })} full />
          <Field label="Payment Terms" value={form.payment_terms} onChange={(v) => setForm({ ...form, payment_terms: v })} />
          <Field label="Credit Limit (₹)" type="number" value={form.credit_limit} onChange={(v) => setForm({ ...form, credit_limit: v })} />
          <div className="md:col-span-2 flex flex-col gap-1.5">
            <Label className="text-xs uppercase tracking-wider">Geo Location · Click map or drag pin</Label>
            <LeafletPinEditor
              lat={form.geo_lat}
              lng={form.geo_lng}
              onChange={({ lat, lng }) => setForm({ ...form, geo_lat: lat, geo_lng: lng })}
              height={180}
            />
            <div className="grid grid-cols-2 gap-2">
              <Field label="Geo Lat" value={form.geo_lat} onChange={(v) => setForm({ ...form, geo_lat: v })} testId="site-field-geo-lat" />
              <Field label="Geo Lng" value={form.geo_lng} onChange={(v) => setForm({ ...form, geo_lng: v })} testId="site-field-geo-lng" />
            </div>
          </div>
          <SelectField label="Status" value={form.status} options={STATUSES} onChange={(v) => setForm({ ...form, status: v })} />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={save} data-testid="site-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ContactDialog({ initial, siteId, onClose, onSaved }) {
  const isEdit = !!initial;
  const [form, setForm] = useState({
    name: initial?.name || "", designation: initial?.designation || "",
    department: initial?.department || "Management", mobile: initial?.mobile || "",
    alt_mobile: initial?.alt_mobile || "", email: initial?.email || "",
    whatsapp: initial?.whatsapp || "", reporting_to: initial?.reporting_to || "",
    remarks: initial?.remarks || "",
  });
  const save = async () => {
    if (!form.name?.trim()) { toast.error("Name is required"); return; }
    try {
      if (isEdit) await api.put(`/contacts/${initial.id}`, form);
      else await api.post(`/sites/${siteId}/contacts`, form);
      toast.success(isEdit ? "Contact updated" : "Contact added");
      onSaved(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display">{isEdit ? "Edit Contact" : "New Contact Person"}</DialogTitle>
          <DialogDescription className="sr-only">Department-tagged contact under a site.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2">
          <Field label="Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} full testId="contact-field-name" />
          <Field label="Designation" value={form.designation} onChange={(v) => setForm({ ...form, designation: v })} testId="contact-field-designation" />
          <SelectField label="Department" value={form.department} options={CONTACT_DEPTS} onChange={(v) => setForm({ ...form, department: v })} testId="contact-field-department" />
          <Field label="Mobile" value={form.mobile} onChange={(v) => setForm({ ...form, mobile: v })} testId="contact-field-mobile" />
          <Field label="Alt Mobile" value={form.alt_mobile} onChange={(v) => setForm({ ...form, alt_mobile: v })} />
          <Field label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testId="contact-field-email" />
          <Field label="WhatsApp" value={form.whatsapp} onChange={(v) => setForm({ ...form, whatsapp: v })} />
          <Field label="Reporting To" value={form.reporting_to} onChange={(v) => setForm({ ...form, reporting_to: v })} />
          <TextareaField label="Remarks" value={form.remarks} onChange={(v) => setForm({ ...form, remarks: v })} full />
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={save} data-testid="contact-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value, onChange, disabled, type = "text", full, testId }) {
  return (
    <div className={cn("flex flex-col gap-1.5", full && "md:col-span-2")}>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <Input value={value ?? ""} disabled={disabled} type={type} onChange={(e) => onChange && onChange(e.target.value)} className="h-9 rounded-sm" data-testid={testId} />
    </div>
  );
}
function TextareaField({ label, value, onChange, full, testId }) {
  return (
    <div className={cn("flex flex-col gap-1.5", full && "md:col-span-2")}>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm" data-testid={testId} />
    </div>
  );
}
function SelectField({ label, value, options, onChange, testId }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid={testId}>
        <option value=""></option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
