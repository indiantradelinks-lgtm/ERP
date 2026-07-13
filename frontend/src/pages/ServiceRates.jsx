import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Trash2, Edit2, RefreshCw, X, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const SERVICES = ["scaffolding", "painting", "rope_access", "insulation", "roof_sheeting", "other"];
const UNITS = ["m²", "m³", "m", "Nos", "kg", "ltr", "day", "shift", "hour"];
const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const blank = () => ({ service: "scaffolding", activity: "", unit: "m²", standard_rate: 0, description: "", effective_from: new Date().toISOString().slice(0, 10), effective_until: "", notes: "" });

export default function ServiceRates() {
  const [rows, setRows] = useState([]);
  const [serviceFilter, setServiceFilter] = useState("");
  const [activeOnly, setActiveOnly] = useState(true);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editing, setEditing] = useState(null);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (serviceFilter) params.set("service", serviceFilter);
      if (activeOnly) params.set("active_only", "true");
      const qs = params.toString() ? `?${params.toString()}` : "";
      const r = await api.get(`/service-rates${qs}`);
      setRows(r.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [serviceFilter, activeOnly]);

  const save = async () => {
    if (!form.activity.trim()) { toast.error("activity is required"); return; }
    try {
      const payload = {
        ...form, standard_rate: Number(form.standard_rate) || 0,
        effective_until: form.effective_until || null,
      };
      if (editing) {
        await api.put(`/service-rates/${editing.id}`, payload);
        toast.success("Updated");
      } else {
        await api.post("/service-rates", payload);
        toast.success("Created");
      }
      setOpen(false); setEditing(null); setForm(blank()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete rate ${r.service} · ${r.activity}?`)) return;
    try { await api.delete(`/service-rates/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const openEdit = (r) => { setEditing(r); setForm({ ...blank(), ...r, effective_until: r.effective_until || "" }); setOpen(true); };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => [r.service, r.activity, r.unit, r.description].some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [rows, query]);

  // Group by service for visual structure
  const grouped = filtered.reduce((acc, r) => { (acc[r.service] = acc[r.service] || []).push(r); return acc; }, {});

  return (
    <div className="space-y-6" data-testid="service-rates-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <Tag className="h-3 w-3" /> Commercial · Master Data
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Service Rate Master</h1>
        <p className="text-sm text-muted-foreground mt-1">Standard rates per service × activity × unit with effective-window control. Quotations &amp; Measurements consume these via the lookup endpoint.</p>
      </div>

      <div className="bg-card border border-border rounded-sm">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-border">
          <div className="relative w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9 h-9 rounded-sm" placeholder="Search service, activity…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="sr-search" />
          </div>
          <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} className="h-9 rounded-sm border border-input bg-background px-2 text-sm" data-testid="sr-service-filter">
            <option value="">All services</option>
            {SERVICES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} data-testid="sr-active-only" /> Active only
          </label>
          <Button variant="outline" size="sm" className="h-9 rounded-sm" onClick={load}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          <div className="ml-auto">
            <Button className="h-9 rounded-sm" onClick={() => { setEditing(null); setForm(blank()); setOpen(true); }} data-testid="sr-add"><Plus className="h-4 w-4 mr-1" /> New Rate</Button>
          </div>
        </div>

        <div className="p-2 space-y-4">
          {Object.keys(grouped).length === 0 && <div className="text-center text-sm text-muted-foreground py-10">No rates configured yet.</div>}
          {Object.entries(grouped).map(([service, items]) => (
            <div key={service} className="border border-border rounded-sm" data-testid={`sr-group-${service}`}>
              <div className="p-2.5 border-b border-border bg-muted/30">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{service.replaceAll("_", " ")} · {items.length} rates</div>
              </div>
              <Table>
                <TableHeader><TableRow className="bg-muted/20 hover:bg-muted/20">
                  <TableHead className="text-[10px] uppercase tracking-wider">Activity</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Unit</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Standard Rate</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Effective</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Description</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {items.map((r) => (
                    <TableRow key={r.id} data-testid={`sr-row-${r.id}`}>
                      <TableCell className="text-sm font-semibold">{r.activity}</TableCell>
                      <TableCell className="text-xs">{r.unit}</TableCell>
                      <TableCell className="font-mono-data tabular text-sm font-bold">{inr(r.standard_rate)}</TableCell>
                      <TableCell className="text-xs">{r.effective_from || "—"}{r.effective_until ? ` → ${r.effective_until}` : ""}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.description || "—"}</TableCell>
                      <TableCell className="text-right">
                        <div className="inline-flex gap-1">
                          <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openEdit(r)} data-testid={`sr-edit-${r.id}`}><Edit2 className="h-3 w-3" /></Button>
                          <Button size="sm" variant="outline" className="h-7 rounded-sm text-destructive border-destructive/40" onClick={() => remove(r)} data-testid={`sr-delete-${r.id}`}><Trash2 className="h-3 w-3" /></Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ))}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl rounded-sm" data-testid="sr-form-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">{editing ? "Edit" : "New"} Service Rate</DialogTitle>
            <DialogDescription className="sr-only">Set the standard rate per service × activity × unit.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <SelectField label="Service" value={form.service} options={SERVICES} onChange={(v) => setForm({ ...form, service: v })} testid="sr-form-service" />
              <Field label="Activity *" value={form.activity} onChange={(v) => setForm({ ...form, activity: v })} testid="sr-form-activity" />
              <SelectField label="Unit" value={form.unit} options={UNITS} onChange={(v) => setForm({ ...form, unit: v })} testid="sr-form-unit" />
              <Field label="Standard rate" type="number" value={form.standard_rate} onChange={(v) => setForm({ ...form, standard_rate: v })} testid="sr-form-rate" />
              <Field label="Effective from" type="date" value={form.effective_from} onChange={(v) => setForm({ ...form, effective_from: v })} testid="sr-form-from" />
              <Field label="Effective until" type="date" value={form.effective_until} onChange={(v) => setForm({ ...form, effective_until: v })} />
            </div>
            <Field label="Description" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
            <TextArea label="Notes" value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} data-testid="sr-form-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", testid }) { return (
  <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>
    <Input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-sm mt-1" data-testid={testid} />
  </div>
);}
function TextArea({ label, value, onChange }) { return (
  <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>
    <Textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="rounded-sm mt-1 min-h-[60px]" />
  </div>
);}
function SelectField({ label, value, options, onChange, testid }) { return (
  <div><Label className="text-[10px] uppercase tracking-wider">{label}</Label>
    <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1" data-testid={testid}>
      {options.map((o) => <option key={o} value={o}>{(o || "").replaceAll("_", " ")}</option>)}
    </select>
  </div>
);}
