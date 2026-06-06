import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Activity, Clock, User, ChevronRight } from "lucide-react";
import { Label } from "@/components/ui/label";

export default function ActivityTimeline() {
  const [sp] = useSearchParams();
  const initialHid = sp.get("handover_id") || "";
  const [handovers, setHandovers] = useState([]);
  const [hid, setHid] = useState(initialHid);
  const [events, setEvents] = useState([]);
  const [handover, setHandover] = useState(null);

  useEffect(() => { api.get("/ops/handovers").then((r) => setHandovers(r.data || [])).catch(() => {}); }, []);

  useEffect(() => {
    if (!hid) { setEvents([]); setHandover(null); return; }
    api.get(`/ops/handovers/${hid}/timeline`).then((r) => setEvents(r.data || [])).catch((e) => toast.error(e.response?.data?.detail || "Failed"));
    api.get(`/ops/handovers/${hid}`).then((r) => setHandover(r.data)).catch(() => {});
  }, [hid]);

  return (
    <div className="p-6 space-y-4" data-testid="activity-timeline-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700 mb-1.5">Module · Projects & Operations</div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project Activity Timeline</h1>
        <p className="text-sm text-slate-600 mt-1">Full audit trail of every event in the contract-handover lifecycle.</p>
      </div>

      <div className="bg-white border rounded-lg p-3">
        <Label className="text-[10px] uppercase tracking-wider">Handover</Label>
        <select value={hid} onChange={(e) => setHid(e.target.value)}
                 className="h-10 w-full mt-1 rounded-sm border border-input bg-background px-3 text-sm" data-testid="tl-picker">
          <option value="">— pick a handover —</option>
          {handovers.map((h) => <option key={h.id} value={h.id}>{h.handover_no} · {h.project_name} · {h.client_name}</option>)}
        </select>
      </div>

      {handover && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
          <b>{handover.project_name}</b> · {handover.client_name} · ₹{(handover.contract_value || 0).toLocaleString("en-IN")} · status: <b>{handover.status}</b>
        </div>
      )}

      {hid && (
        <div className="bg-white border rounded-lg p-4">
          {events.length === 0 && <div className="text-sm text-slate-500 py-6">No events recorded yet.</div>}
          <ul className="relative space-y-0">
            {events.map((e, i) => (
              <li key={e.id || i} className="flex gap-3 pb-4 last:pb-0">
                <div className="flex flex-col items-center">
                  <div className="h-2 w-2 rounded-full bg-blue-500 mt-2" />
                  {i < events.length - 1 && <div className="w-px flex-1 bg-slate-200" />}
                </div>
                <div className="flex-1 -mt-0.5">
                  <div className="text-xs text-slate-500 flex items-center gap-2">
                    <Clock className="h-3 w-3" />
                    {(e.at || "").slice(0, 19).replace("T", " ")}
                    <span className="text-slate-300">·</span>
                    <User className="h-3 w-3" />
                    <span className="text-slate-700">{e.by_name || "system"}</span>
                    {e.by_role && <span className="text-slate-400 text-[10px]">({e.by_role})</span>}
                  </div>
                  <div className="text-sm font-medium mt-0.5">{e.message}</div>
                  <div className="text-[10px] uppercase tracking-wider text-blue-600 mt-0.5">{e.event}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
