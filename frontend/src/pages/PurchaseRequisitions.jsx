import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, FileText, Trash2, Send, ClipboardCheck, Briefcase, AlertTriangle, RefreshCw, X, Network, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import LineageTrail from "@/components/LineageTrail";
import { api } from "@/lib/api";
import { downloadPdf } from "@/lib/exports";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import SubmitWithDocsDialog from "@/components/SubmitWithDocsDialog";

const PR_STATUS_TONE = {
  draft: "neutral", pending_approval: "warning", approved: "success",
  rejected: "danger", pending_revision: "warning",
  rfq_initiated: "info", po_generated: "primary",
  partially_fulfilled: "warning", closed: "success",
};
const PRIORITY_TONE = { high: "danger", medium: "warning", low: "success" };

const blankItem = () => ({ category: "", category_id: "", name: "", item_id: "", item_code: "", description: "", quantity: 1, unit: "Nos", required_date: "", technical_specs: "", vendor_suggestion: "" });
const blankForm = () => ({
  department: "", project_id: "", project_code: "", site_id: "", site_code: "", priority: "medium",
  budget_reference: "", remarks: "",
  pr_date: new Date().toISOString().slice(0, 10),
  items: [blankItem()],
  submit_for_approval: false,  // Iter 63 — create as draft; user clicks Submit (which opens the docs-gate dialog)
});

export default function PurchaseRequisitions() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [lineageFor, setLineageFor] = useState(null);
  const [submitFor, setSubmitFor] = useState(null);
  const [dropdowns, setDropdowns] = useState({ departments: [], projects: [], sites: [], categories: [], items_by_category: {}, cost_centers: [] });

  const load = async () => {
    try { const { data } = await api.get("/procurement/prs"); setRows(data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load PRs"); }
  };
  const loadDropdowns = async (projectId) => {
    try {
      const url = projectId ? `/procurement/master/pr-dropdowns?project_id=${projectId}` : "/procurement/master/pr-dropdowns";
      const { data } = await api.get(url);
      setDropdowns(data);
    } catch (e) { /* non-fatal */ }
  };
  useEffect(() => { load(); loadDropdowns(); }, []);
  useEffect(() => { if (open) loadDropdowns(form.project_id || ""); /* eslint-disable-next-line */ }, [open, form.project_id]);

  const create = async () => {
    if (!form.items.length || !form.items[0].name) {
      toast.error("Add at least one item with a name");
      return;
    }
    try {
      const payload = { ...form, items: form.items.map((i) => ({ ...i, quantity: Number(i.quantity) || 0 })) };
      const { data } = await api.post("/procurement/prs", payload);
      toast.success(`${data.pr_number} created${data.approval_id ? " · sent for approval" : ""}`);
      setOpen(false);
      setForm(blankForm());
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const submit = async (pr) => {
    setSubmitFor(pr);
  };

  const remove = async (pr) => {
    if (!window.confirm(`Delete ${pr.pr_number}?`)) return;
    try { await api.delete(`/procurement/prs/${pr.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) =>
      [r.pr_number, r.department, r.project_code, r.site_code, r.priority, r.status, r.budget_reference]
        .some((v) => String(v ?? "").toLowerCase().includes(q))
      || (r.items || []).some((i) => String(i.name || "").toLowerCase().includes(q)),
    );
  }, [rows, query]);

  return (
    <div className="space-y-6" data-testid="prs-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Briefcase className="h-3 w-3" /> Procurement · Purchase Requisitions
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Purchase Requisitions</h1>
        <p className="text-sm text-muted-foreground mt-1">Capture material requests with multi-item BOQ. Submit for multi-level approval → RFQ → PO → GRN.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-80">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search PR #, department, item…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="prs-search" />
          </div>
          <div className="ml-auto">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="h-9 rounded-sm" data-testid="prs-add"><Plus className="h-4 w-4 mr-1" /> New PR</Button>
              </DialogTrigger>
              <PRDialog form={form} setForm={setForm} dropdowns={dropdowns} onSave={create} onClose={() => setOpen(false)} />
            </Dialog>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-[10px] uppercase tracking-wider">PR #</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Date</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Department · Project</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Items</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Priority</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider">Linked</TableHead>
                <TableHead className="text-right w-40">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-10">No PRs yet.</TableCell></TableRow>
              )}
              {filtered.map((r) => (
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`pr-row-${r.id}`}>
                  <TableCell className="font-mono-data text-sm font-bold">{r.pr_number}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.pr_date}</TableCell>
                  <TableCell className="text-sm">
                    {r.department || "—"}
                    <div className="text-[11px] text-muted-foreground">{r.project_code || r.site_code || ""}</div>
                  </TableCell>
                  <TableCell className="text-xs">{(r.items || []).length} item{r.items?.length === 1 ? "" : "s"}<div className="text-[10px] text-muted-foreground truncate max-w-[200px]">{(r.items || []).map((i) => i.name).filter(Boolean).join(", ")}</div></TableCell>
                  <TableCell><StatusBadge text={r.priority || "—"} tone={PRIORITY_TONE[r.priority]} /></TableCell>
                  <TableCell>
                    <StatusBadge text={(r.status || "draft").replaceAll("_", " ")} tone={PR_STATUS_TONE[r.status] || "neutral"} />
                    {r.status === "rejected" && r.reject_reason && (
                      <div className="text-[10px] text-destructive mt-0.5 flex items-center gap-1"><AlertTriangle className="h-2.5 w-2.5" /> {r.reject_reason}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-xs font-mono-data">
                    {r.rfq_number && <div>RFQ: {r.rfq_number}</div>}
                    {r.po_number && <div className="text-success">PO: {r.po_number}</div>}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1 items-center">
                      {(r.status === "draft" || r.status === "rejected") && (
                        <Button size="sm" className="h-7 rounded-sm" onClick={() => submit(r)} data-testid={`pr-submit-${r.id}`}>
                          <Send className="h-3 w-3 mr-1" /> Submit
                        </Button>
                      )}
                      {r.approval_id && (
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => navigate(`/app/approvals?id=${r.approval_id}`)} data-testid={`pr-approval-${r.id}`}>
                          <ClipboardCheck className="h-3 w-3 mr-1" /> Approval
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(r)} data-testid={`pr-lineage-${r.id}`} title="View end-to-end procurement lineage">
                        <Network className="h-3 w-3 mr-1" /> Lineage
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/prs/${r.id}/pdf`, `${r.pr_number}.pdf`)} data-testid={`pr-pdf-${r.id}`} title="Download PR PDF">
                        <FileDown className="h-3 w-3 mr-1" /> PDF
                      </Button>
                      {r.status === "approved" && (
                        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => navigate(`/app/rfqs?pr=${r.id}`)} data-testid={`pr-rfq-${r.id}`}>
                          <RefreshCw className="h-3 w-3 mr-1" /> RFQ
                        </Button>
                      )}
                      {!(r.status === "approved" || r.status === "rfq_initiated" || r.status === "po_generated") && (
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => remove(r)} data-testid={`pr-delete-${r.id}`}>
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

      <Dialog open={!!lineageFor} onOpenChange={(o) => !o && setLineageFor(null)}>
        <DialogContent className="max-w-5xl rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display">Procurement Lineage — {lineageFor?.pr_number}</DialogTitle>
            <DialogDescription>End-to-end traceability from this PR to every downstream RFQ, PO and GRN.</DialogDescription>
          </DialogHeader>
          {lineageFor && <LineageTrail kind="pr" recordId={lineageFor.id} />}
        </DialogContent>
      </Dialog>

      <SubmitWithDocsDialog
        open={!!submitFor}
        onOpenChange={(o) => !o && setSubmitFor(null)}
        title="Submit Purchase Requisition for Approval"
        description={submitFor && `${submitFor.pr_number} · ${(submitFor.items || []).length} item(s) · ${submitFor.priority || "medium"} priority`}
        endpoint={submitFor ? `/procurement/prs/${submitFor.id}/submit` : null}
        parentType="purchase_requisitions"
        parentId={submitFor?.id}
        ctaLabel="Submit PR"
        onSuccess={() => { setSubmitFor(null); load(); }}
        testidPrefix="pr-submit-docs"
      />
    </div>
  );
}

function PRDialog({ form, setForm, dropdowns, onSave, onClose }) {
  const updateItem = (idx, patch) => setForm({ ...form, items: form.items.map((it, i) => i === idx ? { ...it, ...patch } : it) });
  const addItem = () => setForm({ ...form, items: [...form.items, { category: "", category_id: "", name: "", item_id: "", item_code: "", description: "", quantity: 1, unit: "Nos", required_date: "", technical_specs: "", vendor_suggestion: "" }] });
  const removeItem = (idx) => setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });

  const sitesForProject = (dropdowns.sites || []).filter((s) =>
    !form.project_id || s.project_id === form.project_id || s.project_code === form.project_code);

  return (
    <DialogContent className="max-w-5xl rounded-sm max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="font-display">New Purchase Requisition</DialogTitle>
        <DialogDescription className="sr-only">Multi-item PR with dropdown-driven master data and cost center auto-tagging.</DialogDescription>
      </DialogHeader>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 py-2">
        <SelectField label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })}
                     options={(dropdowns.departments || []).map((d) => ({ value: d, label: d }))}
                     testid="pr-dept" placeholder="Select…" />
        <SelectField label="Project" value={form.project_id}
                     options={(dropdowns.projects || []).map((p) => ({ value: p.id, label: `${p.code || ""} · ${p.name}` }))}
                     onChange={(v) => {
                       const proj = (dropdowns.projects || []).find((p) => p.id === v);
                       setForm({ ...form, project_id: v, project_code: proj?.code || "", site_id: "", site_code: "" });
                     }}
                     testid="pr-project" placeholder="Select project…" />
        <SelectField label="Site" value={form.site_id}
                     options={sitesForProject.map((s) => ({ value: s.id, label: `${s.code || ""} · ${s.name || ""}` }))}
                     onChange={(v) => {
                       const site = sitesForProject.find((s) => s.id === v);
                       setForm({ ...form, site_id: v, site_code: site?.code || "" });
                     }}
                     testid="pr-site" placeholder={sitesForProject.length ? "Select site…" : "No sites for project"} />
        <Field label="PR Date" type="date" value={form.pr_date} onChange={(v) => setForm({ ...form, pr_date: v })} testid="pr-date" />
        <div>
          <Label className="text-xs uppercase tracking-wider">Priority</Label>
          <select className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} data-testid="pr-priority">
            {["high", "medium", "low"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <Field label="Budget Reference" value={form.budget_reference} onChange={(v) => setForm({ ...form, budget_reference: v })} testid="pr-budget" />
      </div>

      {form.project_id && (dropdowns.cost_centers || []).length > 0 && (
        <div className="text-[11px] text-muted-foreground border border-dashed border-border rounded-sm px-3 py-2 bg-primary/5">
          <b>Cost centers ready for this project:</b> {(dropdowns.cost_centers || []).length} active. Each line item is auto-tagged based on the selected category.
        </div>
      )}

      <div className="border-t border-border pt-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Line Items</div>
          <Button type="button" size="sm" variant="outline" className="h-7 rounded-sm" onClick={addItem} data-testid="pr-add-item">
            <Plus className="h-3 w-3 mr-1" /> Add item
          </Button>
        </div>
        <div className="space-y-3">
          {form.items.map((it, idx) => {
            const itemOptions = (dropdowns.items_by_category[it.category_id] || []).map((m) => ({ value: m.id, label: `${m.code} · ${m.name}` }));
            const ccMatch = (dropdowns.cost_centers || []).find((c) => c.category_id === it.category_id);
            return (
              <div key={idx} className="border border-border rounded-sm p-3 bg-muted/20 grid grid-cols-1 md:grid-cols-6 gap-2" data-testid={`pr-item-${idx}`}>
                <SelectField label="Category"
                             value={it.category_id}
                             options={(dropdowns.categories || []).map((c) => ({ value: c.id, label: `${c.code} · ${c.name}` }))}
                             onChange={(v) => {
                               const cat = (dropdowns.categories || []).find((c) => c.id === v);
                               updateItem(idx, { category_id: v, category: cat?.name || "", item_id: "", item_code: "", name: "" });
                             }}
                             testid={`pr-item-${idx}-cat`} placeholder="Select…" />
                <div className="md:col-span-2">
                  <Label className="text-[10px] uppercase tracking-wider">Item Name *</Label>
                  {itemOptions.length > 0 ? (
                    <div className="flex gap-1 mt-1">
                      <select value={it.item_id || ""} onChange={(e) => {
                        const itm = (dropdowns.items_by_category[it.category_id] || []).find((m) => m.id === e.target.value);
                        updateItem(idx, { item_id: itm?.id || "", item_code: itm?.code || "", name: itm?.name || "", unit: itm?.unit || it.unit });
                      }} className="h-9 flex-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`pr-item-${idx}-name-select`}>
                        <option value="">— from master —</option>
                        {itemOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                  ) : (
                    <Input value={it.name} onChange={(e) => updateItem(idx, { name: e.target.value })} className="h-9 rounded-sm mt-1" data-testid={`pr-item-${idx}-name`} placeholder={it.category_id ? "No master items — type to add custom" : "Select category first"} />
                  )}
                  {itemOptions.length > 0 && (
                    <Input value={it.name} onChange={(e) => updateItem(idx, { name: e.target.value, item_id: "", item_code: "" })} className="h-7 rounded-sm mt-1 text-[11px]" placeholder="…or type custom name" data-testid={`pr-item-${idx}-name`} />
                  )}
                </div>
                <Field label="Qty" type="number" value={it.quantity} onChange={(v) => updateItem(idx, { quantity: v })} testid={`pr-item-${idx}-qty`} />
                <Field label="Unit" value={it.unit} onChange={(v) => updateItem(idx, { unit: v })} testid={`pr-item-${idx}-unit`} />
                <Field label="Required by" type="date" value={it.required_date} onChange={(v) => updateItem(idx, { required_date: v })} testid={`pr-item-${idx}-req`} />
                <div className="md:col-span-3"><Field label="Description" value={it.description} onChange={(v) => updateItem(idx, { description: v })} /></div>
                <div className="md:col-span-2"><Field label="Tech Specs" value={it.technical_specs} onChange={(v) => updateItem(idx, { technical_specs: v })} /></div>
                <Field label="Suggested Vendor" value={it.vendor_suggestion} onChange={(v) => updateItem(idx, { vendor_suggestion: v })} />
                <div className="md:col-span-6 flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground">
                    {ccMatch
                      ? <>Cost Center: <b className="font-mono">{ccMatch.code}</b></>
                      : form.project_id && it.category_id
                        ? <>No cost center for this category in selected project — visit <b>Admin → Cost Centers</b> to auto-provision.</>
                        : "Pick project + category to auto-tag a cost center"}
                  </span>
                  {form.items.length > 1 && (
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-destructive" onClick={() => removeItem(idx)} data-testid={`pr-remove-item-${idx}`}>
                      <X className="h-3 w-3 mr-1" /> Remove
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <TextareaField label="Remarks" value={form.remarks} onChange={(v) => setForm({ ...form, remarks: v })} testid="pr-remarks" />
      </div>

      <div className="flex items-center gap-2 mt-3">
        <input id="pr-submit-now" type="checkbox" checked={form.submit_for_approval} onChange={(e) => setForm({ ...form, submit_for_approval: e.target.checked })} className="h-4 w-4" data-testid="pr-submit-now" />
        <Label htmlFor="pr-submit-now" className="text-xs uppercase tracking-wider">Submit for approval immediately</Label>
      </div>

      <DialogFooter>
        <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
        <Button className="rounded-sm" onClick={onSave} data-testid="pr-save">Save PR</Button>
      </DialogFooter>
    </DialogContent>
  );
}

function Field({ label, value, onChange, testid, type = "text" }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
function TextareaField({ label, value, onChange, testid }) {
  return (
    <div>
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


function SelectField({ label, value, onChange, options, testid, placeholder }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wider">{label}</Label>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}
              className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid={testid}>
        <option value="">{placeholder || "Select…"}</option>
        {(options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
