import { useEffect, useState } from "react";
import { Grid3x3, Save, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * Role × Department matrix — super_admin toggles which departments a role can
 * see on the Department Launcher. Empty row falls back to ALL departments.
 */
export default function RoleDepartmentMap() {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { reload(); }, []);

  const reload = () => {
    api.get("/admin/role-department-map")
      .then((r) => { setData(r.data); setDraft(r.data.map || {}); })
      .catch(() => toast.error("Failed to load mapping"));
  };

  const toggle = (role, deptSlug) => {
    setDraft((d) => {
      const cur = new Set(d[role] || []);
      cur.has(deptSlug) ? cur.delete(deptSlug) : cur.add(deptSlug);
      return { ...d, [role]: Array.from(cur) };
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/role-department-map", { map: draft });
      toast.success("Role-department mapping saved");
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  if (!data) return <div className="text-sm text-muted-foreground" data-testid="rdm-loading">Loading…</div>;

  const { roles, departments } = data;

  return (
    <div className="space-y-6" data-testid="role-department-map">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Grid3x3 className="h-3 w-3" /> Super Admin · Workspace Access
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Role × Department Matrix</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Toggle which departments each role sees on the Module Launcher.
          <br />Empty row → user sees all departments (fail-open). <strong>super_admin</strong> always sees everything regardless of this map.
        </p>
      </div>

      <div className="flex gap-2">
        <Button className="rounded-sm" onClick={save} disabled={saving} data-testid="rdm-save">
          <Save className="h-4 w-4 mr-1.5" /> {saving ? "Saving…" : "Save Mapping"}
        </Button>
        <Button variant="outline" className="rounded-sm" onClick={() => setDraft(data.map)} data-testid="rdm-reset">
          <RotateCcw className="h-4 w-4 mr-1.5" /> Reset
        </Button>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto">
        <table className="w-full text-sm" data-testid="rdm-table">
          <thead>
            <tr className="bg-muted/40 border-b border-border">
              <th className="text-left p-3 text-[10px] uppercase tracking-wider sticky left-0 bg-muted/40 z-10">Role</th>
              {departments.map((d) => (
                <th key={d.slug} className="text-center p-3 text-[10px] uppercase tracking-wider">
                  <div className="flex flex-col items-center gap-0.5">
                    <span className="text-[10px] font-bold">{d.title}</span>
                    <span className="text-[9px] text-muted-foreground font-mono-data">{d.slug}</span>
                  </div>
                </th>
              ))}
              <th className="text-center p-3 text-[10px] uppercase tracking-wider">Count</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => {
              const set = new Set(draft[role] || []);
              return (
                <tr key={role} className="border-b border-border hover:bg-muted/30" data-testid={`rdm-row-${role}`}>
                  <td className="p-3 font-semibold sticky left-0 bg-card capitalize">{role.replaceAll("_", " ")}</td>
                  {departments.map((d) => {
                    const active = set.has(d.slug);
                    return (
                      <td key={d.slug} className="p-2 text-center">
                        <button
                          onClick={() => toggle(role, d.slug)}
                          className={cn(
                            "h-7 w-12 rounded-sm border text-[10px] font-bold uppercase tracking-wider transition-colors",
                            active
                              ? "bg-primary text-primary-foreground border-primary"
                              : "border-border text-muted-foreground hover:border-primary/40",
                          )}
                          data-testid={`rdm-cell-${role}-${d.slug}`}
                          aria-label={`${role} can see ${d.slug}`}
                        >
                          {active ? "ON" : "—"}
                        </button>
                      </td>
                    );
                  })}
                  <td className="p-3 text-center font-display font-bold tabular">{set.size}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
