import { HardHat } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Brand({ compact = false, className = "" }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)} data-testid="brand-logo">
      <div className="relative h-9 w-9 grid place-items-center bg-primary text-primary-foreground rounded-sm shadow-[0_0_0_1px_hsl(var(--border))]">
        <HardHat className="h-5 w-5" strokeWidth={2.5} />
        <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 bg-accent rounded-full ring-2 ring-background" />
      </div>
      {!compact && (
        <div className="leading-tight">
          <div className="font-display font-black text-base tracking-tight">WORKSITE<span className="opacity-70">.</span>CMD</div>
          <div className="text-[10px] uppercase tracking-[0.18em] opacity-60 -mt-0.5">Industrial ERP</div>
        </div>
      )}
    </div>
  );
}
