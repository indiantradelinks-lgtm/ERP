import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { Plus } from "lucide-react";
import { toast } from "sonner";

const ROLES = ["super_admin", "director", "general_manager", "dept_head", "project_manager", "site_engineer", "supervisor", "store_incharge", "accounts_executive", "hr_executive", "safety_officer", "purchase_officer", "client_rep", "vendor"];

export default function Profile() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "site_engineer", department: "", phone: "" });

  const load = async () => {
    try { const { data } = await api.get("/auth/users"); setUsers(data); } catch (e) { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    try {
      await api.post("/auth/register", form);
      toast.success("User created");
      setOpen(false);
      setForm({ email: "", password: "", name: "", role: "site_engineer", department: "", phone: "" });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  if (!user) return null;
  const initials = (user.name || "U").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="space-y-8">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">User</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Profile & Access</h1>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-sm p-6 lg:col-span-1">
          <div className="flex items-center gap-4">
            <Avatar className="h-16 w-16 rounded-sm">
              <AvatarFallback className="rounded-sm bg-primary text-primary-foreground font-display font-black text-xl">{initials}</AvatarFallback>
            </Avatar>
            <div>
              <div className="font-display font-bold text-lg">{user.name}</div>
              <div className="text-xs text-muted-foreground">{user.email}</div>
              <div className="mt-2"><StatusBadge text={user.role?.replaceAll("_", " ")} tone="primary" /></div>
            </div>
          </div>
          <div className="h-px bg-border my-5" />
          <div className="space-y-3 text-sm">
            <Row label="Department" value={user.department || "—"} />
            <Row label="Phone" value={user.phone || "—"} />
            <Row label="Joined" value={(user.created_at || "").slice(0, 10)} />
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm lg:col-span-2">
          <div className="flex items-center justify-between p-4 border-b border-border">
            <div>
              <div className="font-display font-bold text-lg">Team Members</div>
              <div className="text-xs text-muted-foreground">Users registered under this tenant.</div>
            </div>
            {user.role === "super_admin" && (
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button className="rounded-sm h-9" data-testid="add-user-btn"><Plus className="h-4 w-4 mr-1" /> Add User</Button>
                </DialogTrigger>
                <DialogContent className="max-w-xl rounded-sm">
                  <DialogHeader><DialogTitle className="font-display">New User</DialogTitle></DialogHeader>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2">
                    {[
                      { k: "name", l: "Full Name" },
                      { k: "email", l: "Email" },
                      { k: "password", l: "Password" },
                      { k: "department", l: "Department" },
                      { k: "phone", l: "Phone" },
                    ].map((f) => (
                      <div key={f.k} className="flex flex-col gap-1.5">
                        <Label className="text-xs uppercase tracking-wider">{f.l}</Label>
                        <Input value={form[f.k]} onChange={(e) => setForm({ ...form, [f.k]: e.target.value })} className="h-9 rounded-sm" data-testid={`user-${f.k}`} />
                      </div>
                    ))}
                    <div className="flex flex-col gap-1.5 md:col-span-2">
                      <Label className="text-xs uppercase tracking-wider">Role</Label>
                      <select className="h-9 rounded-sm border border-input bg-background px-2 text-sm" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="user-role">
                        {ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
                      </select>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">Cancel</Button>
                    <Button onClick={submit} className="rounded-sm" data-testid="user-save">Create</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Email</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Role</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Dept</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-semibold">{u.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{u.email}</TableCell>
                    <TableCell><StatusBadge text={u.role?.replaceAll("_", " ")} tone={u.role === "super_admin" ? "primary" : "neutral"} /></TableCell>
                    <TableCell className="text-sm">{u.department || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground text-xs uppercase tracking-wider">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}
