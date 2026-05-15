import { cn } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

export default function KPICard({ label, value, sub, delta, deltaTone = "up", icon: Icon, accent = false, testid, className = "", onClick }) {
  return (
    <div
      data-testid={testid}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter") onClick(); } : undefined}
      className={cn(
        "kpi-tile relative bg-card border border-border rounded-sm p-5 flex flex-col gap-2",
        accent && "border-primary/40",
        onClick && "cursor-pointer",
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        {Icon && (
          <div className={cn("h-8 w-8 rounded-sm grid place-items-center border", accent ? "bg-primary/10 border-primary/30 text-primary" : "bg-muted/40 border-border text-muted-foreground")}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
      <div className="font-display font-black text-3xl tabular leading-none">{value}</div>
      <div className="flex items-center gap-2 mt-1 min-h-[20px]">
        {delta != null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-semibold",
              deltaTone === "up" ? "text-success" : "text-destructive"
            )}
          >
            {deltaTone === "up" ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {delta}
          </span>
        )}
        {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
      </div>
    </div>
  );
}
