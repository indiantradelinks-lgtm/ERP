import { useEffect, useMemo, useState } from "react";
import { ShieldCheck, Save, RotateCcw, Search, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Lock, Globe, List, PanelsTopLeft, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { MENU_ITEMS, DEPARTMENTS } from "@/config/menuConfig";

/**
 * Role × Permission Matrix
 *  • "By Menu" view mirrors the sidebar hierarchy exactly (Department → Sub-menu group → Menu item),
 *    driven from the same menuConfig the sidebar renders — nothing can go missing.
 *  • "By Resource" view is the flat API-resource matrix (covers resources not bound to any menu).
 *  • Toggling writes an override for the menu's bound resource; menus sharing a resource move together.
 *  • super_admin is implicit and always allowed. Saves apply instantly to all API gates,
 *    and the sidebar/permissions of the current session refresh immediately.
 */
const ACTIONS = ["read", "write", "delete"];
const ACTION_LABEL = { read: "View", write: "Create / Edit", delete: "Delete" };
const ACTION_LETTER = { read: "V", write: "E", delete: "D" };

export default function RoleRegister() {
  const { refresh } = useAuth();
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});
  const [overrideMask, setOverrideMask] = useState({});
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  const [view, setView] = useState("menu");
  const [copyOpen, setCopyOpen] = useState(false);
  const [openDepts, setOpenDepts] = useState(() => new Set([DEPARTMENTS[0]?.key]));

  const load = async () => {
    try {
      const r = await api.get("/admin/role-register");
      setData(r.data);
      const d = {};
      for (const res of Object.keys(r.data.effective || {})) {
        d[res] = {};
        for (const action of ACTIONS) d[res][action] = new Set(r.data.effective[res][action] || []);
      }
      setDraft(d);
      const mask = {};
      for (const [res, rules] of Object.entries(r.data.overrides || {})) {
        mask[res] = {};
        for (const action of Object.keys(rules)) mask[res][action] = true;
      }
      setOverrideMask(mask);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load role register"); }
  };
  useEffect(() => { load(); }, []);

  const toggle = (res, action, role) => {
    setDraft((prev) => {
      const next = { ...prev };
      const setRef = new Set(next[res]?.[action] || []);
      if (setRef.has(role)) setRef.delete(role); else setRef.add(role);
      next[res] = { ...(next[res] || {}), [action]: setRef };
      return next;
    });
    setOverrideMask((prev) => ({ ...prev, [res]: { ...(prev[res] || {}), [action]: true } }));
  };

  const revertCell = (res, action) => {
    if (!data?.base?.[res]?.[action]) return;
    setDraft((prev) => ({ ...prev, [res]: { ...prev[res], [action]: new Set(data.base[res][action] || []) } }));
    setOverrideMask((prev) => {
      const next = { ...prev };
      if (next[res]) { const r = { ...next[res] }; delete r[action]; next[res] = r; }
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const overrides = {};
      for (const [res, actions] of Object.entries(overrideMask)) {
        const inner = {};
        for (const action of Object.keys(actions || {})) inner[action] = Array.from(draft[res]?.[action] || []);
        if (Object.keys(inner).length) overrides[res] = inner;
      }
      const r = await api.put("/admin/role-register", { overrides });
      setData(r.data);
      await refresh();   // instantly refresh sidebar / page / button permissions for this session
      toast.success(`Saved — permissions live everywhere · ${Object.keys(overrides).length} resource(s) overridden`);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const resetAll = async () => {
    if (!window.confirm("Reset all RBAC overrides back to code defaults?")) return;
    try { await api.post("/admin/role-register/reset"); await refresh(); toast.success("All overrides cleared"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Reset failed"); }
  };

  // ── Sidebar hierarchy tree (Department → parentLabel group → items) ──
  const menuTree = useMemo(() => {
    const s = q.trim().toLowerCase();
    return DEPARTMENTS.map((dept) => {
      const items = MENU_ITEMS.filter((it) => it.department === dept.key)
        .filter((it) => !s || it.label.toLowerCase().includes(s) || (it.perm || "").toLowerCase().includes(s) || (it.parentLabel || "").toLowerCase().includes(s));
      const groups = [];
      const idx = {};
      for (const it of items) {
        const key = it.parentLabel || "";
        if (!(key in idx)) { idx[key] = groups.length; groups.push({ parent: key, items: [] }); }
        groups[idx[key]].items.push(it);
      }
      return { dept, groups, count: items.length };
    }).filter((d) => d.count > 0);
  }, [q]);

  const mappedResources = useMemo(() => new Set(MENU_ITEMS.map((i) => i.perm).filter(Boolean)), []);
  const unmappedResources = useMemo(() => {
    if (!data) return [];
    let arr = (data.resources || []).filter((r) => !mappedResources.has(r));
    if (q.trim()) arr = arr.filter((r) => r.toLowerCase().includes(q.toLowerCase()));
    return arr;
  }, [data, mappedResources, q]);

  const flatResources = useMemo(() => {
    if (!data) return [];
    let arr = data.resources || [];
    if (q.trim()) arr = arr.filter((r) => r.toLowerCase().includes(q.toLowerCase()));
    return arr;
  }, [data, q]);

  if (!data) return <div className="p-8 text-sm text-muted-foreground">Loading role register…</div>;

  const roles = data.roles.filter((r) => r !== "super_admin");
  const overrideCount = Object.values(overrideMask).reduce((acc, x) => acc + Object.keys(x).length, 0);
  const toggleDept = (key) => setOpenDepts((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  const expandAll = () => setOpenDepts(new Set(DEPARTMENTS.map((d) => d.key)));
  const collapseAll = () => setOpenDepts(new Set());

  return (
    <div className="space-y-5" data-testid="role-register-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ShieldCheck className="h-3 w-3" /> Admin · Role Register
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Role × Permission Matrix</h1>
        <p className="text-sm text-muted-foreground mt-1">
          The <b>By Menu</b> view mirrors the sidebar exactly — every department, sub-menu and nested menu.
          Toggle <b>V</b>iew / Create-<b>E</b>dit / <b>D</b>elete per role. Saves apply instantly to the sidebar, pages, buttons and every API gate.
          <span className="text-primary"> super_admin always has full access.</span>
        </p>
      </div>

      <div className="bg-card border border-border rounded-sm sticky top-2 z-20">
        <div className="p-3 flex flex-wrap items-center gap-2">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search menu / resource…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="rr-search" />
          </div>
          <div className="flex border border-border rounded-sm overflow-hidden text-xs">
            <button className={`px-3 py-2 flex items-center gap-1.5 ${view === "menu" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setView("menu")} data-testid="rr-view-menu">
              <PanelsTopLeft className="h-3.5 w-3.5" /> By Menu
            </button>
            <button className={`px-3 py-2 flex items-center gap-1.5 ${view === "resource" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setView("resource")} data-testid="rr-view-resource">
              <List className="h-3.5 w-3.5" /> By Resource
            </button>
          </div>
          {view === "menu" && (
            <div className="flex gap-1 text-[11px]">
              <Button size="sm" variant="ghost" className="h-9" onClick={expandAll} data-testid="rr-expand-all">Expand all</Button>
              <Button size="sm" variant="ghost" className="h-9" onClick={collapseAll} data-testid="rr-collapse-all">Collapse all</Button>
            </div>
          )}
          <div className="text-[11px] text-muted-foreground">
            {roles.length + 1} roles · <span className="text-primary font-semibold">{overrideCount} override(s)</span>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="rounded-sm h-9" onClick={() => setCopyOpen(true)} data-testid="rr-copy-open">
              <Copy className="h-3.5 w-3.5 mr-1.5" /> Copy Permissions
            </Button>
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

      {view === "menu" ? (
        <div className="space-y-3">
          {menuTree.map(({ dept, groups, count }) => {
            const open = openDepts.has(dept.key) || !!q.trim();
            return (
              <div key={dept.key} className="bg-card border border-border rounded-sm" data-testid={`rr-dept-${dept.key}`}>
                <button className="w-full px-4 py-2.5 flex items-center gap-2 text-left" onClick={() => toggleDept(dept.key)} data-testid={`rr-dept-toggle-${dept.key}`}>
                  {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <span className="font-display font-black text-base">{dept.label}</span>
                  <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{count} menu{count > 1 ? "s" : ""}</span>
                  {dept.superAdminOnly && <SuperOnlyBadge />}
                </button>
                {open && (
                  <div className="overflow-x-auto border-t border-border">
                    <table className="w-full text-[11px]">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="px-3 py-2 text-left min-w-[260px] sticky left-0 bg-muted/30 z-10">Menu (as in sidebar)</th>
                          <th className="px-1 py-2 text-center w-12 bg-primary/5" title='Wildcard "*" — everyone'>
                            <Globe className="h-3 w-3 mx-auto" /><div className="text-[8px] text-muted-foreground">everyone</div>
                          </th>
                          {roles.map((r) => (
                            <th key={r} className="px-0.5 py-2 text-center min-w-[52px]" title={r}>
                              <div className="text-[9px] uppercase tracking-wide leading-tight break-words max-w-[52px] mx-auto">{r.replaceAll("_", " ")}</div>
                            </th>
                          ))}
                          <th className="px-2 py-2 w-14"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {groups.map(({ parent, items }) => (
                          <GroupRows key={parent || "__root"} parent={parent} items={items} roles={roles}
                                     draft={draft} base={data.base} overrideMask={overrideMask}
                                     onToggle={toggle} onRevert={revertCell} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}

          {unmappedResources.length > 0 && (
            <div className="bg-card border border-border rounded-sm" data-testid="rr-dept-other">
              <div className="px-4 py-2.5 flex items-center gap-2">
                <span className="font-display font-black text-base">Other API Resources</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">not bound to a sidebar menu — nothing is hidden from the matrix</span>
              </div>
              <div className="border-t border-border divide-y divide-border">
                {unmappedResources.map((res) => (
                  <ResourceRows key={res} resource={res} roles={roles} draft={draft[res] || {}}
                                base={data.base[res] || {}} overrideMask={overrideMask[res] || {}}
                                onToggle={(a, r) => toggle(res, a, r)} onRevert={(a) => revertCell(res, a)} />
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {flatResources.map((res) => (
            <div key={res} className="bg-card border border-border rounded-sm" data-testid={`rr-resource-${res}`}>
              <ResourceRows resource={res} roles={roles} draft={draft[res] || {}}
                            base={data.base[res] || {}} overrideMask={overrideMask[res] || {}}
                            onToggle={(a, r) => toggle(res, a, r)} onRevert={(a) => revertCell(res, a)} />
            </div>
          ))}
        </div>
      )}
      <CopyPermissionsDialog open={copyOpen} onOpenChange={setCopyOpen} roles={data.roles || []} onDone={load} />
    </div>
  );
}

function CopyPermissionsDialog({ open, onOpenChange, roles, onDone }) {
  const [src, setSrc] = useState("");
  const [tgt, setTgt] = useState("");
  const [busy, setBusy] = useState(false);
  const targets = roles.filter((r) => r !== "super_admin");

  const submit = async () => {
    if (!src || !tgt) return toast.error("Pick both source and target roles");
    if (src === tgt) return toast.error("Source and target must differ");
    setBusy(true);
    try {
      const r = await api.post("/admin/role-register/copy", { source_role: src, target_role: tgt });
      toast.success(`Copied ${src} → ${tgt} (${r.data.actions_updated} permission(s) updated)`);
      onOpenChange(false);
      setSrc(""); setTgt("");
      onDone();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Copy failed");
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Copy className="h-4 w-4" /> Copy Role Permissions</DialogTitle>
          <DialogDescription>
            The target role's View/Edit/Delete access will be changed to exactly mirror the source role — across every module.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider mb-1">Copy from (source)</div>
            <select value={src} onChange={(e) => setSrc(e.target.value)}
              className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-copy-source">
              <option value="">— select role —</option>
              {roles.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider mb-1">Apply to (target)</div>
            <select value={tgt} onChange={(e) => setTgt(e.target.value)}
              className="w-full h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="rr-copy-target">
              <option value="">— select role —</option>
              {targets.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div className="flex items-start gap-2 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-2">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
            This overwrites the target role's current permissions everywhere. You can still adjust individual cells afterwards.
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button className="rounded-sm" onClick={submit} disabled={busy} data-testid="rr-copy-submit">
            {busy ? "Copying…" : "Copy Permissions"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground items-center">
      <span className="inline-flex items-center gap-1"><MiniDot on tone="read" /> V = View (read)</span>
      <span className="inline-flex items-center gap-1"><MiniDot on tone="write" /> E = Create / Edit (write)</span>
      <span className="inline-flex items-center gap-1"><MiniDot on tone="delete" /> D = Delete</span>
      <span className="inline-flex items-center gap-1"><span className="w-3 h-3 inline-block bg-background border border-border rounded-[3px]" /> Not allowed</span>
      <span className="inline-flex items-center gap-1"><Globe className="h-3 w-3" /> "everyone" column = all authenticated users</span>
      <span className="inline-flex items-center gap-1"><AlertTriangle className="h-3 w-3 text-amber-600" /> Overridden vs code default</span>
      <span className="inline-flex items-center gap-1"><Lock className="h-3 w-3" /> Super-Admin-only menu</span>
    </div>
  );
}

function SuperOnlyBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-slate-100 text-slate-700 border border-slate-300">
      <Lock className="h-2.5 w-2.5" /> Super Admin only
    </span>
  );
}

function GroupRows({ parent, items, roles, draft, base, overrideMask, onToggle, onRevert }) {
  return (
    <>
      {parent && (
        <tr className="bg-muted/20">
          <td colSpan={roles.length + 3} className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground sticky left-0">
            ▸ {parent}
          </td>
        </tr>
      )}
      {items.map((it) => (
        <MenuItemRow key={`${it.to}-${it.label}`} item={it} indent={!!parent} roles={roles}
                     draft={draft} base={base} overrideMask={overrideMask}
                     onToggle={onToggle} onRevert={onRevert} />
      ))}
    </>
  );
}

function MenuItemRow({ item, indent, roles, draft, base, overrideMask, onToggle, onRevert }) {
  const res = item.perm;
  const labelCell = (
    <td className={`px-3 py-1 sticky left-0 bg-card z-10 ${indent ? "pl-7" : ""}`}>
      <div className="font-medium text-[12px] leading-tight">{item.label}</div>
      <div className="text-[9px] text-muted-foreground font-mono flex items-center gap-1.5 flex-wrap">
        {item.to}
        {res && <span className="px-1 rounded-sm bg-muted/60 border border-border">{res}</span>}
      </div>
    </td>
  );

  if (item.superAdminOnly || item.vendorOnly || !res) {
    return (
      <tr className="border-t border-border/60" data-testid={`rr-menu-${slug(item)}`}>
        {labelCell}
        <td colSpan={roles.length + 2} className="px-3 py-1 text-[10px] text-muted-foreground">
          {item.superAdminOnly ? <SuperOnlyBadge />
            : item.vendorOnly ? <span className="text-[10px]">Vendor portal only</span>
            : <span className="inline-flex items-center gap-1"><Globe className="h-3 w-3" /> No permission resource mapped — contact developer to gate this page</span>}
        </td>
      </tr>
    );
  }

  const cellFor = (roleToken) => {
    const overridden = ACTIONS.some((a) => overrideMask[res]?.[a]);
    return (
      <td key={roleToken} className={`px-0.5 py-1 text-center ${roleToken === "*" ? "bg-primary/5" : ""}`}>
        <div className="inline-flex gap-[3px]">
          {ACTIONS.map((a) => {
            const allowed = draft[res]?.[a] || new Set();
            const on = allowed.has(roleToken) || (roleToken !== "*" && allowed.has("*"));
            const lockedByWild = roleToken !== "*" && allowed.has("*");
            const baseSet = new Set(base[res]?.[a] || []);
            const baseOn = baseSet.has(roleToken) || (roleToken !== "*" && baseSet.has("*"));
            return (
              <MiniToggle key={a} letter={ACTION_LETTER[a]} tone={a} on={on} diff={on !== baseOn}
                          disabled={lockedByWild}
                          title={`${ACTION_LABEL[a]} — ${roleToken === "*" ? "everyone" : roleToken}${lockedByWild ? " (granted via everyone)" : ""}`}
                          onClick={() => onToggle(res, a, roleToken)}
                          testid={`rr-cell-${res}-${a}-${roleToken === "*" ? "wild" : roleToken}-${slug(item)}`} />
            );
          })}
        </div>
        {overridden && roleToken === "*" && <span className="sr-only">overridden</span>}
      </td>
    );
  };

  const anyOverride = ACTIONS.some((a) => overrideMask[res]?.[a]);
  return (
    <tr className={`border-t border-border/60 ${anyOverride ? "bg-amber-50/40" : ""}`} data-testid={`rr-menu-${slug(item)}`}>
      {labelCell}
      {cellFor("*")}
      {roles.map((r) => cellFor(r))}
      <td className="px-2 py-1 text-right">
        {anyOverride && (
          <button className="text-[9px] text-primary hover:underline" title="Revert this resource to code defaults"
                  onClick={() => ACTIONS.forEach((a) => overrideMask[res]?.[a] && onRevert(res, a))}
                  data-testid={`rr-revert-${res}-${slug(item)}`}>
            Revert
          </button>
        )}
      </td>
    </tr>
  );
}

function ResourceRows({ resource, roles, draft, base, overrideMask, onToggle, onRevert }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/30">
          <tr>
            <th className="px-3 py-1.5 text-left w-40 sticky left-0 bg-muted/30">
              <span className="font-display font-bold">{resource.replaceAll("_", " ").toUpperCase()}</span>
            </th>
            <th className="px-1 py-1.5 text-center w-12 bg-primary/5"><Globe className="h-3 w-3 mx-auto" /></th>
            {roles.map((r) => (
              <th key={r} className="px-0.5 py-1.5 text-center min-w-[52px]" title={r}>
                <div className="text-[9px] uppercase tracking-wide leading-tight break-words max-w-[52px] mx-auto">{r.replaceAll("_", " ")}</div>
              </th>
            ))}
            <th className="px-2 py-1.5 w-14"></th>
          </tr>
        </thead>
        <tbody>
          {ACTIONS.map((action) => {
            const allowed = draft[action] || new Set();
            const overridden = !!overrideMask[action];
            const baseSet = new Set(base[action] || []);
            const cell = (roleToken) => {
              const on = allowed.has(roleToken) || (roleToken !== "*" && allowed.has("*"));
              const lockedByWild = roleToken !== "*" && allowed.has("*");
              const baseOn = baseSet.has(roleToken) || (roleToken !== "*" && baseSet.has("*"));
              return (
                <td key={roleToken} className={`px-0.5 py-1 text-center ${roleToken === "*" ? "bg-primary/5" : ""}`}>
                  <MiniToggle letter={ACTION_LETTER[action]} tone={action} on={on} diff={on !== baseOn} disabled={lockedByWild}
                              title={`${ACTION_LABEL[action]} — ${roleToken === "*" ? "everyone" : roleToken}`}
                              onClick={() => onToggle(action, roleToken)}
                              testid={`rr-cell-${resource}-${action}-${roleToken === "*" ? "wild" : roleToken}`} />
                </td>
              );
            };
            return (
              <tr key={action} className={`border-t border-border/60 ${overridden ? "bg-amber-50/40" : ""}`} data-testid={`rr-row-${resource}-${action}`}>
                <td className="px-3 py-1 sticky left-0 bg-card">
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold">
                    {overridden && <AlertTriangle className="h-3 w-3 text-amber-600" />}
                    <span className={action === "delete" ? "text-red-700" : action === "write" ? "text-amber-700" : "text-emerald-700"}>{ACTION_LABEL[action]}</span>
                  </span>
                </td>
                {cell("*")}
                {roles.map((r) => cell(r))}
                <td className="px-2 py-1 text-right">
                  {overridden && (
                    <button className="text-[9px] text-primary hover:underline" onClick={() => onRevert(action)} data-testid={`rr-revert-${resource}-${action}`}>
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
  );
}

function MiniToggle({ letter, tone, on, diff, disabled, title, onClick, testid }) {
  const onClass = tone === "read" ? "bg-emerald-500 border-emerald-600 text-white"
    : tone === "write" ? "bg-amber-500 border-amber-600 text-white"
    : "bg-red-500 border-red-600 text-white";
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title} data-testid={testid}
            className={`relative h-[18px] w-[18px] text-[9px] font-bold border rounded-[3px] leading-none transition-colors
              ${on ? onClass : "bg-background border-border text-muted-foreground hover:bg-muted"}
              ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}>
      {letter}
      {diff && <span className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-amber-500 border border-white" />}
    </button>
  );
}

function MiniDot({ on, tone }) {
  const c = tone === "read" ? "bg-emerald-500" : tone === "write" ? "bg-amber-500" : "bg-red-500";
  return <span className={`w-3 h-3 inline-block rounded-[3px] ${on ? c : "bg-background border border-border"}`} />;
}

function slug(item) {
  return `${item.department}-${item.label}`.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
