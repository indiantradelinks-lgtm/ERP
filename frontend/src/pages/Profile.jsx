import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";
import { LayoutGrid, Briefcase, FileText, Wallet, Boxes, ShieldAlert, Car, HardHat, Truck, ArrowRight, Users, CalendarDays, ChevronLeft, ChevronRight, Eye } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_TONE = {
  P: "bg-green-100 text-green-800 border-green-300",
  A: "bg-red-100 text-red-800 border-red-300",
  HD: "bg-amber-100 text-amber-800 border-amber-300",
  L: "bg-blue-100 text-blue-800 border-blue-300",
  WO: "bg-slate-100 text-slate-700 border-slate-300",
  H: "bg-purple-100 text-purple-800 border-purple-300",
  OD: "bg-cyan-100 text-cyan-800 border-cyan-300",
};
const currentMonth = () => new Date().toISOString().slice(0, 7);

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

      {/* Personal attendance dashboard — self-only, view-only */}
      <MyAttendance />

      {/* Personal leave balances + pending requests — self-only, view-only */}
      <MyLeave />
    </div>
  );
}

const LEAVE_STATUS_TONE = {
  pending: "bg-amber-100 text-amber-900 border-amber-300",
  approved: "bg-emerald-100 text-emerald-900 border-emerald-300",
  rejected: "bg-red-100 text-red-900 border-red-300",
  cancelled: "bg-secondary text-muted-foreground border-border",
};

function MyLeave() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.get("/hr/leave/my-summary")
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="bg-card border border-border rounded-sm p-6" data-testid="my-leave-card">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <div className="font-display font-bold text-lg flex items-center gap-2">
            <Wallet className="h-4 w-4 text-primary" /> My Leave
          </div>
          <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
            <Eye className="h-3 w-3" /> View-only — your balances & requests for {data?.year || new Date().getFullYear()}
          </div>
        </div>
      </div>

      {loading && <div className="text-sm text-muted-foreground py-4">Loading leave data…</div>}
      {!loading && data && !data.linked && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-sm" data-testid="my-leave-not-linked">
          No employee record is linked to your login — contact HR to link your account.
        </div>
      )}
      {!loading && data?.linked && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">Leave Balances</div>
            {(data.balances || []).length === 0 && (
              <div className="text-sm text-muted-foreground py-4 border border-dashed border-border rounded-sm text-center">
                No leave balances granted yet.
              </div>
            )}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {(data.balances || []).map((b) => (
                <div key={b.leave_type} className="border border-border rounded-sm p-2.5 bg-muted/20" data-testid={`my-leave-bal-${b.leave_type}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold font-mono-data">{b.leave_type}</span>
                    <span className="text-[9px] text-muted-foreground uppercase truncate ml-1">{b.leave_type_label}</span>
                  </div>
                  <div className="text-xl font-black tabular mt-1">{b.balance}</div>
                  <div className="text-[10px] text-muted-foreground">of {b.granted} · used {b.used}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">
              Pending Requests ({(data.pending || []).length})
            </div>
            {(data.pending || []).length === 0 && (
              <div className="text-sm text-muted-foreground py-4 border border-dashed border-border rounded-sm text-center" data-testid="my-leave-no-pending">
                No pending leave requests.
              </div>
            )}
            <ul className="space-y-1.5">
              {(data.pending || []).map((a) => (
                <li key={a.id} className="flex items-center justify-between border border-border rounded-sm p-2.5 bg-muted/20" data-testid={`my-leave-pending-${a.id}`}>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">
                      {a.leave_type} · {a.from_date} → {a.to_date}
                      {a.half_day && <span className="ml-1 text-[10px] text-muted-foreground">(½)</span>}
                    </div>
                    <div className="text-[11px] text-muted-foreground truncate">{a.days} day(s){a.reason ? ` · ${a.reason}` : ""}</div>
                  </div>
                  <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded-sm border flex-shrink-0 ml-2", LEAVE_STATUS_TONE[a.status])}>
                    {a.status}
                  </span>
                </li>
              ))}
            </ul>
            {(data.recent || []).filter((a) => a.status !== "pending").length > 0 && (
              <>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mt-4 mb-2">Recent</div>
                <ul className="space-y-1">
                  {(data.recent || []).filter((a) => a.status !== "pending").slice(0, 3).map((a) => (
                    <li key={a.id} className="flex items-center justify-between text-xs text-muted-foreground px-1" data-testid={`my-leave-recent-${a.id}`}>
                      <span>{a.leave_type} · {a.from_date} → {a.to_date} ({a.days}d)</span>
                      <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded-sm border", LEAVE_STATUS_TONE[a.status])}>{a.status}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MyAttendance() {
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.get("/hr2/attendance-plus/my/monthly", { params: { month } })
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month]);

  const shiftMonth = (delta) => {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    const next = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    if (next > currentMonth()) return;
    setMonth(next);
  };

  const monthLabel = new Date(month + "-01T00:00:00").toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const s = data?.summary;

  return (
    <div className="bg-card border border-border rounded-sm p-6" data-testid="my-attendance-card">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <div className="font-display font-bold text-lg flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-primary" /> My Attendance
          </div>
          <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
            <Eye className="h-3 w-3" /> View-only — your own records, month-wise
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" className="h-8 w-8 p-0 rounded-sm" onClick={() => shiftMonth(-1)} data-testid="my-att-prev">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="text-sm font-bold w-40 text-center" data-testid="my-att-month">{monthLabel}</div>
          <Button variant="outline" className="h-8 w-8 p-0 rounded-sm" onClick={() => shiftMonth(1)}
                  disabled={month >= currentMonth()} data-testid="my-att-next">
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {loading && <div className="text-sm text-muted-foreground py-6">Loading attendance…</div>}
      {!loading && data && !data.linked && (
        <div className="text-sm text-muted-foreground py-8 text-center border border-dashed border-border rounded-sm" data-testid="my-att-not-linked">
          No employee record is linked to your login — contact HR to link your account.
        </div>
      )}
      {!loading && data?.linked && (
        <>
          <div className="text-xs text-muted-foreground mb-3" data-testid="my-att-employee">
            {data.employee?.name} {data.employee?.code && `(${data.employee.code})`}
            {data.employee?.designation && ` · ${data.employee.designation}`}
            {` · ${data.employee?.project_code || "Head Office"}`}
          </div>
          {s && (
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-8 gap-2 mb-4">
              {[["Paid Days", s.paid_days], ["P", s.P], ["HD", s.HD], ["A", s.A], ["L", s.L],
                ["WO", s.WO], ["H", s.H], ["OD", s.OD]].map(([k, v]) => (
                <div key={k} className="border border-border rounded-sm p-2 text-center bg-muted/20" data-testid={`my-att-sum-${k.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
                  <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{k}</div>
                  <div className="text-lg font-black tabular">{v}</div>
                </div>
              ))}
            </div>
          )}
          <div className="border border-border rounded-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2">Date</th>
                  <th className="text-left px-3 py-2">Day</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">In</th>
                  <th className="text-left px-3 py-2">Out</th>
                  <th className="text-right px-3 py-2">Hours</th>
                  <th className="text-left px-3 py-2">Remarks</th>
                </tr>
              </thead>
              <tbody>
                {(data.rows || []).length === 0 && (
                  <tr><td colSpan={7} className="text-center py-8 text-muted-foreground">No attendance marked for {monthLabel}.</td></tr>
                )}
                {(data.rows || []).map((r) => (
                  <tr key={r.date} className="border-t border-border/60" data-testid={`my-att-row-${r.date}`}>
                    <td className="px-3 py-1.5 font-mono-data text-xs">{r.date}</td>
                    <td className="px-3 py-1.5 text-xs text-muted-foreground">
                      {new Date(r.date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short" })}
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded-sm border", STATUS_TONE[r.code] || "bg-secondary border-border")}>
                        {r.code || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-xs tabular">{r.in_time || "—"}</td>
                    <td className="px-3 py-1.5 text-xs tabular">{r.out_time || "—"}</td>
                    <td className="px-3 py-1.5 text-xs text-right tabular">{r.total_hours ?? "—"}</td>
                    <td className="px-3 py-1.5 text-xs text-muted-foreground max-w-[240px] truncate" title={r.remarks || ""}>{r.remarks || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
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
