import { useEffect, useState } from "react";
import { Hash, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Super Admin only — controls the auto-generated Customer Code format.
 * Stored under settings._id="customer_code_format".
 */
export default function CustomerCodeSettings() {
  const [form, setForm] = useState({ prefix: "CUST", padding: 4, include_fy: false });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/admin/customer-code-format")
      .then((r) => setForm(r.data))
      .catch(() => toast.error("Failed to load settings"));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/admin/customer-code-format", form);
      setForm(data);
      toast.success("Customer code format updated");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const preview = form.include_fy
    ? `${form.prefix}-${new Date().getFullYear()}-${"1".padStart(form.padding, "0")}`
    : `${form.prefix}-${"1".padStart(form.padding, "0")}`;

  return (
    <div className="max-w-2xl space-y-6" data-testid="customer-code-settings">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Hash className="h-3 w-3" /> Admin · Numbering
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Customer Code Format</h1>
        <p className="text-sm text-muted-foreground mt-1">System-wide format for auto-generated client codes. Changes apply to NEW clients only.</p>
      </div>

      <div className="bg-card border border-border rounded-sm p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs uppercase tracking-wider">Prefix</Label>
            <Input
              value={form.prefix}
              onChange={(e) => setForm({ ...form, prefix: e.target.value.toUpperCase() })}
              maxLength={10}
              className="rounded-sm font-mono-data mt-1"
              data-testid="ccs-prefix"
            />
            <p className="text-[10px] text-muted-foreground mt-1">1-10 uppercase chars (CUST, CL, TATA, etc.)</p>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Padding</Label>
            <Input
              type="number" min={3} max={8}
              value={form.padding}
              onChange={(e) => setForm({ ...form, padding: parseInt(e.target.value) || 4 })}
              className="rounded-sm font-mono-data mt-1"
              data-testid="ccs-padding"
            />
            <p className="text-[10px] text-muted-foreground mt-1">Number digits (4 → 0001, 5 → 00001)</p>
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm" data-testid="ccs-include-fy">
          <input
            type="checkbox"
            checked={form.include_fy}
            onChange={(e) => setForm({ ...form, include_fy: e.target.checked })}
            className="h-4 w-4 rounded-sm border-input"
          />
          Include current year in code (resets each calendar year)
        </label>

        <div className="border-t border-border pt-4">
          <Label className="text-xs uppercase tracking-wider">Live preview</Label>
          <div className="mt-2 font-display font-black text-3xl font-mono-data text-primary" data-testid="ccs-preview">
            {preview}
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Next client created will get this format.</p>
        </div>

        <div className="flex justify-end pt-2">
          <Button onClick={save} disabled={saving} className="rounded-sm" data-testid="ccs-save">
            <Save className="h-4 w-4 mr-1.5" /> {saving ? "Saving…" : "Save Format"}
          </Button>
        </div>
      </div>
    </div>
  );
}
