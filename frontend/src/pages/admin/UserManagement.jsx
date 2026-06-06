import { useEffect, useMemo, useState } from "react";
import {
  Users, UserPlus, Edit2, Trash2, KeyRound, Power, Search,
  ShieldCheck, ShieldOff, ShieldAlert, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { api } from "@/lib/api";
import { toast } from "sonner";

const FALLBACK_ROLES = [
  "super_admin", "director", "general_manager", "dept_head", "project_manager",
  "site_engineer", "supervisor", "store_incharge", "accounts_executive",
  "hr_executive", "safety_officer", "purchase_officer", "sales_executive", "client_rep", "vendor",
];

const blankUser = () => ({
  email: "", name: "", role: "site_engineer", department: "", phone: "",
  password: "", active: true, must_change_password: false,
});

export default function UserManagement() {
  const [rows, setRows] = useState([]);
  const [ROLES, setRoles] = useState(FALLBACK_ROLES);
  const [departments, setDepartments] = useState([]);
  const [q, setQ] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankUser());
  const [pwOpen, setPwOpen] = useState(false);
  const [pwUser, setPwUser] = useState(null);
  const [pwForm, setPwForm] = useState({ password: "", must_change_password: false });

  const load = async () => {
    try { const r = await api.get("/admin/users"); setRows(r.data || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load users"); }
  };
  const loadRoles = async () => {
    try {
      const { data } = await api.get("/admin/role-catalog");
      const keys = (data?.roles || []).map((r) => r.key);
      if (keys.length) setRoles(keys);
    } catch { /* keep fallback */ }
  };
  const loadDepts = async () => {
    try {
      const { data } = await api.get("/departments");
      setDepartments((data || []).map((d) => d.name || d.code).filter(Boolean));
    } catch { /* leave empty — input falls back to free text */ }
  };
  useEffect(() => { load(); loadRoles(); loadDepts(); }, []);

  const filtered = useMemo(() => {
    let arr = rows;
    if (filterRole) arr = arr.filter((r) => r.role === filterRole);
    if (filterStatus === "active") arr = arr.filter((r) => r.active !== false);
    if (filterStatus === "inactive") arr = arr.filter((r) => r.active === false);
    if (q.trim()) {
      const s = q.toLowerCase();
      arr = arr.filter((r) =>
        (r.email || "").toLowerCase().includes(s) ||
        (r.name || "").toLowerCase().includes(s) ||
        (r.department || "").toLowerCase().includes(s)
      );
    }
    return arr;
  }, [rows, q, filterRole, filterStatus]);

  const save = async () => {
    if (editing) {
      const patch = {
        name: form.name, role: form.role, department: form.department, phone: form.phone,
      };
      if (form.email && form.email !== editing.email) patch.email = form.email;
      try { await api.put(`/admin/users/${editing.id}`, patch); toast.success("Updated"); setOpen(false); load(); }
      catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    } else {
      if (!form.email || !form.name || !form.password) { toast.error("Email, name and password required"); return; }
      try { await api.post("/admin/users", form); toast.success("User created · login ready"); setOpen(false); load(); }
      catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    }
  };
  const toggleActive = async (u) => {
    try { await api.post(`/admin/users/${u.id}/toggle-active`); toast.success(u.active === false ? "Activated" : "Deactivated"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const resetPassword = async () => {
    if (!pwForm.password || pwForm.password.length < 8) { toast.error("Password must be ≥ 8 chars"); return; }
    try {
      await api.post(`/admin/users/${pwUser.id}/reset-password`, pwForm);
      toast.success(`Password reset · ${pwUser.email} can login now`);
      setPwOpen(false); setPwUser(null); setPwForm({ password: "", must_change_password: false });
    } catch (e) { toast.error(e.response?.data?.detail || "Reset failed"); }
  };
  const remove = async (u) => {
    if (!window.confirm(`Delete user ${u.email}? This is permanent.`)) return;
    try { await api.delete(`/admin/users/${u.id}`); toast.success("User deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };
  const openCreate = () => { setEditing(null); setForm(blankUser()); setOpen(true); };
  const openEdit = (u) => { setEditing(u); setForm({ ...blankUser(), ...u, password: "" }); setOpen(true); };
  const openReset = (u) => { setPwUser(u); setPwForm({ password: "", must_change_password: false }); setPwOpen(true); };

  return (
    <div className="space-y-6" data-testid="user-management-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Users className="h-3 w-3" /> Admin · User Management
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Users & Logins</h1>
        <p className="text-sm text-muted-foreground mt-1">Create login IDs, set passwords, assign roles, activate or deactivate accounts. Password resets are immediate.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex flex-wrap items-center gap-2">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search email / name / department" value={q} onChange={(e) => setQ(e.target.value)} data-testid="um-search" />
          </div>
          <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)}
                  className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="um-filter-role">
            <option value="">All roles</option>
            {ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
          </select>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                  className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="um-filter-status">
            <option value="">All status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
          <span className="text-[11px] text-muted-foreground ml-2">{filtered.length} of {rows.length}</span>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={openCreate} data-testid="um-add">
              <UserPlus className="h-4 w-4 mr-1.5" /> Create User
            </Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name & Login</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((u) => (
                <TableRow key={u.id} data-testid={`um-row-${u.id}`} className={u.active === false ? "opacity-60" : ""}>
                  <TableCell>
                    <div className="font-semibold text-sm">{u.name || "—"}</div>
                    <div className="text-[11px] text-muted-foreground">{u.email}</div>
                  </TableCell>
                  <TableCell>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-sm border border-border bg-background">{u.role?.replaceAll("_", " ")}</span>
                  </TableCell>
                  <TableCell className="text-sm">{u.department || "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{u.phone || "—"}</TableCell>
                  <TableCell>
                    {u.active === false ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-sm bg-red-100 text-red-900 border border-red-300">
                        <ShieldOff className="h-3 w-3" /> Inactive
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-sm bg-emerald-100 text-emerald-900 border border-emerald-300">
                        <ShieldCheck className="h-3 w-3" /> Active
                      </span>
                    )}
                    {u.must_change_password && (
                      <span className="ml-1 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-sm bg-amber-100 text-amber-900 border border-amber-300" title="Must change password at next login">
                        <ShieldAlert className="h-3 w-3" /> reset
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-[11px] text-muted-foreground">{(u.last_login || "—").slice(0, 16).replace("T", " ")}</TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openEdit(u)} data-testid={`um-edit-${u.id}`}>
                        <Edit2 className="h-3 w-3" />
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openReset(u)} data-testid={`um-reset-${u.id}`} title="Reset password">
                        <KeyRound className="h-3 w-3" />
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => toggleActive(u)} data-testid={`um-toggle-${u.id}`} title={u.active === false ? "Activate" : "Deactivate"}>
                        <Power className="h-3 w-3" />
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(u)} data-testid={`um-delete-${u.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              {editing ? <Edit2 className="h-4 w-4 text-primary" /> : <UserPlus className="h-4 w-4 text-primary" />}
              {editing ? "Edit User" : "Create User"}
            </DialogTitle>
            <DialogDescription>{editing ? "Update profile details. Password is managed separately via the key icon." : "Set login id, password, role and department. The user can log in immediately after save."}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Field label="Login Email *" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="um-form-email" />
            <Field label="Full Name *" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="um-form-name" />
            {!editing && (
              <Field label="Password *" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })}
                     testid="um-form-password" hint="≥ 8 chars; at least one letter and one digit" />
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-wider">Role *</Label>
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                        className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm" data-testid="um-form-role">
                  {ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
                </select>
              </div>
              <Field label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} testid="um-form-dept" type="select" options={departments} />
            </div>
            <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testid="um-form-phone" />
            {!editing && (
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={form.must_change_password} onChange={(e) => setForm({ ...form, must_change_password: e.target.checked })} data-testid="um-form-must-change" />
                Force password change at first login
              </label>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="um-form-save">
              {editing ? "Save Changes" : "Create User"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={pwOpen} onOpenChange={setPwOpen}>
        <DialogContent className="max-w-md rounded-sm">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><KeyRound className="h-4 w-4 text-primary" /> Reset Password</DialogTitle>
            <DialogDescription>
              You're setting a new password for <b>{pwUser?.email}</b>. Any active lockouts will be cleared.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Field label="New Password *" type="password" value={pwForm.password} onChange={(v) => setPwForm({ ...pwForm, password: v })}
                   hint="≥ 8 chars; at least one letter and one digit" testid="um-pw-password" />
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={pwForm.must_change_password}
                     onChange={(e) => setPwForm({ ...pwForm, must_change_password: e.target.checked })} data-testid="um-pw-must-change" />
              Force user to change at next login
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setPwOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={resetPassword} data-testid="um-pw-submit">Reset Password</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", testid, hint, options }) {
  if (type === "select") {
    return (
      <div>
        <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
        <select
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm"
          data-testid={testid}
        >
          <option value="">— select —</option>
          {(options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        {hint && <p className="text-[10px] text-muted-foreground mt-0.5">{hint}</p>}
      </div>
    );
  }
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
      {hint && <p className="text-[10px] text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}
