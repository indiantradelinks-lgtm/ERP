import { useEffect, useMemo, useState } from "react";
import { ShieldCheck, Save, RotateCcw, Search, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Role Register — interactive matrix of (resource × action × role) toggles.
 *
 *  • "Base" values come from code (PERMISSIONS_BASE in backend rbac.py)
 *  • "Effective" is the merged map — what every API gate actually uses
 *  • Toggling a cell creates an "override" entry that REPLACES the base set
 *    for that (resource, action). Reset clears all overrides back to base.
 *  • super_admin is implicit and always allowed (auto-added on save).
 */
export default function RoleRegister() {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});           // { resource: { action: Set<role> } }
  const [overrideMask, setOverrideMask] = useState({}); // { resource: { action: true } } — which cells are explicit overrides
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");

  const load = async () => {
    try {
      const r = await api.get("/admin/role-register");
      setData(r.data);
      // Build draft from EFFECTIVE map (base + override)
      const d = {};
      for (const res of Object.keys(r.data.effective || {})) {
        d[res] = {};
        for (const action of ["read", "write", "delete"]) {
          d[res][action] = new Set(r.data.effective[res][action] || []);
        }
      }
      setDraft(d);
      // Mark which cells are currently overridden
      const mask = {};
      for (const [res, rules] of Object.entries(r.data.overrides || {})) {
        mask[res] = {};
        for (const action of Object.keys(rules)) mask[res][action] = true;
      }
      setOverrideMask(mask);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load role register"); }
  };
  useEffect(() => { load(); }, []);

  const resources = useMemo(() => {
    if (!data) return [];
    let arr = data.resources || [];
    if (q.trim()) arr = arr.filter((r) => r.toLowerCase().includes(q.toLowerCase()));
    return arr;
  }, [data, q]);

  const toggle = (res, action, role) => {
    setDraft((prev) => {
      const next = { ...prev };
      const setRef = new Set(next[res][action] || []);
      if (setRef.has(role)) setRef.delete(role); else setRef.add(role);
      next[res] = { ...next[res], [action]: setRef };
      return next;
    });
    setOverrideMask((prev) => ({ ...prev, [res]: { ...(prev[res] || {}), [action]: true } }));
  };

  const revertCell = (res, action) => {
    if (!data?.base?.[res]?.[action]) return;
    setDraft((prev) => ({
      ...prev,
      [res]: { ...prev[res], [action]: new Set(data.base[res][action] || []) },
    }));
    setOverrideMask((prev) => {
      const next = { ...prev };
      if (next[res]) { const r = { ...next[res] }; delete r[action]; next[res] = r; }
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      // Build overrides payload: only cells that are explicitly overridden
      const overrides = {};
      for (const [res, actions] of Object.entries(overrideMask)) {
        const inner = {};
        for (const action of Object.keys(actions || {})) {
          inner[action] = Array.from(draft[res]?.[action] || []);
        }
        if (Object.keys(inner).length) overrides[res] = inner;
      }
      const r = await api.put("/admin/role-register", { overrides });
      setData(r.data);
      toast.success(`Saved · ${Object.keys(overrides).length} resource(s) overridden`);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const resetAll = async () => {
    if (!window.confirm("Reset all RBAC overrides back to code defaults?")) return;
    try { await api.post("/admin/role-register/reset"); toast.success("All overrides cleared"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Reset failed"); }
  };

  if (!data) return <div className="p-8 text-sm text-muted-foreground">Loading role register…</div>;

  const roles = data.roles.filter((r) => r !== "super_admin");
  const overrideCount = Object.values(overrideMask).reduce((acc, x) => acc + Object.keys(x).length, 0);

  return (
    <div className="space-y-6" data-testid="role-register-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ShieldCheck className="h-3 w-3" /> Admin · Role Register
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Role × Permission Matrix</h1>
        <p className="text-sm text-muted-foreground mt-1">Toggle which roles have <b>read / write / delete</b> access per resource. Changes take effect instantly across all API gates. <span className="text-primary">super_admin is always allowed.</span></p>
      </div>

      <div className="bg-card border border-border rounded-sm sticky top-2 z-10">
        <div className="p-3 flex flex-wrap items-center gap-2">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search resource…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="rr-search" />
          </div>
          <div className="text-[11px] text-muted-foreground">
            {resources.length} of {data.resources.length} resources · <span className="text-primary font-semibold">{overrideCount} override(s) pending</span>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="rounded-sm h-9" onClick={resetAll} data-testid="rr-reset-all">
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset to Defaults
            </Button>
            <Button className="rounded-sm h-9" onClick={save} disabled={saving} data-testid="rr-save">
              <Save className="h-3.5 w-3.5 mr-1.5" /> {saving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        </div>
      </div>

      <Legend />

      <div className="space-y-4">
        {resources.map((res) => (
          <ResourceCard key={res} resource={res}
                        roles={roles} draft={draft[res] || {}}
                        base={data.base[res] || {}} overrideMask={overrideMask[res] || {}}
                        onToggle={(a, r) => toggle(res, a, r)} onRevert={(a) => revertCell(res, a)} />
        ))}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1"><span className="w-3 h-3 inline-block bg-emerald-200 border border-emerald-400" /> Allowed</span>
      <span className="inline-flex items-center gap-1"><span className="w-3 h-3 inline-block bg-background border border-border" /> Not allowed</span>
      <span className="inline-flex items-center gap-1"><span className="w-3 h-3 inline-block bg-primary/15 border border-primary" /> Wildcard "*" (everyone)</span>
      <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3 w-3 text-amber-600" /> Overridden — differs from code default</span>
    </div>
  );
}

function ResourceCard({ resource, roles, draft, base, overrideMask, onToggle, onRevert }) {
  return (
    <div className="bg-card border border-border rounded-sm" data-testid={`rr-resource-${resource}`}>
      <div className="px-4 py-2 border-b border-border flex items-center gap-2">
        <span className="font-display font-black text-base">{resource.replaceAll("_", " ").toUpperCase()}</span>
        {Object.keys(overrideMask).length > 0 && (
          <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-amber-100 text-amber-900 border border-amber-300">
            <AlertTriangle className="h-2.5 w-2.5" /> {Object.keys(overrideMask).length} override(s)
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead className="bg-muted/30">
            <tr>
              <th className="px-3 py-2 text-left w-24 sticky left-0 bg-muted/30">Action</th>
              <th className="px-2 py-2 text-center w-16 bg-primary/5">
                <span className="inline-flex items-center gap-1 text-[10px]">"*"</span>
                <div className="text-[9px] text-muted-foreground normal-case">everyone</div>
              </th>
              {roles.map((r) => (
                <th key={r} className="px-1 py-2 text-center" title={r}>
                  <div className="text-[10px] uppercase tracking-wider whitespace-nowrap rotate-[-30deg] origin-center inline-block w-8">{shortRole(r)}</div>
                </th>
              ))}
              <th className="px-2 py-2 text-right w-20">Revert</th>
            </tr>
          </thead>
          <tbody>
            {["read", "write", "delete"].map((action) => {
              const allowed = draft[action] || new Set();
              const overridden = !!overrideMask[action];
              const baseSet = new Set(base[action] || []);
              return (
                <tr key={action} className="border-t border-border" data-testid={`rr-row-${resource}-${action}`}>
                  <td className={`px-3 py-1.5 font-semibold sticky left-0 ${overridden ? "bg-amber-50" : "bg-background"}`}>
                    <span className="inline-flex items-center gap-1">
                      {overridden && <AlertTriangle className="h-3 w-3 text-amber-600" />}
                      <span className={action === "delete" ? "text-red-700" : action === "write" ? "text-amber-700" : "text-emerald-700"}>{action}</span>
                    </span>
                  </td>
                  <Cell on={allowed.has("*")} baseOn={baseSet.has("*")} wildcard
                        onClick={() => onToggle(action, "*")} testid={`rr-cell-${resource}-${action}-wild`} />
                  {roles.map((r) => (
                    <Cell key={r} on={allowed.has(r) || allowed.has("*")} baseOn={baseSet.has(r) || baseSet.has("*")} disabledByWild={allowed.has("*")}
                          onClick={() => onToggle(action, r)} testid={`rr-cell-${resource}-${action}-${r}`} />
                  ))}
                  <td className="px-2 py-1.5 text-right">
                    {overridden && (
                      <button className="text-[10px] text-primary hover:underline" onClick={() => onRevert(action)} title="Revert to code default" data-testid={`rr-revert-${resource}-${action}`}>
                        Revert
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Cell({ on, baseOn, wildcard, disabledByWild, onClick, testid }) {
  const diff = on !== baseOn;
  const bg = wildcard && on
    ? "bg-primary/15 border-primary"
    : on
      ? "bg-emerald-100 border-emerald-400 hover:bg-emerald-200"
      : "bg-background border-border hover:bg-muted";
  return (
    <td className="px-1 py-1.5 text-center">
      <button onClick={onClick} disabled={disabledByWild && !wildcard}
              className={`relative h-6 w-6 border rounded-sm transition-colors ${bg} ${disabledByWild && !wildcard ? "opacity-30" : ""}`}
              data-testid={testid} title={on ? "Allowed" : "Not allowed"}>
        {on && <CheckCircle2 className="h-3.5 w-3.5 mx-auto text-emerald-700" />}
        {diff && <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-amber-500 border border-white" />}
      </button>
    </td>
  );
}

function shortRole(r) {
  const map = {
    director: "DIR", general_manager: "GM", dept_head: "DPT", project_manager: "PM",
    site_engineer: "SE", supervisor: "SUP", store_incharge: "STO", accounts_executive: "ACC",
    hr_executive: "HR", safety_officer: "SAF", purchase_officer: "PUR", sales_executive: "SAL",
    client_rep: "CLI", vendor: "VEN",
  };
  return map[r] || r.slice(0, 4).toUpperCase();
}
