import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/**
 * Monthly deployment calendar — rows are projects, columns are days 1..N.
 * Each deployment renders as a horizontal coloured bar spanning its
 * start_offset → end_offset (clamped to the visible window by the backend).
 */
export default function DeploymentCalendar() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/allocation/calendar?year=${year}&month=${month}`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [year, month]);

  const shift = (delta) => {
    const m = month + delta;
    if (m < 1) { setMonth(12); setYear(year - 1); }
    else if (m > 12) { setMonth(1); setYear(year + 1); }
    else setMonth(m);
  };

  return (
    <div className="space-y-6" data-testid="deployment-calendar">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
            <CalendarDays className="h-3 w-3" /> Operations · Deployment Calendar
          </div>
          <h1 className="font-display font-black text-3xl tracking-tight" data-testid="calendar-month-heading">{MONTHS[month - 1]} {year}</h1>
          <p className="text-sm text-muted-foreground mt-1">Project-wise deployment spans for the selected month.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" className="rounded-sm" onClick={() => shift(-1)} data-testid="calendar-prev" aria-label="Previous month">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" className="rounded-sm" onClick={() => { setYear(today.getFullYear()); setMonth(today.getMonth() + 1); }} data-testid="calendar-today">
            Today
          </Button>
          <Button variant="outline" className="rounded-sm" onClick={() => shift(1)} data-testid="calendar-next" aria-label="Next month">
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-x-auto" data-testid="cal-grid-wrap">
        {loading && <div className="p-6 text-sm text-muted-foreground">Loading…</div>}
        {!loading && data && data.projects.length === 0 && (
          <div className="p-10 text-center text-sm text-muted-foreground">No deployments in this window.</div>
        )}
        {!loading && data && data.projects.length > 0 && <Grid data={data} todayDay={month === today.getMonth() + 1 && year === today.getFullYear() ? today.getDate() : null} />}
      </div>
    </div>
  );
}

function Grid({ data, todayDay }) {
  const colW = 28; // px per day
  const labelW = 220;
  return (
    <div style={{ minWidth: labelW + data.days * colW + 8 }}>
      {/* Header row */}
      <div className="flex border-b border-border sticky top-0 bg-card z-10">
        <div className="font-display font-bold text-[10px] uppercase tracking-wider text-muted-foreground p-2" style={{ width: labelW }}>Project</div>
        <div className="flex">
          {Array.from({ length: data.days }, (_, i) => i + 1).map((d) => (
            <div
              key={d}
              className={cn(
                "text-[10px] uppercase tracking-wider text-center py-2 border-l border-border",
                todayDay === d && "bg-primary/10 text-primary font-bold",
              )}
              style={{ width: colW }}
            >
              {d}
            </div>
          ))}
        </div>
      </div>

      {/* Project rows */}
      {data.projects.map((p, rowIdx) => (
        <div
          key={p.project}
          className={cn("flex border-b border-border", rowIdx % 2 === 1 && "bg-muted/30")}
          data-testid={`cal-row-${p.project}`}
        >
          <div className="font-display font-bold text-sm p-2 truncate" style={{ width: labelW }} title={p.project}>
            {p.project}
            <div className="text-[10px] font-normal text-muted-foreground">{p.deployments.length} deployed</div>
          </div>
          <div className="relative" style={{ width: data.days * colW, minHeight: Math.max(38, p.deployments.length * 18) }}>
            {/* Day separators */}
            {Array.from({ length: data.days - 1 }, (_, i) => i + 1).map((d) => (
              <div key={d} className="absolute top-0 bottom-0 border-l border-border" style={{ left: d * colW }} />
            ))}
            {/* Today marker */}
            {todayDay && (
              <div className="absolute top-0 bottom-0 bg-primary/15" style={{ left: (todayDay - 1) * colW, width: colW }} />
            )}
            {/* Deployment bars stacked vertically */}
            {p.deployments.map((d, i) => {
              const left = (d.start_offset - 1) * colW + 2;
              const width = Math.max((d.end_offset - d.start_offset + 1) * colW - 4, colW - 4);
              const tone = d.status === "pending_approval"
                ? "bg-warning/30 border-warning text-warning"
                : "bg-primary/20 border-primary/60 text-primary";
              return (
                <div
                  key={d.id}
                  className={cn("absolute h-[14px] rounded-sm border text-[10px] font-bold uppercase tracking-wider px-1 truncate", tone)}
                  style={{ top: 4 + i * 18, left, width }}
                  title={`${d.employee} · ${d.site_role} · ${d.shift}`}
                  data-testid={`cal-bar-${d.id}`}
                >
                  {d.employee}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
