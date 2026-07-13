/**
 * Training Expiry Register — bucketed list from safety_trainings.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { GraduationCap, RefreshCcw } from "lucide-react";

const BUCKETS = [
  { key: "expired", label: "Expired", tone: "bg-red-50 text-red-700 border-red-300" },
  { key: "expiring_soon", label: "Expiring in 30 days", tone: "bg-amber-50 text-amber-800 border-amber-300" },
  { key: "expiring_later", label: "Expiring later", tone: "bg-slate-50 text-slate-700 border-slate-200" },
];

export default function TrainingExpiryRegister() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(90);

  const load = async () => {
    try { const r = await api.get(`/safety/training-expiry?days=${days}`); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Load failed"); }
  };
  useEffect(() => { load(); }, [days]);

  return (
    <div className="p-6 space-y-4" data-testid="training-expiry-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-2xl flex items-center gap-2"><GraduationCap className="h-6 w-6 text-amber-600" /> Training Expiry Register</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Trainings from `safety_trainings` bucketed by days-until-expiry.</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Horizon (days):</label>
          <input type="number" min="1" max="365" value={days} onChange={(e) => setDays(Number(e.target.value) || 90)} className="h-8 w-20 rounded-sm border border-input bg-background px-2 text-xs" />
          <Button variant="outline" onClick={load}><RefreshCcw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      {!data ? <div className="text-sm text-muted-foreground">Loading…</div> : (
        <>
          <div className="grid grid-cols-3 gap-3">
            {BUCKETS.map((b) => (
              <div key={b.key} className={`border-2 rounded-sm p-3 ${b.tone}`}>
                <div className="text-[10px] uppercase tracking-wider font-semibold">{b.label}</div>
                <div className="font-display font-black text-3xl tabular leading-none mt-1">{data.counts[b.key] || 0}</div>
              </div>
            ))}
          </div>

          {BUCKETS.map((b) => (
            <section key={b.key} data-testid={`bucket-${b.key}`}>
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-2">{b.label} ({(data[b.key] || []).length})</div>
              <div className="border rounded-sm overflow-hidden bg-card">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-600">
                    <tr><th className="text-left px-3 py-1.5">Training #</th><th className="text-left px-3 py-1.5">Type</th><th className="text-left px-3 py-1.5">Employee</th><th className="text-left px-3 py-1.5">Expiry</th></tr>
                  </thead>
                  <tbody>
                    {(data[b.key] || []).length === 0 && <tr><td colSpan={4} className="text-center py-4 text-slate-400 italic">Nothing in this bucket.</td></tr>}
                    {(data[b.key] || []).map((r) => (
                      <tr key={r.id} className="border-t">
                        <td className="px-3 py-1.5 font-mono">{r.training_no || r.id?.slice(0, 8)}</td>
                        <td className="px-3 py-1.5">{r.training_type || "—"}</td>
                        <td className="px-3 py-1.5">{r.employee_name || r.employee_id || "—"}</td>
                        <td className="px-3 py-1.5">{r.expiry_date || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
