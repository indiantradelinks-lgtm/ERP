/**
 * Site Master · Projects & Operations
 *
 * A dedicated registry of all client sites — currently sites only existed
 * as a sub-tab inside Clients UI, which made cross-site reporting and
 * project-by-site lookup awkward.
 *
 * Backend: /api/sites (existing CRUD) — this page is a richer view layer with
 *   • client filter
 *   • state filter
 *   • project-count per site (resolved from db.projects on the server side
 *     via /api/sites?_with_project_count=1 — graceful fallback if endpoint
 *     doesn't yet support the flag, we just compute locally).
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { MapPin, Search, RefreshCcw, Building2, ExternalLink, Pencil } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { lookupGet } from "@/lib/lookups";

export default function SiteMaster() {
  const [sites, setSites] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [q, setQ] = useState("");
  const [clientFilter, setClientFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const { user } = useAuth() || {};
  const canEdit = ["super_admin", "director", "general_manager", "dept_head"].includes(user?.role);

  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([
        api.get("/sites"),
        lookupGet("/clients"),
        lookupGet("/projects"),
      ]);
      setSites(a.data);
      setClients(b.data);
      setProjects(c.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load sites");
    }
  };
  useEffect(() => { load(); }, []);

  const projectsBySite = useMemo(() => {
    const m = {};
    projects.forEach((p) => {
      const k = p.site_id || p.site;
      if (!k) return;
      if (!m[k]) m[k] = [];
      m[k].push(p);
    });
    return m;
  }, [projects]);

  const states = useMemo(() => [...new Set(sites.map((s) => s.state).filter(Boolean))].sort(), [sites]);

  const filtered = useMemo(() => {
    const qq = q.toLowerCase().trim();
    return sites.filter((s) => {
      if (clientFilter && s.client_id !== clientFilter) return false;
      if (stateFilter && s.state !== stateFilter) return false;
      if (!qq) return true;
      return [s.site_code, s.name, s.client_name, s.plant_name, s.city, s.state]
        .filter(Boolean).join(" ").toLowerCase().includes(qq);
    });
  }, [sites, q, clientFilter, stateFilter]);

  const totalProjects = sites.reduce((sum, s) => sum + (projectsBySite[s.id]?.length || projectsBySite[s.name]?.length || 0), 0);

  return (
    <div className="p-6 space-y-4" data-testid="page-site-master">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MapPin className="h-6 w-6 text-primary" />
            Site Master
          </h1>
          <p className="text-sm text-muted-foreground">All client sites across regions — primary reference for projects, manpower deployment & material allocation.</p>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="sm-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Refresh
        </Button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total Sites" value={sites.length} />
        <Stat label="Total Clients" value={clients.length} />
        <Stat label="States Covered" value={states.length} />
        <Stat label="Projects Mapped" value={totalProjects} />
      </div>

      {/* Filter bar */}
      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="h-4 w-4 absolute left-2.5 top-3 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, code, city, plant…"
                   className="pl-8 h-9" data-testid="sm-search" />
          </div>
          <select value={clientFilter} onChange={(e) => setClientFilter(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="sm-filter-client">
            <option value="">All clients</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}
                   className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="sm-filter-state">
            <option value="">All states</option>
            {states.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="text-xs text-muted-foreground">{filtered.length} shown</span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Sites</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2">Site Code</th>
                  <th className="px-3 py-2">Site / Plant</th>
                  <th className="px-3 py-2">Client</th>
                  <th className="px-3 py-2">City</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2 text-center">Projects</th>
                  <th className="px-3 py-2 text-center">GPS</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-8 text-slate-400">No sites match the filters</td></tr>
                )}
                {filtered.map((s) => {
                  const projCount = (projectsBySite[s.id] || projectsBySite[s.name] || []).length;
                  return (
                    <tr key={s.id} className="border-b hover:bg-slate-50/50" data-testid={`sm-row-${s.id}`}>
                      <td className="px-3 py-2 font-mono text-primary">{s.site_code || "—"}</td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{s.name}</div>
                        {s.plant_name && s.plant_name !== s.name && (
                          <div className="text-xs text-muted-foreground">{s.plant_name}</div>
                        )}
                      </td>
                      <td className="px-3 py-2">{s.client_name || "—"}</td>
                      <td className="px-3 py-2">{s.city || "—"}</td>
                      <td className="px-3 py-2">{s.state || "—"}</td>
                      <td className="px-3 py-2 text-center">
                        {projCount > 0 ? (
                          <span className="inline-flex items-center text-xs gap-1 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                            <Building2 className="h-3 w-3" /> {projCount}
                          </span>
                        ) : <span className="text-muted-foreground">0</span>}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {s.geo_lat && s.geo_lng ? (
                          <a href={`https://www.google.com/maps?q=${s.geo_lat},${s.geo_lng}`} target="_blank" rel="noreferrer"
                             className="text-blue-600 underline inline-flex items-center gap-0.5 text-xs">
                            map <ExternalLink className="h-3 w-3" />
                          </a>
                        ) : <span className="text-muted-foreground text-xs">—</span>}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                          (s.status || "active") === "active"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-slate-50 text-slate-600 border-slate-200"}`}>
                          {s.status || "active"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        {canEdit && (
                          <Button size="icon" variant="ghost" className="h-7 w-7"
                                   onClick={() => { setEditing(s); setForm({ ...s }); }}
                                   data-testid={`sm-edit-${s.id}`}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <div className="text-xs text-muted-foreground">
        ℹ️ Click the pencil icon on a row to edit site-specific compliance details (safety, PPE, shifts, accommodation).
        To create a NEW site, use <strong>Clients → [select client] → Sites</strong>.
      </div>

      {/* Edit dialog — extended site fields */}
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Site · {editing?.name}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Section title="Basics" />
            <F label="Site Code"><Input value={form.site_code || ""} onChange={(e) => setForm({ ...form, site_code: e.target.value })} /></F>
            <F label="Site Name"><Input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="sm-form-name" /></F>
            <F label="Linked Project Code"><Input value={form.project_code || ""} onChange={(e) => setForm({ ...form, project_code: e.target.value })} /></F>
            <F label="Status">
              <select value={form.status || "active"} onChange={(e) => setForm({ ...form, status: e.target.value })}
                       className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid="sm-form-status">
                <option value="active">active</option><option value="inactive">inactive</option>
              </select>
            </F>
            <F label="Site Address" full><Textarea rows={2} value={form.billing_address || form.site_address || ""} onChange={(e) => setForm({ ...form, site_address: e.target.value })} /></F>

            <Section title="On-Site Contact" />
            <F label="Site Contact Person"><Input value={form.site_contact_person || form.contact_person || ""} onChange={(e) => setForm({ ...form, site_contact_person: e.target.value })} /></F>
            <F label="Site Contact Number"><Input value={form.site_contact_number || form.contact_phone || ""} onChange={(e) => setForm({ ...form, site_contact_number: e.target.value })} /></F>
            <F label="Reporting Gate / Location" full><Input value={form.reporting_gate || ""} onChange={(e) => setForm({ ...form, reporting_gate: e.target.value })} /></F>

            <Section title="Compliance Requirements" />
            <F label="Safety Induction Required">
              <YesNo value={form.safety_induction_required} onChange={(v) => setForm({ ...form, safety_induction_required: v })} testid="sm-form-induction" />
            </F>
            <F label="Medical Fitness Required">
              <YesNo value={form.medical_fitness_required} onChange={(v) => setForm({ ...form, medical_fitness_required: v })} />
            </F>
            <F label="Work Permit Required">
              <YesNo value={form.work_permit_required} onChange={(v) => setForm({ ...form, work_permit_required: v })} />
            </F>
            <F label="PPE Requirement" full>
              <Textarea rows={2} value={form.ppe_requirement || ""} onChange={(e) => setForm({ ...form, ppe_requirement: e.target.value })}
                         placeholder="e.g. Helmet, FBH, Safety shoes, Face shield, FRC coverall" />
            </F>

            <Section title="Working Schedule & Logistics" />
            <F label="Site Working Hours"><Input value={form.site_working_hours || ""} onChange={(e) => setForm({ ...form, site_working_hours: e.target.value })} placeholder="08:00 – 17:30 IST" /></F>
            <F label="Shift Details"><Input value={form.shift_details || ""} onChange={(e) => setForm({ ...form, shift_details: e.target.value })} placeholder="1 shift / 2-shift / round-the-clock" /></F>
            <F label="Accommodation Required">
              <YesNo value={form.accommodation_required} onChange={(v) => setForm({ ...form, accommodation_required: v })} />
            </F>
            <F label="Local Conveyance Required">
              <YesNo value={form.local_conveyance_required} onChange={(v) => setForm({ ...form, local_conveyance_required: v })} />
            </F>
            <F label="Loading/Unloading Requirement" full>
              <Textarea rows={2} value={form.loading_unloading_requirement || ""} onChange={(e) => setForm({ ...form, loading_unloading_requirement: e.target.value })} />
            </F>
            <F label="Site Store Available">
              <YesNo value={form.store_available_at_site} onChange={(v) => setForm({ ...form, store_available_at_site: v })} />
            </F>
            <F label="Remarks" full>
              <Textarea rows={2} value={form.remarks || ""} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            </F>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button disabled={busy} onClick={async () => {
              setBusy(true);
              try {
                await api.put(`/sites/${editing.id}`, { ...editing, ...form });
                toast.success("Site updated");
                setEditing(null);
                load();
              } catch (e) { toast.error(e.response?.data?.detail || "Update failed"); }
              finally { setBusy(false); }
            }} data-testid="sm-form-save">{busy ? "Saving…" : "Save"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Section({ title }) {
  return (
    <div className="md:col-span-2 pt-2 first:pt-0">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary border-b border-border pb-1.5">{title}</div>
    </div>
  );
}
function F({ label, full, children }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}
function YesNo({ value, onChange, testid }) {
  return (
    <select value={value === true ? "yes" : value === false ? "no" : ""}
             onChange={(e) => onChange(e.target.value === "yes" ? true : e.target.value === "no" ? false : null)}
             className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm" data-testid={testid}>
      <option value="">— select —</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>
  );
}

function Stat({ label, value }) {
  return (
    <div className="border rounded-sm p-3 bg-card">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
