import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ShieldCheck, Plus, Trash2, Pencil, Search, Users, AlertTriangle, Save, X } from "lucide-react";
import { toast } from "sonner";

const ACTIONS = ["read", "write", "delete"];

export default function RoleCatalog() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteFor, setDeleteFor] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/role-catalog");
      setData(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load roles");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const filteredRoles = useMemo(() => {
    if (!data) return [];
    const s = q.trim().toLowerCase();
    if (!s) return data.roles;
    return data.roles.filter(r => r.key.toLowerCase().includes(s) || (r.label || "").toLowerCase().includes(s));
  }, [data, q]);

  const removeRole = async (role) => {
    try {
      await api.delete(`/admin/role-catalog/${role.key}`);
      toast.success(`Removed role "${role.label}"`);
      setDeleteFor(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading role catalog…</div>;
  if (!data) return null;

  const builtinCount = data.roles.filter(r => r.is_builtin).length;
  const customCount = data.roles.length - builtinCount;

  return (
    <div className="space-y-6" data-testid="role-catalog-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ShieldCheck className="h-3 w-3" /> Super-Admin Control
        </div>
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Role Catalog</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Add custom roles tailored to your org (e.g. "Site Safety Supervisor"), or retire any role no users hold.
          Granular permissions per role live in <a className="underline text-primary" href="/app/admin/role-register">Role Register</a>.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total roles" value={data.roles.length} icon={ShieldCheck} />
        <StatCard label="Built-in" value={builtinCount} icon={ShieldCheck} tone="muted" />
        <StatCard label="Custom" value={customCount} icon={Plus} tone="primary" />
        <StatCard label="Resources covered" value={data.resources.length} icon={Users} tone="muted" />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1">
            <div className="relative w-full max-w-sm">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search roles…" className="pl-8 h-9" data-testid="role-catalog-search" />
            </div>
          </div>
          <Button onClick={() => setCreateOpen(true)} data-testid="role-catalog-add-btn">
            <Plus className="h-3.5 w-3.5 mr-1.5" /> Add custom role
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">Key</TableHead>
                <TableHead>Label</TableHead>
                <TableHead className="hidden lg:table-cell">Description</TableHead>
                <TableHead className="w-[80px] text-center">Type</TableHead>
                <TableHead className="w-[90px] text-center">Users</TableHead>
                <TableHead className="w-[120px] text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRoles.map((r) => (
                <TableRow key={r.key} data-testid={`role-row-${r.key}`}>
                  <TableCell><code className="text-[12px] font-mono bg-muted/40 px-1.5 py-0.5 rounded-sm">{r.key}</code></TableCell>
                  <TableCell className="font-medium">{r.label}</TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground max-w-md">{r.description || "—"}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant={r.is_builtin ? "secondary" : "default"} className="text-[10px]">
                      {r.is_builtin ? "Built-in" : "Custom"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center text-sm tabular-nums">{r.user_count}</TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(r)} data-testid={`role-edit-${r.key}`} title="Rename / edit description"><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleteFor(r)}
                        disabled={r.key === "super_admin"}
                        title={r.key === "super_admin" ? "Root role — cannot delete" : "Delete role"}
                        data-testid={`role-delete-${r.key}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {filteredRoles.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">No roles match your search.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateRoleDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        resources={data.resources}
        existingKeys={data.roles.map(r => r.key)}
        onCreated={() => { setCreateOpen(false); load(); }}
      />

      <EditRoleDialog
        role={editing}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); load(); }}
      />

      <DeleteRoleDialog
        role={deleteFor}
        onClose={() => setDeleteFor(null)}
        onConfirm={() => deleteFor && removeRole(deleteFor)}
      />
    </div>
  );
}


function StatCard({ label, value, icon: Icon, tone = "muted" }) {
  const colorClass = tone === "primary" ? "text-primary" : "text-muted-foreground";
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1.5">
          <Icon className="h-3 w-3" /> {label}
        </div>
        <div className={`font-display font-black text-2xl tabular ${colorClass}`}>{value}</div>
      </CardContent>
    </Card>
  );
}


function CreateRoleDialog({ open, onOpenChange, resources, existingKeys, onCreated }) {
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [perms, setPerms] = useState({});
  const [saving, setSaving] = useState(false);
  const [resQ, setResQ] = useState("");

  useEffect(() => {
    if (open) { setKey(""); setLabel(""); setDescription(""); setPerms({}); setResQ(""); }
  }, [open]);

  const filteredResources = useMemo(() => {
    const s = resQ.trim().toLowerCase();
    return s ? (resources || []).filter(r => r.toLowerCase().includes(s)) : (resources || []);
  }, [resources, resQ]);

  const toggle = (resource, action) => {
    setPerms((p) => {
      const cur = { ...(p[resource] || {}) };
      cur[action] = !cur[action];
      return { ...p, [resource]: cur };
    });
  };
  const toggleAllForResource = (resource, on) => {
    setPerms((p) => ({ ...p, [resource]: { read: on, write: on, delete: on } }));
  };
  const summary = useMemo(() => {
    let n = 0;
    for (const a of Object.values(perms)) for (const v of Object.values(a)) if (v) n++;
    return n;
  }, [perms]);

  const save = async () => {
    if (!key || !label) { toast.error("Key and label are required"); return; }
    if (existingKeys.includes(key.trim().toLowerCase())) { toast.error(`Role key '${key}' already exists`); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/admin/role-catalog", { key: key.trim().toLowerCase(), label: label.trim(), description: description.trim(), permissions: perms });
      toast.success(`Created role "${data.role.label}" with ${data.permissions_seeded} permission(s)`);
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Create failed");
    } finally { setSaving(false); }
  };

  const suggestKey = (lbl) => lbl.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="create-role-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Create custom role</DialogTitle>
          <DialogDescription>
            Define a new role and seed its starting permissions. You can refine these later in the Role Register.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
          <div>
            <Label className="text-xs">Role label</Label>
            <Input value={label} onChange={(e) => { setLabel(e.target.value); if (!key) setKey(suggestKey(e.target.value)); }} placeholder="e.g. Site Safety Supervisor" data-testid="create-role-label" />
          </div>
          <div>
            <Label className="text-xs">Key (lowercase, no spaces) <span className="text-muted-foreground">— immutable after create</span></Label>
            <Input value={key} onChange={(e) => setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))} placeholder="site_safety_supervisor" className="font-mono text-sm" data-testid="create-role-key" />
          </div>
          <div className="md:col-span-2">
            <Label className="text-xs">Description</Label>
            <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="One-liner describing this role's scope." data-testid="create-role-description" />
          </div>
        </div>

        <div className="border-t pt-3 mt-2">
          <div className="flex items-center justify-between mb-2">
            <Label className="text-xs uppercase tracking-wider">Starter permissions <span className="text-muted-foreground normal-case">· {summary} selected · super_admin auto-included</span></Label>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setPerms({})} type="button">Clear all</Button>
            </div>
          </div>
          <div className="relative mb-2">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input value={resQ} onChange={(e) => setResQ(e.target.value)} placeholder="Filter resources…" className="pl-8 h-9" data-testid="create-role-res-filter" />
          </div>
          <div className="border rounded-sm max-h-[40vh] overflow-y-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-background z-10">
                <TableRow>
                  <TableHead>Resource</TableHead>
                  {ACTIONS.map(a => <TableHead key={a} className="w-[80px] text-center capitalize">{a}</TableHead>)}
                  <TableHead className="w-[60px] text-center">All</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredResources.map((res) => (
                  <TableRow key={res} data-testid={`create-role-res-${res}`}>
                    <TableCell className="text-xs font-mono">{res}</TableCell>
                    {ACTIONS.map(a => (
                      <TableCell key={a} className="text-center">
                        <input
                          type="checkbox"
                          checked={!!(perms[res] && perms[res][a])}
                          onChange={() => toggle(res, a)}
                          data-testid={`create-role-perm-${res}-${a}`}
                        />
                      </TableCell>
                    ))}
                    <TableCell className="text-center">
                      <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-[11px]"
                        onClick={() => toggleAllForResource(res, !(perms[res]?.read && perms[res]?.write && perms[res]?.delete))}
                        data-testid={`create-role-perm-${res}-all`}>
                        Toggle
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {filteredResources.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-xs text-muted-foreground py-6">No resources match.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="create-role-cancel">Cancel</Button>
          <Button onClick={save} disabled={saving} data-testid="create-role-save">
            <Save className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Creating…" : "Create role"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function EditRoleDialog({ role, onClose, onSaved }) {
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (role) { setLabel(role.label || ""); setDescription(role.description || ""); } }, [role]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/admin/role-catalog/${role.key}`, { label, description });
      toast.success("Role updated");
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={!!role} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="edit-role-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Edit role</DialogTitle>
          <DialogDescription>Key <code className="ml-1 font-mono bg-muted/40 px-1.5 py-0.5 rounded-sm">{role?.key}</code> is immutable. Update display label and description only.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <div>
            <Label className="text-xs">Label</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} data-testid="edit-role-label" />
          </div>
          <div>
            <Label className="text-xs">Description</Label>
            <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} data-testid="edit-role-description" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="edit-role-cancel">Cancel</Button>
          <Button onClick={save} disabled={saving} data-testid="edit-role-save">
            <Save className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function DeleteRoleDialog({ role, onClose, onConfirm }) {
  const blocked = role && role.user_count > 0;
  return (
    <Dialog open={!!role} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="delete-role-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning" /> Delete role "{role?.label}"?
          </DialogTitle>
          <DialogDescription>
            {blocked ? (
              <span className="text-destructive">
                <strong>{role.user_count}</strong> user{role.user_count > 1 ? "s" : ""} currently hold this role.
                Reassign them in Profile → User Management before deleting.
              </span>
            ) : (
              <>This will remove <code className="font-mono bg-muted/40 px-1 rounded-sm">{role?.key}</code> from every permission cell, the role dropdown, and the Role Register. {role?.is_builtin && <span className="text-warning"> Built-in role — proceed with caution.</span>}</>
            )}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="delete-role-cancel">Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={blocked} data-testid="delete-role-confirm">
            <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
