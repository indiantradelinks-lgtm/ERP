import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";
import { LayoutGrid, Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck, ArrowRight, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const DEPT_ICONS = { Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck, LayoutGrid };
const TONE_TEXT = {
  primary: "text-primary",
  info: "text-chart-3",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  neutral: "text-foreground",
};

export default function Profile() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tiles, setTiles] = useState(null);

  // Fetch the department launcher tiles for THIS user's role so they can see where they have access.
  useEffect(() => {
    if (!user?.role) return;
    api.get(`/admin/role-preview/${user.role}`)
      .then((r) => setTiles(r.data))
      .catch(() => setTiles(null));
  }, [user?.role]);

  if (!user) return null;
  const initials = (user.name || "U").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="space-y-8" data-testid="profile-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">User</div>
          <h1 className="font-display font-black text-3xl tracking-tight">My Profile & Access</h1>
          <p className="text-sm text-muted-foreground mt-1">Your account information and the workspaces you have access to.</p>
        </div>
        {user.role === "super_admin" && (
          <Button
            className="rounded-sm h-9"
            variant="outline"
            onClick={() => navigate("/app/admin/users")}
            data-testid="profile-goto-user-management"
          >
            <Users className="h-4 w-4 mr-1.5" /> Go to User Management
          </Button>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* My account card */}
        <div className="bg-card border border-border rounded-sm p-6 lg:col-span-1" data-testid="profile-my-card">
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
            <Row label="Joined" value={(user.created_at || "").slice(0, 10) || "—"} />
            <Row label="Last login" value={(user.last_login || "").slice(0, 19).replace("T", " ") || "—"} />
          </div>
        </div>

        {/* My workspace access */}
        <div className="bg-card border border-border rounded-sm lg:col-span-2 p-6" data-testid="profile-access-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-display font-bold text-lg">My Workspace Access</div>
              <div className="text-xs text-muted-foreground">Modules you can open from the Department Launcher.</div>
            </div>
            {tiles && (
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                {tiles.departments?.length || 0} tile{(tiles.departments?.length || 0) !== 1 ? "s" : ""}
              </div>
            )}
          </div>
          {!tiles && <div className="text-sm text-muted-foreground py-6">Loading workspace access…</div>}
          {tiles && (
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {(tiles.departments || []).map((d) => {
                const Icon = DEPT_ICONS[d.icon] || LayoutGrid;
                return (
                  <li
                    key={d.slug}
                    className="flex items-start gap-3 p-3 rounded-sm border border-border bg-muted/20 hover:bg-muted/40 transition-colors"
                    data-testid={`profile-tile-${d.slug}`}
                  >
                    <div className={cn("h-8 w-8 grid place-items-center rounded-sm bg-background border border-border flex-shrink-0", TONE_TEXT[d.color] || TONE_TEXT.neutral)}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{d.title}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{d.tagline}</div>
                    </div>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground mt-1.5" />
                  </li>
                );
              })}
              {tiles.departments?.length === 0 && (
                <li className="md:col-span-2 text-center text-sm text-muted-foreground py-8 border border-dashed border-border rounded-sm">
                  No workspaces assigned yet — please contact your administrator.
                </li>
              )}
            </ul>
          )}
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
