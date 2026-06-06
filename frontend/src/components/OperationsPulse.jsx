import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const TONE_STYLES = {
  primary: "border-primary/40 bg-primary/5 hover:bg-primary/10",
  success: "border-success/40 bg-success/5 hover:bg-success/10",
  warning: "border-warning/40 bg-warning/5 hover:bg-warning/10",
  danger: "border-destructive/40 bg-destructive/5 hover:bg-destructive/10",
  info: "border-chart-3/40 bg-chart-3/5 hover:bg-chart-3/10",
  neutral: "border-border bg-card hover:bg-muted/30",
};

const TONE_TEXT = {
  primary: "text-primary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  info: "text-chart-3",
  neutral: "text-foreground",
};

/**
 * Strip of live operational counters rendered above the executive dashboard.
 * Each card is clickable and deep-links to the relevant module.
 */
export default function OperationsPulse() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    const load = () => api
      .get("/dashboard/operations-pulse")
      .then((r) => { if (active) setData(r.data); })
      .catch(() => { if (active) setData({ cards: [] }); });
    load();
    const id = setInterval(load, 60000); // refresh every minute
    return () => { active = false; clearInterval(id); };
  }, []);

  if (!data) return null;
  const cards = data.cards || [];

  return (
    <section data-testid="operations-pulse" aria-label="Operations Pulse">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-3.5 w-3.5 text-primary" />
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">Operations Pulse</div>
        <div className="text-[10px] text-muted-foreground tabular ml-auto">live · refreshes every 60s</div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2 stagger">
        {cards.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => c.deeplink && navigate(c.deeplink)}
            data-testid={`pulse-${c.key}`}
            className={cn(
              "kpi-tile text-left border rounded-sm px-3 py-3 transition-colors",
              TONE_STYLES[c.tone] || TONE_STYLES.neutral,
            )}
          >
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground leading-tight">{c.label}</div>
            <div className={cn("font-display font-black text-3xl tabular leading-none mt-1.5", TONE_TEXT[c.tone] || TONE_TEXT.neutral)}>{c.value}</div>
          </button>
        ))}
      </div>
    </section>
  );
}
