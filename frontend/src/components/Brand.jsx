import { cn } from "@/lib/utils";

/**
 * INDIAN TRADE LINKS brand mark — single source of truth for the brand block
 * shown in the sidebar, login page, landing page, and footer.
 *
 * The native logo file is wide (~2.2:1 aspect). We render it inside a
 * pill-shaped container so the colourful "ITL" letterforms stay legible
 * even when collapsed.
 */
export default function Brand({ compact = false, className = "" }) {
  return (
    <div className={cn("flex items-center gap-3", className)} data-testid="brand-logo">
      <div className="h-11 min-w-[80px] px-2 flex items-center justify-center bg-white rounded-sm shadow-[0_0_0_1px_hsl(var(--border))] overflow-hidden">
        <img
          src="/brand/itl-logo.jpg"
          alt="INDIAN TRADE LINKS"
          className="h-9 max-w-full object-contain"
          loading="eager"
          decoding="async"
        />
      </div>
      {!compact && (
        <div className="leading-tight">
          <div className="font-display font-black text-[13px] tracking-tight uppercase">Indian Trade Links</div>
          <div className="text-[9px] uppercase tracking-[0.18em] opacity-60 -mt-0.5">Industrial Services Pvt. Ltd.</div>
        </div>
      )}
    </div>
  );
}
