import { useEffect, useState } from "react";
import usePagedList from "@/hooks/usePagedList";
import TablePager from "@/components/TablePager";
import TableViewsMenu from "@/components/TableViewsMenu";
import useSearchLanding from "@/hooks/useSearchLanding";
import { useNavigate } from "react-router-dom";
import { Plus, Search, Trash2, Send, ClipboardCheck, Briefcase, AlertTriangle, RefreshCw, X, Network, FileDown, ListTree } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/DataTableShell";
import LineageTrail from "@/components/LineageTrail";
import RateContractHint from "@/components/RateContractHint";
import { api } from "@/lib/api";
import { downloadPdf } from "@/lib/exports";
import { toast } from "sonner";
import SubmitWithDocsDialog from "@/components/SubmitWithDocsDialog";
import { lookupGet } from "@/lib/lookups";

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
  const { rows, pagination, search: query, setSearch: setQuery, reload } = usePagedList("/procurement/prs", {}, {
    viewKey: "procurement_prs", errorLabel: "PRs",
    searchKeys: "pr_number,department,project_code,site_code,priority,status,budget_reference,items.name",
  });
  const [projMap, setProjMap] = useState({});
  useEffect(() => {
    lookupGet("/projects").then((res) => {
      const m = {};
      (res.data || []).forEach((p) => {
        const info = { code: p.code || p.project_code, name: p.name, manager: p.manager || p.project_manager_name };
        if (info.code) m[info.code] = info;
        m[p.id] = info;
      });
      setProjMap(m);
    }).catch(() => {});
  }, []);
  useSearchLanding(setQuery, [rows]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blankForm());
  const [lineageFor, setLineageFor] = useState(null);
  const [coverageFor, setCoverageFor] = useState(null);
  const [submitFor, setSubmitFor] = useState(null);
  const [dropdowns, setDropdowns] = useState({ departments: [], projects: [], sites: [], categories: [], items_by_category: {}, cost_centers: [] });

  const load = () => reload();
  const loadDropdowns = async (projectId) => {
    try {
      const url = projectId ? `/procurement/master/pr-dropdowns?project_id=${projectId}` : "/procurement/master/pr-dropdowns";
      const { data } = await api.get(url);
      setDropdowns(data);
    } catch { /* non-fatal */ }
  };
  useEffect(() => { loadDropdowns(); }, []);
  useEffect(() => { if (open) loadDropdowns(form.project_id || ""); }, [open, form.project_id]);

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

  const filtered = rows;

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
          <TableViewsMenu pagination={pagination} testidPrefix="prs" />
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
                <TableRow key={r.id} className="hover:bg-muted/30" data-testid={`pr-row-${r.id}`} data-row-id={r.id}>
                  <TableCell className="font-mono-data text-sm font-bold">{r.pr_number}</TableCell>
                  <TableCell className="font-mono-data text-xs">{r.pr_date}</TableCell>
                  <TableCell className="text-sm">
                    {r.department || "—"}
                    {(() => {
                      const p = projMap[r.project_code] || projMap[r.project_id];
                      const code = p?.code || r.project_code || r.site_code;
                      if (!code) return null;
                      return (
                        <div className="text-[11px] text-muted-foreground" data-testid={`pr-project-${r.id}`}>
                          <span className="font-medium text-foreground/80">{code}</span>
                          {p?.name && <span> · {p.name}</span>}
                          {p?.manager && <div className="text-[10px]">PM: {p.manager}</div>}
                        </div>
                      );
                    })()}
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
                      {["approved", "rfq_initiated", "partially_fulfilled", "po_generated", "closed"].includes(r.status) && (
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setCoverageFor(r)} data-testid={`pr-coverage-${r.id}`} title="Item-wise release map: RFQ / PO / pending">
                          <ListTree className="h-3 w-3 mr-1" /> Coverage
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setLineageFor(r)} data-testid={`pr-lineage-${r.id}`} title="View end-to-end procurement lineage">
                        <Network className="h-3 w-3 mr-1" /> Lineage
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => downloadPdf(`/procurement/prs/${r.id}/pdf`, `${r.pr_number}.pdf`)} data-testid={`pr-pdf-${r.id}`} title="Download PR PDF">
                        <FileDown className="h-3 w-3 mr-1" /> PDF
                      </Button>
                      {["approved", "rfq_initiated", "partially_fulfilled"].includes(r.status) && (
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
        <div className="px-4 py-2 border-t border-border"><TablePager pagination={pagination} testidPrefix="prs" /></div>
      </div>

      {coverageFor && <PRCoverageDialog pr={coverageFor} onClose={() => setCoverageFor(null)} />}
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

  // The backend already scopes sites to the selected project's client, so use them as-is.
  const sitesForProject = dropdowns.sites || [];

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
                     options={sitesForProject.map((s) => ({ value: s.id, label: `${s.site_code || ""} · ${s.name || ""}` }))}
                     onChange={(v) => {
                       const site = sitesForProject.find((s) => s.id === v);
                       setForm({ ...form, site_id: v, site_code: site?.site_code || "" });
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
            const vendorOptions = (dropdowns.vendors_by_category?.[it.category_id] || []);
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
                <div>
                  <Label className="text-[10px] uppercase tracking-wider">Suggested Vendor</Label>
                  {vendorOptions.length > 0 ? (
                    <>
                      <select value={vendorOptions.some((v) => v.name === it.vendor_suggestion) ? it.vendor_suggestion : ""}
                        onChange={(e) => updateItem(idx, { vendor_suggestion: e.target.value })}
                        className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1"
                        data-testid={`pr-item-${idx}-vendor-select`}>
                        <option value="">— select vendor —</option>
                        {vendorOptions.map((v) => <option key={v.id} value={v.name}>{v.vendor_code ? `${v.vendor_code} · ` : ""}{v.name}</option>)}
                      </select>
                      <Input value={vendorOptions.some((v) => v.name === it.vendor_suggestion) ? "" : it.vendor_suggestion}
                        onChange={(e) => updateItem(idx, { vendor_suggestion: e.target.value })}
                        className="h-7 rounded-sm mt-1 text-[11px]" placeholder="…or type custom vendor" data-testid={`pr-item-${idx}-vendor`} />
                    </>
                  ) : (
                    <Input value={it.vendor_suggestion} onChange={(e) => updateItem(idx, { vendor_suggestion: e.target.value })}
                      className="h-9 rounded-sm mt-1" data-testid={`pr-item-${idx}-vendor`}
                      placeholder={it.category_id ? "No vendors mapped to this category" : "Select category first"} />
                  )}
                </div>
                <div className="md:col-span-6">
                  <RateContractHint
                    itemId={it.item_id}
                    itemName={it.name}
                    onApply={(rc) => updateItem(idx, {
                      vendor_suggestion: rc.vendor_name,
                      unit: rc.unit || it.unit,
                      rate_contract_id: rc.rc_id,
                      rate_contract_rate: rc.rate,
                    })}
                  />
                  {it.rate_contract_id && (
                    <span className="ml-2 text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-sm px-1.5 py-0.5" data-testid={`pr-item-${idx}-rc-chip`}>
                      RC linked · {it.rate_contract_id.slice(0, 8)}
                    </span>
                  )}
                </div>
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

const COVERAGE_STATE = {
  pending_release: { label: "Pending Release", cls: "bg-amber-100 text-amber-800" },
  in_rfq: { label: "In RFQ", cls: "bg-sky-100 text-sky-700" },
  po_created: { label: "PO Created", cls: "bg-emerald-100 text-emerald-700" },
};

function PRCoverageDialog({ pr, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.get(`/procurement/prs/${pr.id}/coverage`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load coverage"));
  }, [pr.id]);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[85vh] overflow-y-auto" data-testid="pr-coverage-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Item Coverage — {pr.pr_number}</DialogTitle>
          <DialogDescription>Which items went into which RFQ / PO, and what is still pending release.</DialogDescription>
        </DialogHeader>
        {error && <div className="text-sm text-destructive py-4">{error}</div>}
        {!data && !error && <div className="text-sm text-muted-foreground py-4">Loading…</div>}
        {data && (
          <>
            <div className="flex flex-wrap gap-2 text-xs" data-testid="pr-coverage-summary">
              <span className="px-2 py-1 rounded-sm bg-muted font-semibold">{data.summary.total_items} item(s)</span>
              <span className="px-2 py-1 rounded-sm bg-sky-100 text-sky-700 font-semibold">{data.summary.released} released to RFQ</span>
              <span className="px-2 py-1 rounded-sm bg-emerald-100 text-emerald-700 font-semibold">{data.summary.po_created} with PO</span>
              <span className={`px-2 py-1 rounded-sm font-semibold ${data.summary.pending ? "bg-amber-100 text-amber-800" : "bg-muted text-muted-foreground"}`}>{data.summary.pending} pending release</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">#</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">RFQ</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">PO</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">State</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((it) => {
                  const st = COVERAGE_STATE[it.state] || COVERAGE_STATE.pending_release;
                  return (
                    <TableRow key={it.index} data-testid={`pr-coverage-row-${it.index}`}>
                      <TableCell className="text-xs text-muted-foreground">{it.index + 1}</TableCell>
                      <TableCell className="text-sm font-semibold">{it.name}</TableCell>
                      <TableCell className="text-xs tabular">{it.quantity} {it.unit}</TableCell>
                      <TableCell className="text-xs font-mono-data">
                        {it.releases.length === 0 ? "—" : it.releases.map((rl, k) => (
                          <div key={k}>{rl.rfq_number} <span className="text-[10px] text-muted-foreground">({(rl.rfq_status || "").replaceAll("_", " ")})</span></div>
                        ))}
                      </TableCell>
                      <TableCell className="text-xs font-mono-data">
                        {it.releases.some((rl) => rl.po_number) ? it.releases.filter((rl) => rl.po_number).map((rl, k) => (
                          <div key={k} className="text-success font-bold">{rl.po_number}{Number(rl.po_revision) > 0 ? ` (Rev ${rl.po_revision})` : ""} <span className="text-[10px] text-muted-foreground font-normal">({(rl.po_status || "").replaceAll("_", " ")})</span></div>
                        )) : "—"}
                      </TableCell>
                      <TableCell className="text-xs">{it.releases.map((rl) => rl.vendor).filter(Boolean).join(", ") || "—"}</TableCell>
                      <TableCell><span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded-sm ${st.cls}`} data-testid={`pr-coverage-state-${it.index}`}>{st.label}</span></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </>
        )}
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
