import { useEffect, useMemo, useState } from "react";
import { Plus, Search, ChevronRight, ShoppingCart, FileText, AlertTriangle, Briefcase } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import RowAttachments from "@/components/RowAttachments";
import { api } from "@/lib/api";
import { DepartmentSelect } from "@/components/DepartmentSelect";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { toneFor } from "@/lib/statusTone";

const STATUS_TONE = {
  open: "info", under_review: "primary", submitted: "primary",
  negotiation: "warning", hold: "neutral", lost: "danger", won: "success",
};
const STATUSES = ["open", "under_review", "submitted", "negotiation", "hold", "lost", "won"];

const RFQ_TYPES = ["supply", "service", "supply_service"];
const SERVICE_CATEGORIES = ["scaffolding", "painting", "roof_sheeting", "insulation", "rope_access"];
const PRIORITIES = ["high", "medium", "low"];
const PRIORITY_TONE = { high: "danger", medium: "warning", low: "success" };

const initialForm = () => ({
  client_id: "",
  site_id: "",
  customer: "",
  contact_person: "",
  contact_email: "",
  contact_phone: "",
  site_location: "",
  customer_enquiry_no: "",
  enquiry_date: new Date().toISOString().slice(0, 10),
  rfq_type: [],
  service_categories: [],
  submission_deadline: "",
  bid_closing_date: "",
  priority: "medium",
  scope_of_work: "",
  technical_requirements: "",
  material_requirements: "",
  site_conditions: "",
  special_instructions: "",
  commercial_notes: "",
  expected_value: 0,
});

export default function Enquiries() {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [sites, setSites] = useState([]);
  const [pulse, setPulse] = useState(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm());
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertForm, setConvertForm] = useState({ customer_po: "", contract_value: 0, payment_terms: "Net 30", create_project: true });
  const [selected, setSelected] = useState(null);
  const [attachOpen, setAttachOpen] = useState(null);   // an enquiry row

  const load = async () => {
    try {
      const [eq, cl, s, p] = await Promise.all([
        api.get("/enquiries"),
        api.get("/clients"),
        api.get("/sites"),
        api.get("/sales/enquiry-pulse"),
      ]);
      setRows(eq.data || []);
      setClients(cl.data || []);
      setSites(s.data || []);
      setPulse(p.data || null);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { load(); }, []);

  const siteMap = useMemo(() => Object.fromEntries(sites.map((s) => [s.id, s])), [sites]);
  const clientMap = useMemo(() => Object.fromEntries(clients.map((c) => [c.id, c])), [clients]);

  // When client_id changes — clear site & customer, prefill customer name
  const pickClient = (clientId) => {
    const c = clientMap[clientId];
    setForm((f) => ({
      ...f,
      client_id: clientId,
      site_id: "",
      customer: c?.name || "",
      site_location: "",
      contact_person: "",
      contact_email: "",
      contact_phone: "",
    }));
  };

  // When site_id changes, auto-fill snapshot fields client-side too for UX preview
  const pickSite = async (siteId) => {
    const s = siteMap[siteId];
    if (!s) { setForm((f) => ({ ...f, site_id: "" })); return; }
    // pull primary contact
    let contact = {};
    try {
      const { data } = await api.get(`/clients/search?q=${encodeURIComponent(s.client_name || "")}`);
      contact = data.contacts.find((c) => c.site_id === siteId) || {};
    } catch (e) { /* ignore */ }
    setForm((f) => ({
      ...f,
      site_id: siteId,
      client_id: s.client_id || f.client_id,
      customer: s.client_name || f.customer,
      site_location: s.city || s.state || f.site_location,
      contact_person: contact.name || f.contact_person,
      contact_email: contact.email || f.contact_email,
      contact_phone: contact.mobile || f.contact_phone,
    }));
  };

  const create = async () => {
    if (!form.client_id) { toast.error("Client is required — pick from the master"); return; }
    if (!form.site_id)   { toast.error("Client Site is required — pick from the master"); return; }
    try {
      const { data } = await api.post("/enquiries", { ...form, expected_value: Number(form.expected_value) || 0, service_type: form.rfq_type.includes("supply_service") ? "sales_services" : (form.rfq_type.includes("service") ? "services" : "sales") });
      toast.success(`Enquiry ${data.enquiry_no} created${data.quotation_no ? ` · auto-quote ${data.quotation_no}` : ""}`);
      setOpen(false);
      setForm(initialForm());
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const setStatus = async (enq, status) => {
    try {
      await api.post(`/enquiries/${enq.id}/status`, { status });
      toast.success(`Status → ${status.replaceAll("_", " ")}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Status change failed"); }
  };

  const openConvert = (enq) => {
    setSelected(enq);
    setConvertForm({ customer_po: "", contract_value: enq.expected_value || 0, payment_terms: "Net 30", create_project: true });
    setConvertOpen(true);
  };

  const convert = async () => {
    try {
      const { data } = await api.post(`/enquiries/${selected.id}/convert`, { ...convertForm, contract_value: Number(convertForm.contract_value) || 0 });
      toast.success(`Order ${data.order.order_no}${data.project ? ` + Project ${data.project.code}` : ""}`);
      setConvertOpen(false);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Conversion failed"); }
  };

  const filtered = rows.filter((r) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return [r.enquiry_no, r.customer, r.site_location, r.status, r.customer_enquiry_no, r.priority, ...(r.service_categories || []), ...(r.rfq_type || [])]
      .some((v) => String(v ?? "").toLowerCase().includes(q));
  });

  return (
    <div className="space-y-6" data-testid="enquiries-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Sales · Pipeline</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Enquiries</h1>
        <p className="text-sm text-muted-foreground mt-1">Capture every RFQ with full scope. Each enquiry auto-creates a draft quotation.</p>
      </div>

      {pulse && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3" data-testid="enq-pulse">
          <PulseKpi label="Total" value={pulse.kpis.total} icon={Briefcase} />
          <PulseKpi label="Open" value={pulse.kpis.open} icon={FileText} tone="info" />
          <PulseKpi label="Won" value={pulse.kpis.won} tone="success" />
          <PulseKpi label="Lost" value={pulse.kpis.lost} tone="danger" />
          <PulseKpi label="Pending Quotes" value={pulse.kpis.pending_quotations} tone="warning" />
          <PulseKpi label="Deadline ≤ 7d" value={pulse.kpis.deadline_approaching} icon={AlertTriangle} tone="danger" />
        </div>
      )}

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search by code, client, service, RFQ type…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="enquiries-search" />
          </div>
          <div className="ml-auto">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="h-9 rounded-sm" data-testid="enquiries-add"><Plus className="h-4 w-4 mr-1" /> New Enquiry</Button>
              </DialogTrigger>
              <EnquiryDialog
                form={form}
                setForm={setForm}
                clients={clients}
                sites={sites}
                pickClient={pickClient}
                pickSite={pickSite}
                onClose={() => setOpen(false)}
                onSave={create}
              />
            </Dialog>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">Enquiry #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Client / Site</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">RFQ Type</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Services</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Priority</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Deadline</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Quote</TableHead>
                <TableHead className="text-right w-44">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-10">No enquiries yet.</TableCell></TableRow>
              )}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`enquiry-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm">{r.enquiry_no}<div className="text-[10px] text-muted-foreground">{r.customer_enquiry_no || ""}</div></TableCell>
                  <TableCell className="text-sm font-semibold">
                    {r.customer}
                    <div className="text-[11px] text-muted-foreground font-normal">{r.site_code ? `${r.site_code} · ${r.site_location || ""}` : (r.site_location || "")}</div>
                  </TableCell>
                  <TableCell className="text-xs">{(r.rfq_type || []).join(", ").replaceAll("_", " ") || "—"}</TableCell>
                  <TableCell className="text-xs">{(r.service_categories || []).join(", ").replaceAll("_", " ") || "—"}</TableCell>
                  <TableCell>{r.priority && <StatusBadge text={r.priority} tone={PRIORITY_TONE[r.priority]} />}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.submission_deadline || r.deadline || "—"}</TableCell>
                  <TableCell><StatusBadge text={r.status?.replaceAll("_", " ")} tone={STATUS_TONE[r.status] || "neutral"} /></TableCell>
                  <TableCell className="font-mono-data text-xs">{r.quotation_no ? <StatusBadge text={r.quotation_no} tone="info" /> : "—"}</TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1 items-center">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setAttachOpen(r)} title="Attachments" data-testid={`enquiry-attach-${r.id}`}>
                        <FileText className="h-3.5 w-3.5" />
                      </Button>
                      <select
                        className="h-7 rounded-sm border border-input bg-background px-1.5 text-xs"
                        value={r.status}
                        onChange={(e) => setStatus(r, e.target.value)}
                        data-testid={`enquiry-status-${r.id}`}
                      >
                        {STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
                      </select>
                      {r.status === "won" && !r.order_id && (
                        <Button size="sm" className="h-7 rounded-sm" onClick={() => openConvert(r)} data-testid={`enquiry-convert-${r.id}`}>
                          <ShoppingCart className="h-3 w-3 mr-1" /> Convert
                        </Button>
                      )}
                      {r.order_id && <StatusBadge text={`→ ${r.project_code || r.order_no}`} tone="success" />}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Convert dialog */}
      <Dialog open={convertOpen} onOpenChange={setConvertOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><ChevronRight className="h-4 w-4 text-primary" />Convert {selected?.enquiry_no} → Order</DialogTitle>
            <DialogDescription className="sr-only">Convert a Won enquiry into an Order (and optionally a Project).</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <SmallField label="Customer PO" value={convertForm.customer_po} onChange={(v) => setConvertForm({ ...convertForm, customer_po: v })} testid="convert-po" />
            <SmallField label="Contract Value" value={convertForm.contract_value} onChange={(v) => setConvertForm({ ...convertForm, contract_value: v })} testid="convert-value" type="number" />
            <SmallField label="Payment Terms" value={convertForm.payment_terms} onChange={(v) => setConvertForm({ ...convertForm, payment_terms: v })} testid="convert-terms" full />
            <div className="col-span-2 flex items-center gap-2">
              <input id="create-project" type="checkbox" checked={convertForm.create_project} onChange={(e) => setConvertForm({ ...convertForm, create_project: e.target.checked })} className="h-4 w-4" data-testid="convert-create-project" />
              <Label htmlFor="create-project" className="text-xs uppercase tracking-wider">Auto-create Project (PRJ-YYYY-####)</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setConvertOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={convert} data-testid="convert-confirm">Convert</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Attachments side-panel using existing RowAttachments component */}
      {attachOpen && (
        <Dialog open onOpenChange={(o) => !o && setAttachOpen(null)}>
          <DialogContent className="max-w-2xl rounded-sm">
            <DialogHeader>
              <DialogTitle className="font-display">{attachOpen.enquiry_no} — Documents</DialogTitle>
              <DialogDescription className="sr-only">Upload RFQ documents, BOQ, drawings, specs.</DialogDescription>
            </DialogHeader>
            <RowAttachments parentType="enquiries" parentId={attachOpen.id} />
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function PulseKpi({ label, value, icon: Icon = Briefcase, tone = "neutral" }) {
  const c = { primary: "text-primary", success: "text-success", danger: "text-destructive", warning: "text-warning", info: "text-chart-3", neutral: "text-foreground" }[tone];
  return (
    <div className="bg-card border border-border rounded-sm p-3 flex items-center gap-2">
      <div className={cn("h-8 w-8 grid place-items-center rounded-sm bg-muted/60", c)}><Icon className="h-4 w-4" /></div>
      <div>
        <div className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className={cn("font-display font-black text-xl tabular leading-none", c)}>{value ?? 0}</div>
      </div>
    </div>
  );
}

function EnquiryDialog({ form, setForm, clients, sites, pickClient, pickSite, onClose, onSave }) {
  // Show only sites for the selected client. If none picked, show empty (forces user to pick client first).
  const filteredSites = (sites || []).filter((s) => s.client_id === form.client_id);
  const clientOptions = (clients || []).map((c) => ({
    value: c.id,
    label: `${c.customer_code || ""} · ${c.name}`.trim(),
  }));
  const siteOptions = filteredSites.map((s) => {
    const display = s.name || s.site_name || `${s.client_name || ""}${s.city ? " — " + s.city : ""}`;
    return {
      value: s.id,
      label: `${s.site_code} · ${display}${s.gst ? " (GST " + s.gst + ")" : ""}`,
    };
  });
  return (
    <DialogContent className="max-w-3xl rounded-sm max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="font-display">New Enquiry</DialogTitle>
        <DialogDescription className="sr-only">Capture a new RFQ. Pick a client and a customer site (both mandatory).</DialogDescription>
      </DialogHeader>

      {/* Section: Customer */}
      <Section title="Customer & Site">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <Label className="text-xs uppercase tracking-wider">Client (master) <span className="text-destructive">*</span></Label>
            <select
              className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1"
              value={form.client_id}
              onChange={(e) => pickClient(e.target.value)}
              data-testid="enq-client-id"
              required
            >
              <option value="">— pick a client —</option>
              {clientOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Customer Site <span className="text-destructive">*</span></Label>
            <select
              className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1 disabled:opacity-60"
              value={form.site_id}
              onChange={(e) => pickSite(e.target.value)}
              data-testid="enq-site-id"
              disabled={!form.client_id}
              required
            >
              <option value="">{form.client_id ? "— pick a site —" : "— pick a client first —"}</option>
              {siteOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <SmallField label="Customer Name (snapshot)" value={form.customer} onChange={() => {}} testid="enq-customer" />
          <SmallField label="Site Location" value={form.site_location} onChange={(v) => setForm({ ...form, site_location: v })} testid="enq-site-location" />
          <SmallField label="Contact Person" value={form.contact_person} onChange={(v) => setForm({ ...form, contact_person: v })} testid="enq-contact" />
          <DepartmentSelect label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} testid="enq-department" />
          <SmallField label="Contact Email" value={form.contact_email} onChange={(v) => setForm({ ...form, contact_email: v })} testid="enq-email" />
          <SmallField label="Contact Phone" value={form.contact_phone} onChange={(v) => setForm({ ...form, contact_phone: v })} testid="enq-phone" />
        </div>
      </Section>

      {/* Section: Enquiry meta */}
      <Section title="Enquiry Reference">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <SmallField label="Customer Enquiry No" value={form.customer_enquiry_no} onChange={(v) => setForm({ ...form, customer_enquiry_no: v })} testid="enq-customer-no" />
          <SmallField label="Enquiry Date" type="date" value={form.enquiry_date} onChange={(v) => setForm({ ...form, enquiry_date: v })} testid="enq-date" />
          <SmallField label="Expected Value (₹)" type="number" value={form.expected_value} onChange={(v) => setForm({ ...form, expected_value: v })} testid="enq-value" />
          <SmallField label="Submission Deadline" type="date" value={form.submission_deadline} onChange={(v) => setForm({ ...form, submission_deadline: v })} testid="enq-deadline" />
          <SmallField label="Bid Closing Date" type="date" value={form.bid_closing_date} onChange={(v) => setForm({ ...form, bid_closing_date: v })} testid="enq-bid-close" />
          <div>
            <Label className="text-xs uppercase tracking-wider">Priority</Label>
            <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} data-testid="enq-priority">
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>
      </Section>

      {/* Section: RFQ type + services */}
      <Section title="RFQ Type & Service Categories">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ChipMulti label="RFQ Type" options={RFQ_TYPES} value={form.rfq_type} onChange={(arr) => setForm({ ...form, rfq_type: arr })} testid="enq-rfq" />
          <ChipMulti label="Service Categories" options={SERVICE_CATEGORIES} value={form.service_categories} onChange={(arr) => setForm({ ...form, service_categories: arr })} testid="enq-services" />
        </div>
      </Section>

      {/* Section: Scope */}
      <Section title="Scope & Specifications">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <TextareaField full label="Scope of Work" value={form.scope_of_work} onChange={(v) => setForm({ ...form, scope_of_work: v })} testid="enq-scope" />
          <TextareaField label="Technical Requirements" value={form.technical_requirements} onChange={(v) => setForm({ ...form, technical_requirements: v })} testid="enq-tech" />
          <TextareaField label="Material Requirements" value={form.material_requirements} onChange={(v) => setForm({ ...form, material_requirements: v })} testid="enq-material" />
          <TextareaField label="Site Conditions" value={form.site_conditions} onChange={(v) => setForm({ ...form, site_conditions: v })} testid="enq-site-cond" />
          <TextareaField label="Special Instructions" value={form.special_instructions} onChange={(v) => setForm({ ...form, special_instructions: v })} testid="enq-special" />
          <TextareaField full label="Commercial Notes" value={form.commercial_notes} onChange={(v) => setForm({ ...form, commercial_notes: v })} testid="enq-commercial" />
        </div>
      </Section>

      <DialogFooter>
        <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
        <Button className="rounded-sm" onClick={onSave} data-testid="enquiries-save">Save & Auto-Quote</Button>
      </DialogFooter>
    </DialogContent>
  );
}

function Section({ title, children }) {
  return (
    <div className="border-t border-border first:border-t-0 pt-3 mt-3 first:mt-0">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">{title}</div>
      {children}
    </div>
  );
}

function SmallField({ label, value, onChange, testid, type = "text", full }) {
  return (
    <div className={cn(full && "md:col-span-2")}>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
function TextareaField({ label, value, onChange, testid, full }) {
  return (
    <div className={cn(full && "md:col-span-2")}>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <textarea
        className="w-full min-h-[60px] rounded-sm border border-input bg-background p-2 text-sm mt-1"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testid}
      />
    </div>
  );
}
function ChipMulti({ label, options, value, onChange, testid }) {
  const arr = Array.isArray(value) ? value : [];
  const toggle = (opt) => onChange(arr.includes(opt) ? arr.filter((x) => x !== opt) : [...arr, opt]);
  return (
    <div>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <div className="flex flex-wrap gap-1.5 p-2 border border-input rounded-sm bg-background mt-1" data-testid={testid}>
        {options.map((o) => {
          const active = arr.includes(o);
          return (
            <button
              key={o}
              type="button"
              onClick={() => toggle(o)}
              className={cn(
                "text-[11px] font-bold uppercase tracking-wider px-2 py-1 rounded-sm border transition-colors",
                active ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary/40",
              )}
              data-testid={`${testid}-opt-${o}`}
            >
              {o.replaceAll("_", " ")}
            </button>
          );
        })}
      </div>
    </div>
  );
}
