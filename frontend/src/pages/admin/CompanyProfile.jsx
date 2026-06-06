import { useEffect, useState } from "react";
import { Building2, Save, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "sonner";

const DEFAULTS = {
  name: "INDIAN TRADE LINKS", gstin: "", pan: "", state: "Gujarat", state_code: "24",
  address: "", city: "", pincode: "", phone: "", email: "", website: "",
  bank_name: "", account_no: "", ifsc: "",
  authorized_signatory: "", designation: "Authorised Signatory",
};

const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Puducherry",
  "Chandigarh", "Andaman & Nicobar", "Dadra & Nagar Haveli", "Daman & Diu",
  "Jammu & Kashmir", "Ladakh", "Lakshadweep",
];

export default function CompanyProfile() {
  const [form, setForm] = useState(DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/company-profile");
      setForm({ ...DEFAULTS, ...data });
      setLoaded(true);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load company profile"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/admin/company-profile", form);
      setForm({ ...DEFAULTS, ...data });
      toast.success("Company profile updated · used on all quotation PDFs");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6" data-testid="company-profile-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Building2 className="h-3 w-3" /> Admin · Company Profile
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Company Profile</h1>
        <p className="text-sm text-muted-foreground mt-1">Used on every quotation PDF. The state is used to auto-pick CGST+SGST vs IGST.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Identity">
          <Field label="Company name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="cp-name" />
          <Field label="GSTIN" value={form.gstin} onChange={(v) => setForm({ ...form, gstin: v.toUpperCase() })} testid="cp-gstin" />
          <Field label="PAN" value={form.pan} onChange={(v) => setForm({ ...form, pan: v.toUpperCase() })} testid="cp-pan" />
          <div>
            <Label className="text-[10px] uppercase tracking-wider">State (for GST auto-detect)</Label>
            <select value={form.state || ""} onChange={(e) => setForm({ ...form, state: e.target.value })}
                    className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="cp-state">
              <option value="">— select —</option>
              {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <Field label="State code (2-digit GST)" value={form.state_code} onChange={(v) => setForm({ ...form, state_code: v })} testid="cp-state-code" />
        </Card>

        <Card title="Registered address">
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Address</Label>
            <Textarea value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })}
                      className="rounded-sm mt-1 min-h-[68px]" data-testid="cp-address" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="City" value={form.city} onChange={(v) => setForm({ ...form, city: v })} testid="cp-city" />
            <Field label="Pincode" value={form.pincode} onChange={(v) => setForm({ ...form, pincode: v })} testid="cp-pincode" />
            <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testid="cp-phone" />
            <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="cp-email" />
          </div>
          <Field label="Website" value={form.website} onChange={(v) => setForm({ ...form, website: v })} testid="cp-website" />
        </Card>

        <Card title="Banking (shown on PDF)">
          <Field label="Bank name" value={form.bank_name} onChange={(v) => setForm({ ...form, bank_name: v })} testid="cp-bank-name" />
          <Field label="Account number" value={form.account_no} onChange={(v) => setForm({ ...form, account_no: v })} testid="cp-account-no" />
          <Field label="IFSC" value={form.ifsc} onChange={(v) => setForm({ ...form, ifsc: v.toUpperCase() })} testid="cp-ifsc" />
        </Card>

        <Card title="Authorised signatory">
          <Field label="Name" value={form.authorized_signatory} onChange={(v) => setForm({ ...form, authorized_signatory: v })} testid="cp-signatory" />
          <Field label="Designation" value={form.designation} onChange={(v) => setForm({ ...form, designation: v })} testid="cp-designation" />
          <p className="text-[11px] text-muted-foreground">Printed at the bottom of every quotation PDF as the signatory block.</p>
        </Card>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" className="rounded-sm h-9" onClick={() => setForm(DEFAULTS)} data-testid="cp-reset">
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset
        </Button>
        <Button className="rounded-sm h-9 ml-auto" onClick={save} disabled={saving || !loaded} data-testid="cp-save">
          <Save className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
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
function Field({ label, value, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
    </div>
  );
}
