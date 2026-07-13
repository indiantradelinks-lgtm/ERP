import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Settings, Save } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

export default function ApprovalWorkflowSettings() {
  const [cfg, setCfg] = useState({
    restart_on_resubmit: true, mandatory_attachment_types: [],
    reject_remark_min_chars: 5, escalation_days: 3, reminder_days: 1,
    auto_reminders_enabled: true,
  });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [attachInput, setAttachInput] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/approval-workflow-config");
      setCfg({
        restart_on_resubmit: data.restart_on_resubmit ?? true,
        mandatory_attachment_types: data.mandatory_attachment_types || [],
        reject_remark_min_chars: data.reject_remark_min_chars ?? 5,
        escalation_days: data.escalation_days ?? 3,
        reminder_days: data.reminder_days ?? 1,
        auto_reminders_enabled: data.auto_reminders_enabled ?? true,
      });
      setAttachInput((data.mandatory_attachment_types || []).join(", "));
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        restart_on_resubmit: cfg.restart_on_resubmit,
        mandatory_attachment_types: attachInput.split(",").map((s) => s.trim()).filter(Boolean),
        reject_remark_min_chars: Number(cfg.reject_remark_min_chars) || 5,
        escalation_days: Number(cfg.escalation_days) || 3,
        reminder_days: Number(cfg.reminder_days) || 1,
        auto_reminders_enabled: cfg.auto_reminders_enabled,
      };
      const { data } = await api.put("/admin/approval-workflow-config", payload);
      toast.success("Saved");
      setCfg({ ...data });
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6" data-testid="approval-workflow-settings">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="h-6 w-6 text-primary" />
          Approval Workflow Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure how the closed-loop approval cycle behaves across every module.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Resubmission Behaviour</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-start justify-between gap-4 p-3 border rounded-sm">
            <div className="flex-1">
              <Label className="text-sm font-semibold">Restart chain from Level 1 on resubmit</Label>
              <p className="text-xs text-muted-foreground mt-1">
                <strong>ON</strong> (safer): every approver re-validates the revised request.<br />
                <strong>OFF</strong> (faster): resume from the level that rejected — previously-approved levels stay approved.
              </p>
            </div>
            <Switch
              checked={cfg.restart_on_resubmit}
              onCheckedChange={(v) => setCfg({ ...cfg, restart_on_resubmit: v })}
              data-testid="restart-on-resubmit-toggle"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">Minimum rejection-remark length (characters)</Label>
            <Input
              type="number"
              min={1}
              max={200}
              value={cfg.reject_remark_min_chars}
              onChange={(e) => setCfg({ ...cfg, reject_remark_min_chars: Number(e.target.value) })}
              className="w-32 mt-1"
              data-testid="reject-min-chars"
            />
            <p className="text-[10px] text-muted-foreground mt-1">Approvers cannot reject or request info without a remark of at least this length.</p>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider">Mandatory attachment categories (comma-separated)</Label>
            <Input
              value={attachInput}
              onChange={(e) => setAttachInput(e.target.value)}
              placeholder="e.g. purchase_requisition, capex, vendor"
              className="mt-1"
              data-testid="mandatory-attachments"
            />
            <p className="text-[10px] text-muted-foreground mt-1">Approval types that <em>require</em> at least one uploaded document before submission. Upstream routers call <code>assert_attachments_for_type()</code> and 400 if missing.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Reminders & Escalation (Phase 2)</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-start justify-between gap-4 p-3 border rounded-sm">
            <div className="flex-1">
              <Label className="text-sm font-semibold">Auto reminder emails enabled</Label>
              <p className="text-xs text-muted-foreground mt-1">
                When ON, the daily scheduler (08:00 UTC) emails pending approvers and pushes in-app notifications. Escalations still run regardless.
              </p>
            </div>
            <Switch
              checked={cfg.auto_reminders_enabled}
              onCheckedChange={(v) => setCfg({ ...cfg, auto_reminders_enabled: v })}
              data-testid="auto-reminders-toggle"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs uppercase tracking-wider">Reminder threshold (days)</Label>
              <Input
                type="number" min={1} max={30}
                value={cfg.reminder_days}
                onChange={(e) => setCfg({ ...cfg, reminder_days: Number(e.target.value) })}
                className="w-32 mt-1"
                data-testid="reminder-days"
              />
              <p className="text-[10px] text-muted-foreground mt-1">After this many days of inactivity, nudge the assigned approver.</p>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider">Escalation threshold (days)</Label>
              <Input
                type="number" min={1} max={60}
                value={cfg.escalation_days}
                onChange={(e) => setCfg({ ...cfg, escalation_days: Number(e.target.value) })}
                className="w-32 mt-1"
                data-testid="escalation-days"
              />
              <p className="text-[10px] text-muted-foreground mt-1">After this many days, auto-escalate to a higher role and write an audit entry.</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={save} disabled={busy} data-testid="save-approval-config">
          <Save className="h-4 w-4 mr-1.5" /> {busy ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
