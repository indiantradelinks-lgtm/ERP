/**
 * Project Settings · ops defaults: RA-bill cadence, default currency, milestone count,
 * auto-create-WO toggle, notification emails, overdue-bill alert window.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Settings as SettingsIcon, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const FREQS = ["weekly", "fortnightly", "monthly", "milestone", "completion"];

export default function ProjectSettings() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth() || {};
  const canEdit = ["super_admin", "director", "general_manager", "dept_head"].includes(user?.role);

  useEffect(() => { api.get("/proj-settings").then((r) => setS(r.data)).catch(() => {}); }, []);

  const save = async () => {
    if (!canEdit) return;
    setBusy(true);
    try {
      const payload = { ...s, notification_emails: typeof s.notification_emails === "string"
        ? s.notification_emails.split(",").map((x) => x.trim()).filter(Boolean)
        : (s.notification_emails || []) };
      const r = await api.put("/proj-settings", payload);
      setS(r.data);
      toast.success("Settings saved");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setBusy(false); }
  };

  if (!s) return <div className="p-6 text-muted-foreground">Loading…</div>;

  return (
    <div className="p-6 space-y-4 max-w-3xl" data-testid="page-project-settings">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><SettingsIcon className="h-6 w-6 text-primary" /> Project Settings</h1>
          <p className="text-sm text-muted-foreground">Operations-wide defaults applied to every new Project, Work Order & Billing schedule.</p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Operations Defaults</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <F label="Default RA Bill Frequency">
              <select disabled={!canEdit} value={s.default_ra_bill_frequency} onChange={(e) => setS({ ...s, default_ra_bill_frequency: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="settings-freq">
                {FREQS.map((f) => <option key={f}>{f}</option>)}
              </select>
            </F>
            <F label="Default Currency">
              <Input disabled={!canEdit} value={s.default_currency || "INR"} onChange={(e) => setS({ ...s, default_currency: e.target.value })} />
            </F>
            <F label="Default Billing Milestones">
              <Input disabled={!canEdit} type="number" value={s.default_billing_milestone_count || 4} onChange={(e) => setS({ ...s, default_billing_milestone_count: Number(e.target.value) || 0 })} data-testid="settings-milestones" />
            </F>
            <F label="Project Code Prefix">
              <Input disabled={!canEdit} value={s.project_code_prefix || "PRJ"} onChange={(e) => setS({ ...s, project_code_prefix: e.target.value })} />
            </F>
            <F label="Auto-alert overdue bills after (days)">
              <Input disabled={!canEdit} type="number" value={s.auto_alert_overdue_bills_days || 7} onChange={(e) => setS({ ...s, auto_alert_overdue_bills_days: Number(e.target.value) || 0 })} />
            </F>
            <F label="" >
              <label className="flex items-center gap-2 text-sm h-9">
                <input disabled={!canEdit} type="checkbox" checked={!!s.auto_create_wo_from_order}
                        onChange={(e) => setS({ ...s, auto_create_wo_from_order: e.target.checked })} data-testid="settings-auto-wo" />
                Auto-create Work Order on Order conversion
              </label>
            </F>
            <F label="">
              <label className="flex items-center gap-2 text-sm h-9">
                <input disabled={!canEdit} type="checkbox" checked={!!s.require_pm_approval_for_wo}
                        onChange={(e) => setS({ ...s, require_pm_approval_for_wo: e.target.checked })} />
                Require PM approval before WO goes Active
              </label>
            </F>
            <F label="">
              <label className="flex items-center gap-2 text-sm h-9">
                <input disabled={!canEdit} type="checkbox" checked={!!s.require_safety_officer}
                        onChange={(e) => setS({ ...s, require_safety_officer: e.target.checked })} />
                Safety Officer is mandatory on every Project
              </label>
            </F>
          </div>
          <F label="Notification Emails (comma separated)">
            <Input disabled={!canEdit}
                    value={Array.isArray(s.notification_emails) ? s.notification_emails.join(", ") : (s.notification_emails || "")}
                    onChange={(e) => setS({ ...s, notification_emails: e.target.value })} data-testid="settings-emails" />
          </F>
          <F label="Internal Notes">
            <Textarea disabled={!canEdit} rows={3} value={s.notes || ""} onChange={(e) => setS({ ...s, notes: e.target.value })} />
          </F>
          {canEdit && (
            <div className="flex justify-end">
              <Button onClick={save} disabled={busy} data-testid="settings-save">
                <Save className="h-4 w-4 mr-1" /> {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      {!canEdit && (
        <div className="text-xs text-amber-700">
          ℹ️ Only Super Admin / Director / GM / Dept Head can change project settings.
        </div>
      )}
    </div>
  );
}
function F({ label, children }) {
  return <div><Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label><div className="mt-1">{children}</div></div>;
}
