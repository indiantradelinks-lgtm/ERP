/** My Action Items widget · home dashboard · Iter 121
 * Shows pending / overdue counts + top 5 due-soon action items for the
 * current user. Click navigates to the Internal Review page.
 * Backend: /api/me/action-items/summary
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { ListTodo, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function MyActionItemsWidget() {
  const [d, setD] = useState(null);
  const nav = useNavigate();
  useEffect(() => {
    api.get("/me/action-items/summary").then((r) => setD(r.data)).catch(() => setD({ pending: 0, overdue: 0, completed_7d: 0, top: [] }));
  }, []);
  if (!d) return null;
  return (
    <div className="bg-card border border-border rounded-sm p-5 hover:border-primary/40 transition-colors cursor-pointer" onClick={() => nav("/app/ops/internal-review")} data-testid="dash-my-action-items">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground flex items-center gap-1">
        <ListTodo className="h-3.5 w-3.5" /> My Action Items
      </div>
      <div className="flex items-center gap-4 mt-2">
        <div>
          <div className="font-display font-black text-3xl tabular">{d.pending}</div>
          <div className="text-xs text-muted-foreground">pending</div>
        </div>
        <div>
          <div className="font-display font-black text-3xl tabular text-red-500 flex items-center gap-1">
            {d.overdue}
            {d.overdue > 0 && <AlertTriangle className="h-5 w-5" />}
          </div>
          <div className="text-xs text-muted-foreground">overdue</div>
        </div>
        <div>
          <div className="font-display font-black text-3xl tabular text-emerald-500 flex items-center gap-1">
            {d.completed_7d}
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div className="text-xs text-muted-foreground">done (7d)</div>
        </div>
      </div>
      {d.top && d.top.length > 0 && (
        <>
          <div className="h-px bg-border my-3" />
          <ul className="space-y-1.5 text-xs">
            {d.top.map((a) => (
              <li key={a.id} className="flex items-center justify-between" data-testid={`widget-ai-${a.id}`}>
                <span className="truncate flex-1 mr-2">{a.title}</span>
                <span className={`text-[10px] ${a.priority === "critical" ? "text-red-500" : a.priority === "high" ? "text-amber-500" : "text-muted-foreground"}`}>
                  {a.due_date || "-"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
