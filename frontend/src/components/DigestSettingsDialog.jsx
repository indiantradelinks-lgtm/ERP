import { useEffect, useMemo, useState } from "react";
import { Settings2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";

/** Super-admin: choose which roles / users / extra emails receive the monthly leaderboard digest. */
export default function DigestSettingsDialog() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [userQ, setUserQ] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/sales/leaderboard/digest/settings").then((r) => {
      setData(r.data);
      setForm({ ...r.data.settings, extra_emails_text: (r.data.settings.extra_emails || []).join(", ") });
    }).catch((e) => toast.error(e.response?.data?.detail || "Could not load digest settings"));
  }, [open]);

  const users = useMemo(() => (data?.users || []).filter((u) => !userQ || `${u.name} ${u.email} ${u.role}`.toLowerCase().includes(userQ.toLowerCase())), [data, userQ]);
  const toggle = (key, val) => setForm((f) => ({ ...f, [key]: f[key].includes(val) ? f[key].filter((x) => x !== val) : [...f[key], val] }));

  const save = async () => {
    setSaving(true);
    try {
      const body = { roles: form.roles, include_sales_dept_head: form.include_sales_dept_head, user_ids: form.user_ids,
        extra_emails: form.extra_emails_text.split(/[,\s;]+/).map((e) => e.trim()).filter(Boolean) };
      const { data: r } = await api.put("/sales/leaderboard/digest/settings", body);
      setData((d) => ({ ...d, settings: r.settings, resolved: r.resolved }));
      toast.success(`Digest recipients saved — ${r.resolved.length} recipient${r.resolved.length === 1 ? "" : "s"}`);
      setOpen(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <>
      <Button size="sm" variant="outline" className="h-7 rounded-sm text-xs" onClick={() => setOpen(true)} title="Digest recipients" data-testid="digest-settings-btn">
        <Settings2 className="h-3.5 w-3.5 mr-1" /> Recipients
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl rounded-sm max-h-[85vh] overflow-y-auto" data-testid="digest-settings-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Monthly digest recipients</DialogTitle>
            <DialogDescription className="text-xs">Who receives the Sales Leaderboard email on the first working day of each month (09:00 IST).</DialogDescription>
          </DialogHeader>
          {!form ? <div className="text-sm text-muted-foreground py-6">Loading…</div> : (
            <div className="space-y-5">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Roles</Label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 mt-1.5">
                  {(data.roles || []).map((r) => (
                    <label key={r} className="flex items-center gap-2 text-xs border border-border rounded-sm px-2 py-1.5 cursor-pointer hover:bg-muted/40">
                      <input type="checkbox" checked={form.roles.includes(r)} onChange={() => toggle("roles", r)} data-testid={`digest-role-${r}`} />
                      <span className="truncate">{r.replaceAll("_", " ")}</span>
                    </label>
                  ))}
                </div>
                <label className="flex items-center gap-2 text-xs mt-2 cursor-pointer">
                  <input type="checkbox" checked={!!form.include_sales_dept_head} onChange={(e) => setForm({ ...form, include_sales_dept_head: e.target.checked })} data-testid="digest-sales-dept-head" />
                  Always include the Sales department head
                </label>
              </div>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-[10px] uppercase tracking-wider">Specific users ({form.user_ids.length} selected)</Label>
                  <Input className="h-7 w-52 text-xs" placeholder="Filter users…" value={userQ} onChange={(e) => setUserQ(e.target.value)} data-testid="digest-user-filter" />
                </div>
                <div className="mt-1.5 max-h-44 overflow-y-auto border border-border rounded-sm divide-y divide-border">
                  {users.map((u) => (
                    <label key={u.id} className="flex items-center gap-2 text-xs px-2 py-1.5 cursor-pointer hover:bg-muted/40">
                      <input type="checkbox" checked={form.user_ids.includes(u.id)} onChange={() => toggle("user_ids", u.id)} data-testid={`digest-user-${u.id}`} />
                      <span className="font-medium">{u.name}</span>
                      <span className="text-muted-foreground truncate">{u.email}</span>
                      <span className="ml-auto text-[10px] uppercase text-muted-foreground">{(u.role || "").replaceAll("_", " ")}</span>
                    </label>
                  ))}
                  {users.length === 0 && <div className="text-xs text-muted-foreground px-2 py-3">No users match.</div>}
                </div>
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Extra email addresses (comma separated)</Label>
                <Input className="h-9 mt-1.5 rounded-sm" placeholder="md@company.com, board@company.com" value={form.extra_emails_text} onChange={(e) => setForm({ ...form, extra_emails_text: e.target.value })} data-testid="digest-extra-emails" />
              </div>
              <div className="text-xs text-muted-foreground" data-testid="digest-resolved">
                Currently resolves to <b className="text-foreground">{(data.resolved || []).length}</b> recipient{(data.resolved || []).length === 1 ? "" : "s"}: {(data.resolved || []).map((r) => r.email).join(", ") || "—"}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} disabled={!form || saving} data-testid="digest-settings-save">{saving ? "Saving…" : "Save recipients"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
