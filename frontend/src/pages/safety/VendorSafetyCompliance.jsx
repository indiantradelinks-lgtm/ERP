/**
 * Vendor Safety Compliance (Phase 4) — safety-side vetting of vendors.
 * A vendor cannot be safety-approved if mandatory docs are missing or expired.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Truck, Plus, RefreshCcw } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

const APPROVAL_TONE = {
  approved: "bg-emerald-100 text-emerald-800",
  not_approved: "bg-red-100 text-red-800",
};

const EMPTY = {
  vendor_id: "", vendor_name: "", vendor_type: "",
  project_id: "", project_code: "",
  safety_doc_valid_till: "", labour_licence_valid_till: "",
  pf_esic_valid: false, insurance_valid_till: "",
  training_ok: false, ppe_ok: false, work_permit_ok: false,
  mandatory_docs_present: false, remarks: "",
};

export default function VendorSafetyCompliance() {
  const [rows, setRows] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [projects, setProjects] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);

  const load = async () => {
    try {
      const [a, b, c] = await Promise.all([
        api.get("/safety/vendor-compliance"),
        lookupGet("/vendors"),
        lookupGet("/projects"),
      ]);
      setRows(a.data || []); setVendors(b.data || []); setProjects(c.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const payload = { ...form };
      ["safety_doc_valid_till", "labour_licence_valid_till", "insurance_valid_till"].forEach((k) => {
        if (!payload[k]) delete payload[k];
      });
      await api.post(`/safety/vendor-compliance`, payload);
      toast.success("Recorded");
      setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  return (
    <div className="p-6 space-y-4" data-testid="vendor-safety-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety · Phase 4</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2">
            <Truck className="h-6 w-6 text-red-600" /> Vendor Safety Compliance
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            HSE clearance for vendors — safety docs, labour licence, PF/ESIC, insurance, training, PPE, permits.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
          <Button onClick={() => { setEditing({}); setForm(EMPTY); }} data-testid="vsc-new">
            <Plus className="h-4 w-4 mr-1" /> New Record
          </Button>
        </div>
      </div>

      <div className="border rounded-sm overflow-hidden bg-card">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="text-left px-3 py-2">Vendor</th>
              <th className="text-left px-3 py-2">Project</th>
              <th className="text-left px-3 py-2">Safety Doc</th>
              <th className="text-left px-3 py-2">Insurance</th>
              <th className="text-center px-3 py-2">Training</th>
              <th className="text-center px-3 py-2">PPE</th>
              <th className="text-center px-3 py-2">Permits</th>
              <th className="text-left px-3 py-2">HSE Approval</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={8} className="text-center py-8 text-slate-400">No vendor safety records yet.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-t hover:bg-slate-50/40" data-testid={`vsc-row-${r.id}`}>
                <td className="px-3 py-2">
                  <div className="font-semibold">{r.vendor_name || r.vendor_id}</div>
                  <div className="text-xs text-slate-500">{r.vendor_type || ""}</div>
                </td>
                <td className="px-3 py-2">{r.project_code || "—"}</td>
                <td className="px-3 py-2">{r.safety_doc_valid_till || "—"}</td>
                <td className="px-3 py-2">{r.insurance_valid_till || "—"}</td>
                <td className="px-3 py-2 text-center">{r.training_ok ? "✔" : "✗"}</td>
                <td className="px-3 py-2 text-center">{r.ppe_ok ? "✔" : "✗"}</td>
                <td className="px-3 py-2 text-center">{r.work_permit_ok ? "✔" : "✗"}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${APPROVAL_TONE[r.safety_approval_state] || "bg-slate-100"}`}>
                    {(r.safety_approval_state || "").replace(/_/g, " ")}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Vendor Safety Compliance Record</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Vendor</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.vendor_id} onChange={(e) => {
                const v = vendors.find((x) => x.id === e.target.value);
                setForm({ ...form, vendor_id: e.target.value, vendor_name: v?.name || "", vendor_type: v?.category || "" });
              }} data-testid="vsc-vendor">
                <option value="">— Select —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Project</Label>
              <select className="w-full border rounded h-10 px-2 text-sm" value={form.project_id} onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                setForm({ ...form, project_id: e.target.value, project_code: p?.code || "" });
              }}>
                <option value="">— Optional —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
            <div>
              <Label>Safety Doc Valid Till</Label>
              <Input type="date" value={form.safety_doc_valid_till} onChange={(e) => setForm({ ...form, safety_doc_valid_till: e.target.value })} />
            </div>
            <div>
              <Label>Labour Licence Valid Till</Label>
              <Input type="date" value={form.labour_licence_valid_till} onChange={(e) => setForm({ ...form, labour_licence_valid_till: e.target.value })} />
            </div>
            <div>
              <Label>Insurance Valid Till</Label>
              <Input type="date" value={form.insurance_valid_till} onChange={(e) => setForm({ ...form, insurance_valid_till: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-2 col-span-2">
              {["pf_esic_valid", "training_ok", "ppe_ok", "work_permit_ok", "mandatory_docs_present"].map((k) => (
                <label key={k} className="flex items-center gap-2 text-sm border rounded px-2 py-1.5">
                  <input type="checkbox" checked={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} data-testid={`vsc-${k}`} />
                  <span className="capitalize">{k.replace(/_/g, " ")}</span>
                </label>
              ))}
            </div>
            <div className="col-span-2">
              <Label>Remarks</Label>
              <Textarea rows={2} value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} data-testid="vsc-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
