import { useEffect, useMemo, useState, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  FileText, Sparkles, Save, Send, Download, Plus, Trash2, Copy, Upload,
  ChevronLeft, ListChecks, Wand2, FileSearch, Mail, BadgeCheck, Layers,
  CheckCircle2, AlertTriangle, Eye, RotateCcw, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import SubmitWithDocsDialog from "@/components/SubmitWithDocsDialog";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const newSection = (service = "scaffolding", basis = "manpower_material") => ({
  id: "s_" + Math.random().toString(36).slice(2, 9),
  title: "",
  service, basis,
  notes: "",
  items: [],
});
const emptyItem = (preset = {}) => ({
  description: "", specification: "", unit: "Nos", hsn_sac: "9987",
  quantity: 1, rate: 0, discount_pct: 0, gst_pct: 18, remarks: "",
  ...preset,
});

export default function QuotationBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [quote, setQuote] = useState(null);
  const [presets, setPresets] = useState(null);
  const [conditions, setConditions] = useState([]);
  const [tab, setTab] = useState("header");
  const [saving, setSaving] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const debounceRef = useRef(null);

  // Load quote + presets + conditions in parallel
  useEffect(() => {
    (async () => {
      try {
        const [qRes, pRes, cRes] = await Promise.all([
          api.get(`/quotation-builder/${id}`),
          api.get(`/quotation-builder/presets`),
          api.get(`/quotation-builder/conditions`),
        ]);
        const q = qRes.data;
        // Ensure structure
        q.sections = q.sections || [];
        q.technical_conditions = q.technical_conditions || [];
        q.commercial_conditions = q.commercial_conditions || [];
        q.inclusions = q.inclusions || [];
        q.exclusions = q.exclusions || [];
        setQuote(q);
        setPresets(pRes.data);
        setConditions(cRes.data || []);
      } catch (e) { toast.error(e.response?.data?.detail || "Failed to load quotation"); }
    })();
  }, [id]);

  // Auto-recalc whenever sections / tax_mode / pct fields change (debounced local + remote sync)
  const recalcLocal = (q) => {
    const mode = q.tax_mode || "intra";
    let basic = 0, disc = 0, taxable = 0, cgst = 0, sgst = 0, igst = 0;
    (q.sections || []).forEach((sec) => {
      let sb = 0, sd = 0, st = 0, sg = 0, sgT = 0;
      (sec.items || []).forEach((it, i) => {
        const qty = +it.quantity || 0;
        const r = +it.rate || 0;
        const dp = +it.discount_pct || 0;
        const gp = +it.gst_pct || 0;
        const amt = qty * r;
        const da = amt * dp / 100;
        const ta = amt - da;
        let ic = 0, is = 0, ii = 0;
        if (mode === "inter") ii = ta * gp / 100;
        else { ic = ta * gp / 200; is = ta * gp / 200; }
        const tot = ta + ic + is + ii;
        it.sno = i + 1; it.amount = +amt.toFixed(2); it.discount_amount = +da.toFixed(2);
        it.taxable = +ta.toFixed(2); it.cgst = +ic.toFixed(2); it.sgst = +is.toFixed(2);
        it.igst = +ii.toFixed(2); it.gst_amount = +(ic + is + ii).toFixed(2); it.total = +tot.toFixed(2);
        sb += amt; sd += da; st += ta; sg += (ic + is + ii); sgT += tot;
        basic += amt; disc += da; taxable += ta; cgst += ic; sgst += is; igst += ii;
      });
      sec.subtotal_basic = +sb.toFixed(2); sec.subtotal_discount = +sd.toFixed(2);
      sec.subtotal_taxable = +st.toFixed(2); sec.subtotal_gst = +sg.toFixed(2); sec.subtotal_total = +sgT.toFixed(2);
    });
    const gst_total = cgst + sgst + igst;
    const raw = taxable + gst_total;
    const grand = Math.round(raw);
    q.totals = {
      basic: +basic.toFixed(2), discount: +disc.toFixed(2), taxable: +taxable.toFixed(2),
      cgst: +cgst.toFixed(2), sgst: +sgst.toFixed(2), igst: +igst.toFixed(2),
      gst_total: +gst_total.toFixed(2), round_off: +(grand - raw).toFixed(2),
      grand_total: grand,
      tds_pct: +q.tds_pct || 0,
      tds_amount_indicative: +(taxable * (+q.tds_pct || 0) / 100).toFixed(2),
      retention_pct: +q.retention_pct || 0,
      retention_amount_indicative: +(taxable * (+q.retention_pct || 0) / 100).toFixed(2),
    };
    q.total = grand;
    return q;
  };

  const updateAndRecalc = (patch) => {
    setQuote((prev) => {
      const next = { ...prev, ...patch };
      recalcLocal(next);
      // debounced server save
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => persist(next), 800);
      return next;
    });
  };

  const persist = async (q) => {
    try {
      setSaving(true);
      const payload = {
        client: q.client, client_state: q.client_state, contact_person: q.contact_person,
        contact_email: q.contact_email, project: q.project, scope_of_work: q.scope_of_work,
        date: q.date, valid_until: q.valid_until,
        service_categories: q.service_categories, rfq_type: q.rfq_type,
        sections: q.sections, tax_mode: q.tax_mode, tax_mode_locked: q.tax_mode_locked,
        technical_conditions: q.technical_conditions, commercial_conditions: q.commercial_conditions,
        inclusions: q.inclusions, exclusions: q.exclusions,
        payment_terms: q.payment_terms, validity_days: q.validity_days,
        advance_pct: q.advance_pct, retention_pct: q.retention_pct, tds_pct: q.tds_pct,
        warranty: q.warranty, delivery_timeline: q.delivery_timeline,
      };
      const { data } = await api.put(`/quotation-builder/${id}`, payload);
      setQuote(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Auto-save failed"); }
    finally { setSaving(false); }
  };

  const addSection = (service, basis) => {
    const items = (presets?.preset_items?.[service]?.[basis] || []).map((p) => emptyItem({
      description: p.description, unit: p.unit, hsn_sac: p.hsn_sac, gst_pct: p.gst_pct, quantity: p.quantity || 1, rate: p.rate || 0,
    }));
    const sec = { ...newSection(service, basis), title: `${service.replaceAll("_", " ")} · ${presets?.basis_labels?.[basis] || basis}`, items };
    updateAndRecalc({ sections: [...(quote.sections || []), sec], service_categories: Array.from(new Set([...(quote.service_categories || []), service])) });
  };

  const downloadPdf = async () => {
    try {
      const res = await api.get(`/quotation-builder/${id}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a"); a.href = url; a.download = `${quote.quote_number || "Quotation"}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("PDF download failed"); }
  };

  const [submitOpen, setSubmitOpen] = useState(false);

  const submitForApproval = () => setSubmitOpen(true);

  if (!quote || !presets) {
    return <div className="p-8 text-sm text-muted-foreground">Loading quotation builder…</div>;
  }

  const isLocked = ["won", "lost", "cancelled"].includes(quote.status);
  const statusTone = {
    draft: "bg-muted/40 text-muted-foreground border-border",
    under_review: "bg-amber-100 text-amber-900 border-amber-300",
    approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
    submitted: "bg-blue-100 text-blue-900 border-blue-300",
    won: "bg-emerald-200 text-emerald-900 border-emerald-400",
    lost: "bg-red-100 text-red-900 border-red-300",
    cancelled: "bg-red-100 text-red-900 border-red-300",
  }[quote.status] || "bg-muted/40 text-muted-foreground border-border";

  return (
    <div className="space-y-4" data-testid="quotation-builder-page">
      {/* Header bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={() => navigate("/app/quotations")} data-testid="qb-back">
          <ChevronLeft className="h-4 w-4 mr-1" /> Quotations
        </Button>
        <div className="flex-1">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary flex items-center gap-2">
            <Sparkles className="h-3 w-3" /> AI Quotation Builder
          </div>
          <h1 className="font-display font-black text-2xl tracking-tight flex items-center gap-3 mt-0.5">
            {quote.quote_number}
            <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm border ${statusTone}`} data-testid="qb-status">{quote.status?.replaceAll("_", " ")}</span>
            {saving && <span className="text-[10px] text-muted-foreground">saving…</span>}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={() => setAiOpen(true)} disabled={isLocked} data-testid="qb-ai-rfq">
            <Wand2 className="h-4 w-4 mr-1.5 text-primary" /> AI from RFQ
          </Button>
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={downloadPdf} data-testid="qb-download-pdf">
            <Download className="h-4 w-4 mr-1.5" /> PDF
          </Button>
          {quote.status === "draft" && (
            <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={submitForApproval} disabled={isLocked} data-testid="qb-submit-approval">
              <BadgeCheck className="h-4 w-4 mr-1.5" /> Approval
            </Button>
          )}
          <Button size="sm" className="h-9 rounded-sm" onClick={() => setSendOpen(true)} disabled={isLocked} data-testid="qb-send-client">
            <Send className="h-4 w-4 mr-1.5" /> Send to Client
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border flex gap-4 text-sm">
        {[
          ["header", "Header & Client"],
          ["sections", "Services & Line Items"],
          ["conditions", "Conditions & Terms"],
          ["preview", "Preview & Totals"],
        ].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`qb-tab-${k}`}
                  className={`pb-2 -mb-px font-semibold tracking-wide ${tab === k ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === "header" && (
        <HeaderForm quote={quote} update={updateAndRecalc} presets={presets} disabled={isLocked} />
      )}
      {tab === "sections" && (
        <SectionsEditor quote={quote} update={updateAndRecalc} presets={presets} addSection={addSection} disabled={isLocked} />
      )}
      {tab === "conditions" && (
        <ConditionsEditor quote={quote} update={updateAndRecalc} conditions={conditions} disabled={isLocked} />
      )}
      {tab === "preview" && (
        <PreviewBlock quote={quote} />
      )}

      {/* AI RFQ Dialog */}
      <AiRfqDialog open={aiOpen} onClose={() => setAiOpen(false)} quote={quote} update={updateAndRecalc} presets={presets} />
      <SendToClientDialog open={sendOpen} onClose={() => setSendOpen(false)} quote={quote} reload={async () => {
        const { data } = await api.get(`/quotation-builder/${id}`); setQuote(data);
      }} />
      <SubmitWithDocsDialog
        open={submitOpen}
        onOpenChange={setSubmitOpen}
        title="Submit Quotation for Approval"
        description={quote && `${quote.quote_number} · ${quote.client || ""} · ₹ ${Number(quote.total || 0).toLocaleString("en-IN")}`}
        endpoint={`/quotation-builder/${id}/submit-for-approval`}
        parentType="quotations"
        parentId={id}
        ctaLabel="Submit Quotation"
        onSuccess={async () => { const { data } = await api.get(`/quotation-builder/${id}`); setQuote(data); setSubmitOpen(false); }}
        testidPrefix="qb-submit-docs"
      />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Header & Client
// ──────────────────────────────────────────────────────────────────────────────
function HeaderForm({ quote, update, presets, disabled }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card title="Client & Site">
        <Field label="Client name *" value={quote.client} onChange={(v) => update({ client: v })} testid="qb-client" disabled={disabled} />
        <Field label="Site / project name" value={quote.site_name} onChange={(v) => update({ site_name: v })} disabled={disabled} />
        <Field label="Client state (for GST)" value={quote.client_state} onChange={(v) => update({ client_state: v })} testid="qb-client-state" disabled={disabled} />
        <Field label="Contact person" value={quote.contact_person} onChange={(v) => update({ contact_person: v })} disabled={disabled} />
        <Field label="Contact email" value={quote.contact_email} onChange={(v) => update({ contact_email: v })} disabled={disabled} />
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Tax mode</Label>
          <select value={quote.tax_mode || "intra"} disabled={disabled}
                  onChange={(e) => update({ tax_mode: e.target.value, tax_mode_locked: true })}
                  className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="qb-tax-mode">
            <option value="intra">Intra-state (CGST + SGST)</option>
            <option value="inter">Inter-state (IGST)</option>
          </select>
          <div className="flex items-center justify-between mt-1">
            <p className="text-[11px] text-muted-foreground">{quote.tax_mode_locked ? "Manual override · " : "Auto-detected · "}company ({quote.company_state || "—"}) vs client ({quote.client_state || "—"})</p>
            {quote.tax_mode_locked && (
              <button className="text-[11px] text-primary hover:underline" disabled={disabled}
                      onClick={() => update({ tax_mode_locked: false })} data-testid="qb-tax-auto">
                Auto-detect
              </button>
            )}
          </div>
        </div>
      </Card>
      <Card title="Quote details">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date" type="date" value={quote.date} onChange={(v) => update({ date: v })} disabled={disabled} />
          <Field label="Valid until" type="date" value={quote.valid_until} onChange={(v) => update({ valid_until: v })} disabled={disabled} />
          <Field label="Validity (days)" type="number" value={quote.validity_days} onChange={(v) => update({ validity_days: +v })} disabled={disabled} />
          <Field label="Submission deadline" type="date" value={quote.submission_deadline} onChange={(v) => update({ submission_deadline: v })} disabled={disabled} />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Scope of work</Label>
          <Textarea value={quote.project || quote.scope_of_work || ""} disabled={disabled}
                    onChange={(e) => update({ project: e.target.value, scope_of_work: e.target.value })}
                    className="rounded-sm mt-1 min-h-[100px]" data-testid="qb-scope" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Services covered</Label>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {(presets.services || []).map((s) => {
              const active = (quote.service_categories || []).includes(s);
              return (
                <button key={s} disabled={disabled}
                        className={`text-[11px] px-2.5 py-1 rounded-sm border ${active ? "border-primary bg-primary/10 text-primary font-semibold" : "border-border text-muted-foreground hover:border-primary/50"}`}
                        onClick={() => {
                          const cur = quote.service_categories || [];
                          update({ service_categories: active ? cur.filter((x) => x !== s) : [...cur, s] });
                        }}
                        data-testid={`qb-svc-chip-${s}`}>
                  {s.replaceAll("_", " ")}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <Card title="Payment & commercial">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Payment terms" value={quote.payment_terms} onChange={(v) => update({ payment_terms: v })} testid="qb-payment-terms" disabled={disabled} />
          <Field label="Advance %" type="number" value={quote.advance_pct} onChange={(v) => update({ advance_pct: +v })} disabled={disabled} />
          <Field label="Retention %" type="number" value={quote.retention_pct} onChange={(v) => update({ retention_pct: +v })} testid="qb-retention-pct" disabled={disabled} />
          <Field label="TDS %" type="number" value={quote.tds_pct} onChange={(v) => update({ tds_pct: +v })} disabled={disabled} />
          <Field label="Delivery / timeline" value={quote.delivery_timeline} onChange={(v) => update({ delivery_timeline: v })} disabled={disabled} />
          <Field label="Warranty" value={quote.warranty} onChange={(v) => update({ warranty: v })} disabled={disabled} />
        </div>
      </Card>

      <Card title="Live totals">
        <ul className="text-sm space-y-1">
          <li className="flex justify-between"><span className="text-muted-foreground">Basic</span><span className="tabular">{inr(quote.totals?.basic)}</span></li>
          <li className="flex justify-between"><span className="text-muted-foreground">Discount</span><span className="tabular">-{inr(quote.totals?.discount)}</span></li>
          <li className="flex justify-between"><span className="text-muted-foreground">Taxable</span><span className="tabular">{inr(quote.totals?.taxable)}</span></li>
          {quote.tax_mode === "intra" ? (
            <>
              <li className="flex justify-between"><span className="text-muted-foreground">CGST</span><span className="tabular">{inr(quote.totals?.cgst)}</span></li>
              <li className="flex justify-between"><span className="text-muted-foreground">SGST</span><span className="tabular">{inr(quote.totals?.sgst)}</span></li>
            </>
          ) : (
            <li className="flex justify-between"><span className="text-muted-foreground">IGST</span><span className="tabular">{inr(quote.totals?.igst)}</span></li>
          )}
          <li className="flex justify-between font-bold text-base border-t border-border pt-1.5 mt-2"><span>Grand Total</span><span className="text-primary tabular" data-testid="qb-grand-total">{inr(quote.totals?.grand_total)}</span></li>
          <li className="flex justify-between text-[11px] text-muted-foreground pt-2 border-t border-dashed border-border mt-1">
            <span>TDS {quote.totals?.tds_pct || 0}% (advisory)</span><span className="tabular">{inr(quote.totals?.tds_amount_indicative)}</span>
          </li>
          <li className="flex justify-between text-[11px] text-muted-foreground">
            <span>Retention {quote.totals?.retention_pct || 0}% (advisory)</span><span className="tabular">{inr(quote.totals?.retention_amount_indicative)}</span>
          </li>
        </ul>
      </Card>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Sections editor (multi-service quotation)
// ──────────────────────────────────────────────────────────────────────────────
function SectionsEditor({ quote, update, presets, addSection, disabled }) {
  const [addOpen, setAddOpen] = useState(false);
  const [pickService, setPickService] = useState("scaffolding");
  const [pickBasis, setPickBasis] = useState("manpower_material");

  const updateSection = (idx, patch) => {
    const sections = [...(quote.sections || [])];
    sections[idx] = { ...sections[idx], ...patch };
    update({ sections });
  };
  const deleteSection = (idx) => {
    if (!window.confirm("Delete this service section?")) return;
    update({ sections: (quote.sections || []).filter((_, i) => i !== idx) });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground"><Layers className="h-3.5 w-3.5 inline mr-1" /> {quote.sections?.length || 0} section(s)</span>
        <Button size="sm" className="ml-auto h-9 rounded-sm" disabled={disabled} onClick={() => setAddOpen(true)} data-testid="qb-add-section">
          <Plus className="h-4 w-4 mr-1" /> Add Service Section
        </Button>
      </div>

      {(quote.sections || []).length === 0 && (
        <div className="text-center py-10 border border-dashed border-border rounded-sm">
          <p className="text-sm text-muted-foreground">No service section yet. Pick a service + RFQ basis to start.</p>
          <Button size="sm" className="mt-3 h-9 rounded-sm" disabled={disabled} onClick={() => setAddOpen(true)} data-testid="qb-add-first-section">
            <Plus className="h-4 w-4 mr-1" /> Add first section
          </Button>
        </div>
      )}

      {(quote.sections || []).map((sec, idx) => (
        <SectionCard key={sec.id || idx} idx={idx} sec={sec} disabled={disabled}
                     onChange={(p) => updateSection(idx, p)} onDelete={() => deleteSection(idx)}
                     presets={presets} taxMode={quote.tax_mode || "intra"} />
      ))}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><Plus className="h-4 w-4 text-primary" /> Add Service Section</DialogTitle>
            <DialogDescription className="sr-only">Pick a service and RFQ basis. Suggested line items will pre-populate.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Service</Label>
              <select value={pickService} onChange={(e) => { setPickService(e.target.value); setPickBasis((presets.bases[e.target.value] || [])[0] || ""); }}
                      className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="qb-add-section-service">
                {presets.services.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-wider">RFQ basis</Label>
              <select value={pickBasis} onChange={(e) => setPickBasis(e.target.value)}
                      className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="qb-add-section-basis">
                {(presets.bases[pickService] || []).map((b) => (
                  <option key={b} value={b}>{presets.basis_labels[b] || b}</option>
                ))}
              </select>
            </div>
            <p className="text-[11px] text-muted-foreground">{(presets.preset_items[pickService]?.[pickBasis] || []).length} suggested line items will be pre-filled.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" data-testid="qb-add-section-confirm"
                    onClick={() => { addSection(pickService, pickBasis); setAddOpen(false); }}>
              Add Section
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SectionCard({ sec, idx, onChange, onDelete, presets, taxMode, disabled }) {
  const [aiBusy, setAiBusy] = useState(false);
  const updateItem = (i, patch) => {
    const items = [...(sec.items || [])];
    items[i] = { ...items[i], ...patch };
    onChange({ items });
  };
  const addItem = () => onChange({ items: [...(sec.items || []), emptyItem()] });
  const duplicateItem = (i) => {
    const items = [...(sec.items || [])];
    items.splice(i + 1, 0, { ...items[i] });
    onChange({ items });
  };
  const removeItem = (i) => onChange({ items: (sec.items || []).filter((_, j) => j !== i) });

  const aiSuggest = async () => {
    setAiBusy(true);
    try {
      const { data } = await api.post("/quotation-builder/ai/suggest-items", {
        service: sec.service, basis: sec.basis,
        scope_text: sec.notes || "",
      });
      const newItems = (data.items || []).map(emptyItem);
      onChange({ items: [...(sec.items || []), ...newItems] });
      toast.success(`AI added ${newItems.length} line items${data.assumptions?.length ? ` · ${data.assumptions.length} assumption(s)` : ""}`);
    } catch (e) { toast.error(e.response?.data?.detail || "AI suggestion failed"); }
    finally { setAiBusy(false); }
  };

  return (
    <div className="bg-card border border-border rounded-sm" data-testid={`qb-section-${idx}`}>
      <div className="p-3 border-b border-border flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">
          {sec.service?.replaceAll("_", " ")} · {presets.basis_labels?.[sec.basis] || sec.basis}
        </span>
        <Input className="h-8 rounded-sm w-72" placeholder="Section title (printed on PDF)"
               value={sec.title || ""} disabled={disabled}
               onChange={(e) => onChange({ title: e.target.value })} data-testid={`qb-section-title-${idx}`} />
        <Button size="sm" variant="outline" className="h-8 rounded-sm" disabled={disabled || aiBusy} onClick={aiSuggest} data-testid={`qb-ai-suggest-${idx}`}>
          <Sparkles className="h-3.5 w-3.5 mr-1 text-primary" /> {aiBusy ? "Thinking…" : "AI suggest items"}
        </Button>
        <Button size="sm" variant="outline" className="h-8 rounded-sm ml-auto text-destructive border-destructive/40" disabled={disabled} onClick={onDelete} data-testid={`qb-section-delete-${idx}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">#</TableHead>
              <TableHead className="min-w-[260px]">Description</TableHead>
              <TableHead>HSN/SAC</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead>Unit</TableHead>
              <TableHead className="text-right">Rate</TableHead>
              <TableHead className="text-right">Disc %</TableHead>
              <TableHead className="text-right">GST %</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right w-20"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(sec.items || []).map((it, i) => (
              <TableRow key={i} data-testid={`qb-item-row-${idx}-${i}`}>
                <TableCell className="text-xs text-muted-foreground tabular">{i + 1}</TableCell>
                <TableCell>
                  <Input className="h-8 rounded-sm" value={it.description || ""} disabled={disabled}
                         onChange={(e) => updateItem(i, { description: e.target.value })} data-testid={`qb-item-desc-${idx}-${i}`} />
                  <Input className="h-7 rounded-sm mt-1 text-[11px]" value={it.specification || ""} disabled={disabled}
                         placeholder="specification (optional)"
                         onChange={(e) => updateItem(i, { specification: e.target.value })} />
                </TableCell>
                <TableCell><Input className="h-8 rounded-sm w-20" value={it.hsn_sac || ""} disabled={disabled} onChange={(e) => updateItem(i, { hsn_sac: e.target.value })} /></TableCell>
                <TableCell><Input className="h-8 rounded-sm w-20 text-right tabular" type="number" value={it.quantity ?? 0} disabled={disabled} onChange={(e) => updateItem(i, { quantity: +e.target.value })} data-testid={`qb-item-qty-${idx}-${i}`} /></TableCell>
                <TableCell><Input className="h-8 rounded-sm w-16" value={it.unit || ""} disabled={disabled} onChange={(e) => updateItem(i, { unit: e.target.value })} /></TableCell>
                <TableCell><Input className="h-8 rounded-sm w-24 text-right tabular" type="number" value={it.rate ?? 0} disabled={disabled} onChange={(e) => updateItem(i, { rate: +e.target.value })} data-testid={`qb-item-rate-${idx}-${i}`} /></TableCell>
                <TableCell><Input className="h-8 rounded-sm w-16 text-right tabular" type="number" value={it.discount_pct ?? 0} disabled={disabled} onChange={(e) => updateItem(i, { discount_pct: +e.target.value })} /></TableCell>
                <TableCell><Input className="h-8 rounded-sm w-16 text-right tabular" type="number" value={it.gst_pct ?? 0} disabled={disabled} onChange={(e) => updateItem(i, { gst_pct: +e.target.value })} /></TableCell>
                <TableCell className="text-right tabular font-semibold text-sm">{inr(it.total)}</TableCell>
                <TableCell className="text-right">
                  <div className="inline-flex gap-1">
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={disabled} onClick={() => duplicateItem(i)} title="Duplicate"><Copy className="h-3 w-3" /></Button>
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" disabled={disabled} onClick={() => removeItem(i)} title="Delete"><Trash2 className="h-3 w-3" /></Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={8} className="text-right text-xs uppercase tracking-wider text-muted-foreground font-bold">Section subtotal</TableCell>
              <TableCell className="text-right tabular font-bold">{inr(sec.subtotal_total)}</TableCell>
              <TableCell></TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
      <div className="p-2 border-t border-border flex items-center gap-2">
        <Button size="sm" variant="outline" className="h-8 rounded-sm" disabled={disabled} onClick={addItem} data-testid={`qb-add-item-${idx}`}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add item
        </Button>
        <span className="text-[11px] text-muted-foreground ml-auto">{(sec.items || []).length} items · tax mode: {taxMode}</span>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Conditions editor (technical, commercial, inclusions, exclusions)
// ──────────────────────────────────────────────────────────────────────────────
function ConditionsEditor({ quote, update, conditions, disabled }) {
  const services = ["common", ...(quote.service_categories || [])];
  const libBy = (cat) => conditions.filter((c) => c.category === cat && services.includes(c.service));

  const toggle = (cat, text) => {
    const key = { technical: "technical_conditions", commercial: "commercial_conditions", inclusion: "inclusions", exclusion: "exclusions" }[cat];
    const cur = quote[key] || [];
    const has = cur.includes(text);
    update({ [key]: has ? cur.filter((x) => x !== text) : [...cur, text] });
  };
  const addCustom = (cat, text) => {
    if (!text.trim()) return;
    const key = { technical: "technical_conditions", commercial: "commercial_conditions", inclusion: "inclusions", exclusion: "exclusions" }[cat];
    update({ [key]: [...(quote[key] || []), text.trim()] });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {[
        ["technical", "Technical Conditions", "technical_conditions"],
        ["commercial", "Commercial Conditions", "commercial_conditions"],
        ["inclusion", "Inclusions", "inclusions"],
        ["exclusion", "Exclusions", "exclusions"],
      ].map(([cat, label, key]) => (
        <ConditionPanel key={cat} category={cat} label={label} library={libBy(cat)} selected={quote[key] || []}
                        onToggle={(t) => toggle(cat, t)} onAdd={(t) => addCustom(cat, t)}
                        onRemove={(t) => update({ [key]: (quote[key] || []).filter((x) => x !== t) })}
                        disabled={disabled} />
      ))}
    </div>
  );
}
function ConditionPanel({ category, label, library, selected, onToggle, onAdd, onRemove, disabled }) {
  const [custom, setCustom] = useState("");
  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="p-3 border-b border-border flex items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary"><ListChecks className="h-3 w-3 inline mr-1" /> {label}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{selected.length} selected</span>
      </div>
      <div className="p-3 space-y-2 max-h-96 overflow-y-auto">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">From library</p>
        <ul className="space-y-1">
          {library.map((c) => {
            const isOn = selected.includes(c.text);
            return (
              <li key={c.id} className="flex items-start gap-2">
                <input type="checkbox" disabled={disabled} className="mt-1" checked={isOn} onChange={() => onToggle(c.text)} data-testid={`qb-cond-toggle-${category}-${c.id}`} />
                <span className="text-[12px] flex-1">{c.text}</span>
                <span className="text-[9px] uppercase tracking-wider text-muted-foreground">{c.service}</span>
              </li>
            );
          })}
          {library.length === 0 && <li className="text-xs text-muted-foreground italic">No library clauses for this category yet.</li>}
        </ul>
        <div className="border-t border-dashed border-border pt-2 mt-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Added (incl. custom)</p>
          {selected.length === 0 && <p className="text-xs text-muted-foreground italic">Nothing added yet.</p>}
          <ul className="space-y-1">
            {selected.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] bg-primary/5 rounded-sm px-2 py-1">
                <CheckCircle2 className="h-3 w-3 text-primary mt-0.5 shrink-0" />
                <span className="flex-1">{t}</span>
                <button disabled={disabled} className="text-muted-foreground hover:text-destructive" onClick={() => onRemove(t)} title="Remove"><X className="h-3 w-3" /></button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex gap-1 pt-2 border-t border-dashed border-border">
          <Input className="h-8 rounded-sm" placeholder="Custom clause…" value={custom} disabled={disabled}
                 onChange={(e) => setCustom(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") { onAdd(custom); setCustom(""); } }}
                 data-testid={`qb-cond-custom-${category}`} />
          <Button size="sm" className="h-8 rounded-sm" disabled={disabled} onClick={() => { onAdd(custom); setCustom(""); }}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Preview block
// ──────────────────────────────────────────────────────────────────────────────
function PreviewBlock({ quote }) {
  return (
    <div className="bg-white border border-border rounded-sm p-6 max-w-4xl mx-auto text-[13px]" data-testid="qb-preview-pane">
      <div className="flex justify-between items-start mb-4">
        <div>
          <div className="font-display font-black text-xl">INDIAN TRADE LINKS</div>
          <div className="text-[11px] text-muted-foreground">{quote.company_state || "—"}</div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-primary font-bold">Quotation</div>
          <div className="font-display font-black text-xl">{quote.quote_number}</div>
          <div className="text-[11px] text-muted-foreground">Date: {quote.date} · Valid: {quote.valid_until || "—"}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 border border-border rounded-sm p-3 mb-4">
        <div><div className="text-[10px] uppercase tracking-wider text-primary font-bold">Client</div><div className="font-semibold">{quote.client}</div><div className="text-[11px] text-muted-foreground">{quote.site_name} · {quote.client_state}</div></div>
        <div><div className="text-[10px] uppercase tracking-wider text-primary font-bold">Scope</div><div className="text-[12px]">{quote.project || quote.scope_of_work || "—"}</div></div>
      </div>
      {(quote.sections || []).map((s, i) => (
        <div key={i} className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-primary font-bold mb-1">{s.title || `${s.service} · ${s.basis}`}</div>
          <table className="w-full text-[11.5px]">
            <thead className="bg-slate-900 text-white">
              <tr>
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">Description</th>
                <th className="px-2 py-1 text-right">Qty</th>
                <th className="px-2 py-1 text-left">Unit</th>
                <th className="px-2 py-1 text-right">Rate</th>
                <th className="px-2 py-1 text-right">GST</th>
                <th className="px-2 py-1 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {(s.items || []).map((it, j) => (
                <tr key={j} className={j % 2 ? "bg-slate-50" : ""}>
                  <td className="px-2 py-1">{j + 1}</td>
                  <td className="px-2 py-1">{it.description}<div className="text-[10px] text-muted-foreground">{it.specification}</div></td>
                  <td className="px-2 py-1 text-right tabular">{it.quantity}</td>
                  <td className="px-2 py-1">{it.unit}</td>
                  <td className="px-2 py-1 text-right tabular">{inr(it.rate)}</td>
                  <td className="px-2 py-1 text-right tabular">{it.gst_pct}%</td>
                  <td className="px-2 py-1 text-right tabular font-semibold">{inr(it.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <div className="flex justify-end">
        <table className="text-[12px] min-w-[300px]">
          <tbody>
            <tr><td className="px-2 py-1">Basic</td><td className="px-2 py-1 text-right tabular">{inr(quote.totals?.basic)}</td></tr>
            <tr><td className="px-2 py-1">Discount</td><td className="px-2 py-1 text-right tabular">-{inr(quote.totals?.discount)}</td></tr>
            <tr><td className="px-2 py-1">Taxable</td><td className="px-2 py-1 text-right tabular">{inr(quote.totals?.taxable)}</td></tr>
            {quote.tax_mode === "intra" ? (
              <>
                <tr><td className="px-2 py-1">CGST</td><td className="px-2 py-1 text-right tabular">{inr(quote.totals?.cgst)}</td></tr>
                <tr><td className="px-2 py-1">SGST</td><td className="px-2 py-1 text-right tabular">{inr(quote.totals?.sgst)}</td></tr>
              </>
            ) : (
              <tr><td className="px-2 py-1">IGST</td><td className="px-2 py-1 text-right tabular">{inr(quote.totals?.igst)}</td></tr>
            )}
            <tr className="bg-slate-900 text-white font-bold"><td className="px-2 py-1.5">GRAND TOTAL</td><td className="px-2 py-1.5 text-right tabular">{inr(quote.totals?.grand_total)}</td></tr>
          </tbody>
        </table>
      </div>
      {(quote.inclusions || []).length > 0 && <Block title="Inclusions" items={quote.inclusions} />}
      {(quote.exclusions || []).length > 0 && <Block title="Exclusions" items={quote.exclusions} />}
      {(quote.technical_conditions || []).length > 0 && <Block title="Technical Conditions" items={quote.technical_conditions} />}
      {(quote.commercial_conditions || []).length > 0 && <Block title="Commercial Conditions" items={quote.commercial_conditions} />}
    </div>
  );
}
function Block({ title, items }) {
  return (
    <div className="mt-3">
      <div className="text-[10px] uppercase tracking-wider text-primary font-bold mb-1">{title}</div>
      <ol className="list-decimal list-inside text-[11.5px] space-y-0.5">{items.map((it, i) => <li key={i}>{it}</li>)}</ol>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// AI RFQ extraction dialog
// ──────────────────────────────────────────────────────────────────────────────
function AiRfqDialog({ open, onClose, quote, update, presets }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!file) { toast.error("Pick an RFQ file first"); return; }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/quotation-builder/ai/extract-rfq", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data.extracted);
      toast.success("RFQ analysed · review and click Apply");
    } catch (e) { toast.error(e.response?.data?.detail || "AI extraction failed"); }
    finally { setBusy(false); }
  };

  const apply = () => {
    if (!result) return;
    const patch = {};
    if (result.customer) patch.client = result.customer;
    if (result.site_location) patch.site_name = result.site_location;
    if (result.contact_person) patch.contact_person = result.contact_person;
    if (result.contact_email) patch.contact_email = result.contact_email;
    if (result.scope_of_work) patch.project = result.scope_of_work;
    if (result.submission_deadline) patch.submission_deadline = result.submission_deadline;
    if (result.payment_terms) patch.payment_terms = result.payment_terms;
    if (result.delivery_timeline) patch.delivery_timeline = result.delivery_timeline;
    if (result.service_categories?.length) patch.service_categories = result.service_categories;
    if (result.rfq_type?.length) patch.rfq_type = result.rfq_type;
    // Build a draft section per service with mapped line items (no section if no items)
    if (result.line_items?.length && result.service_categories?.length) {
      const svc = result.service_categories[0];
      const basis = (result.rfq_type || [])[0] || (presets.bases[svc] || [])[0];
      const sec = {
        id: "s_ai_" + Math.random().toString(36).slice(2, 9),
        title: `${svc.replaceAll("_", " ")} · ${presets.basis_labels?.[basis] || basis} (AI draft)`,
        service: svc, basis,
        notes: result.scope_of_work || "",
        items: (result.line_items || []).map((li) => emptyItem({
          description: li.description, specification: li.specification || "",
          quantity: +li.quantity || 1, unit: li.unit || "Nos",
          rate: 0, gst_pct: 18, hsn_sac: "9987",
        })),
      };
      patch.sections = [...(quote.sections || []), sec];
    }
    update(patch);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid="qb-ai-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Wand2 className="h-4 w-4 text-primary" /> AI · Extract RFQ</DialogTitle>
          <DialogDescription>Upload customer RFQ (PDF / image / DOCX / XLSX). Gemini 2.5 Pro extracts structured fields.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {!result && (
            <div className="border border-dashed border-border rounded-sm p-6 text-center">
              <Upload className="h-6 w-6 text-muted-foreground mx-auto mb-2" />
              <input type="file" accept=".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp,.heic,.txt,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="qb-ai-file" />
              <p className="text-[11px] text-muted-foreground mt-2">{file ? file.name : "No file selected"}</p>
            </div>
          )}
          {busy && <p className="text-sm text-primary text-center">Analyzing RFQ with Gemini 2.5 Pro…</p>}
          {result && (
            <div className="space-y-2 text-[12.5px]">
              <KV k="Customer" v={result.customer} />
              <KV k="RFQ #" v={result.customer_rfq_no} />
              <KV k="Submission deadline" v={result.submission_deadline} />
              <KV k="Site / location" v={result.site_location} />
              <KV k="Services" v={(result.service_categories || []).join(", ")} />
              <KV k="RFQ basis" v={(result.rfq_type || []).join(", ")} />
              <KV k="Scope" v={(result.scope_of_work || "").slice(0, 240) + ((result.scope_of_work || "").length > 240 ? "…" : "")} />
              <details><summary className="cursor-pointer text-primary font-semibold text-[11px]">Line items ({(result.line_items || []).length})</summary>
                <ul className="text-[11px] mt-1 pl-4 list-disc">{(result.line_items || []).map((li, i) => <li key={i}>{li.description} — {li.quantity || ""} {li.unit || ""}</li>)}</ul>
              </details>
              {(result.missing_information || []).length > 0 && (
                <div className="border border-amber-300 bg-amber-50 rounded-sm p-2">
                  <div className="text-[10px] uppercase tracking-wider text-amber-900 font-bold flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Missing info / clarifications</div>
                  <ul className="text-[11px] list-disc list-inside text-amber-900">{result.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul>
                  {(result.clarification_questions || []).length > 0 && <ul className="text-[11px] list-disc list-inside text-amber-900 mt-1">{result.clarification_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>}
                </div>
              )}
              {(result.risk_points || []).length > 0 && (
                <div className="border border-red-300 bg-red-50 rounded-sm p-2">
                  <div className="text-[10px] uppercase tracking-wider text-red-900 font-bold">Risk points</div>
                  <ul className="text-[11px] list-disc list-inside text-red-900">{result.risk_points.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          {!result ? (
            <Button className="rounded-sm" onClick={run} disabled={!file || busy} data-testid="qb-ai-run">
              <Wand2 className="h-4 w-4 mr-1.5" /> {busy ? "Analysing…" : "Analyse RFQ"}
            </Button>
          ) : (
            <Button className="rounded-sm" onClick={apply} data-testid="qb-ai-apply">
              <CheckCircle2 className="h-4 w-4 mr-1.5" /> Apply to Quotation
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
function KV({ k, v }) { return <div className="flex gap-2"><span className="text-[10px] uppercase tracking-wider text-muted-foreground w-32 shrink-0">{k}</span><span className="text-[12px]">{v || "—"}</span></div>; }

// ──────────────────────────────────────────────────────────────────────────────
// Send to client dialog
// ──────────────────────────────────────────────────────────────────────────────
function SendToClientDialog({ open, onClose, quote, reload }) {
  const [to, setTo] = useState(quote.contact_email || "");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState(`Quotation ${quote.quote_number} from INDIAN TRADE LINKS`);
  const [body, setBody] = useState("");
  const [attach, setAttach] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setTo(quote.contact_email || ""); }, [quote.contact_email]);

  const submit = async () => {
    if (!to.trim()) { toast.error("Recipient email required"); return; }
    setBusy(true);
    try {
      const cc_list = cc.split(",").map((s) => s.trim()).filter(Boolean);
      const { data } = await api.post(`/quotation-builder/${quote.id}/send-to-client`, { to_email: to.trim(), cc_emails: cc_list, subject, body, attach_pdf: attach });
      if (data.delivered) toast.success("Quotation emailed to client");
      else toast.warning("Submission recorded · email delivery skipped (configure Resend in .env)");
      await reload();
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Send failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-xl rounded-sm">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Mail className="h-4 w-4 text-primary" /> Send Quotation to Client</DialogTitle>
          <DialogDescription>Quotation PDF is attached automatically. Email is delivered via Resend.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Field label="To *" value={to} onChange={setTo} testid="qb-send-to" />
          <Field label="CC (comma-separated)" value={cc} onChange={setCc} testid="qb-send-cc" />
          <Field label="Subject" value={subject} onChange={setSubject} testid="qb-send-subject" />
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Message body (HTML supported)</Label>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} className="rounded-sm mt-1 min-h-[120px]" placeholder="Leave blank for default message…" data-testid="qb-send-body" />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} data-testid="qb-send-attach" /> Attach PDF
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Cancel</Button>
          <Button className="rounded-sm" onClick={submit} disabled={busy} data-testid="qb-send-submit">
            <Send className="h-4 w-4 mr-1.5" /> {busy ? "Sending…" : "Send"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Card({ title, children }) {
  return (
    <div className="bg-card border border-border rounded-sm p-4 space-y-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{title}</div>
      {children}
    </div>
  );
}
function Field({ label, value, onChange, type = "text", testid, disabled }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
