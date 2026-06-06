import { useEffect, useState } from "react";
import { Settings, Save, RotateCcw, Banknote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { toast } from "sonner";

const HARD_DEFAULTS = { gst_pct: 18, retention_pct: 0, tds_pct: 0, due_days: 30, currency_code: "INR", currency_symbol: "₹", locale: "en-IN" };
const CURRENCY_PRESETS = [
  { code: "INR", symbol: "₹", locale: "en-IN", label: "Indian Rupee · en-IN" },
  { code: "USD", symbol: "$", locale: "en-US", label: "US Dollar · en-US" },
  { code: "AED", symbol: "د.إ", locale: "ar-AE", label: "UAE Dirham · ar-AE" },
  { code: "GBP", symbol: "£", locale: "en-GB", label: "Pound Sterling · en-GB" },
  { code: "EUR", symbol: "€", locale: "en-IE", label: "Euro · en-IE" },
];

export default function BillingDefaults() {
  const [form, setForm] = useState(HARD_DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/billing-defaults");
      setForm({ ...HARD_DEFAULTS, ...data });
      setLoaded(true);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load defaults"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        gst_pct: Number(form.gst_pct), retention_pct: Number(form.retention_pct),
        tds_pct: Number(form.tds_pct), due_days: Number(form.due_days),
        currency_code: form.currency_code, currency_symbol: form.currency_symbol,
        locale: form.locale,
      };
      const { data } = await api.put("/admin/billing-defaults", payload);
      setForm({ ...HARD_DEFAULTS, ...data });
      toast.success("Billing defaults updated · new RA bills will use these values");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const applyPreset = (preset) => setForm({ ...form, currency_code: preset.code, currency_symbol: preset.symbol, locale: preset.locale });
  const sample = new Intl.NumberFormat(form.locale || "en-IN", { style: "currency", currency: form.currency_code || "INR", maximumFractionDigits: 0 });
  const sampleAmount = 1234567;
  let preview = `${form.currency_symbol || "₹"} ${Number(sampleAmount).toLocaleString(form.locale || "en-IN", { maximumFractionDigits: 0 })}`;
  try { preview = sample.format(sampleAmount); } catch { /* keep fallback */ }

  return (
    <div className="space-y-6" data-testid="billing-defaults-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Settings className="h-3 w-3" /> Admin · Billing & Tax Defaults
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Billing Defaults</h1>
        <p className="text-sm text-muted-foreground mt-1">Set tax rates, retention %, due-days and currency once. New RA bills auto-fill from these values — line items can still override per bill.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title={<><Banknote className="h-4 w-4 inline mr-1.5" /> Tax & retention</>}>
          <div className="grid grid-cols-2 gap-3">
            <PctField label="GST %" value={form.gst_pct} onChange={(v) => setForm({ ...form, gst_pct: v })} testid="bd-gst" />
            <PctField label="Retention %" value={form.retention_pct} onChange={(v) => setForm({ ...form, retention_pct: v })} testid="bd-retention" />
            <PctField label="TDS %" value={form.tds_pct} onChange={(v) => setForm({ ...form, tds_pct: v })} testid="bd-tds" />
            <Field label="Due days (post-invoice)" type="number" value={form.due_days} onChange={(v) => setForm({ ...form, due_days: v })} testid="bd-due-days" />
          </div>
          <p className="text-[11px] text-muted-foreground mt-3">RA bill math: subtotal × GST = gross · retention/TDS are computed on subtotal (not gross) and deducted from net.</p>
        </Card>

        <Card title="Currency & locale">
          <div className="space-y-2">
            <div>
              <Label className="text-[10px] uppercase tracking-wider">Preset</Label>
              <div className="grid grid-cols-1 gap-1.5 mt-1">
                {CURRENCY_PRESETS.map((p) => (
                  <button key={p.code} type="button"
                          className={`h-9 rounded-sm border text-xs text-left px-3 flex items-center justify-between hover:bg-muted/30 ${form.currency_code === p.code ? "border-primary bg-primary/10" : "border-input"}`}
                          onClick={() => applyPreset(p)} data-testid={`bd-currency-${p.code}`}>
                    <span><span className="font-mono-data font-bold mr-1">{p.symbol}</span>{p.label}</span>
                    {form.currency_code === p.code && <span className="text-[10px] text-primary font-bold">SELECTED</span>}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Field label="Code" value={form.currency_code} onChange={(v) => setForm({ ...form, currency_code: (v || "").toUpperCase().slice(0, 3) })} testid="bd-currency-code" />
              <Field label="Symbol" value={form.currency_symbol} onChange={(v) => setForm({ ...form, currency_symbol: v })} testid="bd-currency-symbol" />
              <Field label="Locale" value={form.locale} onChange={(v) => setForm({ ...form, locale: v })} testid="bd-locale" />
            </div>
            <div className="bg-muted/30 border border-border rounded-sm p-2.5 mt-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Preview · 12,34,567</div>
              <div className="font-display font-black text-2xl text-primary tabular" data-testid="bd-preview">{preview}</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" className="rounded-sm h-9" onClick={() => setForm(HARD_DEFAULTS)} data-testid="bd-reset"><RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset to defaults</Button>
        <Button className="rounded-sm h-9 ml-auto" onClick={save} disabled={saving || !loaded} data-testid="bd-save"><Save className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Saving…" : "Save"}</Button>
      </div>
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div className="bg-card border border-border rounded-sm p-4">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-3">{title}</div>
      {children}
    </div>
  );
}
function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
function PctField({ label, value, onChange, testid }) {
  return (
    <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <div className="relative mt-1">
        <Input type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm pr-9 tabular" data-testid={testid} />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-bold">%</span>
      </div>
    </div>
  );
}
