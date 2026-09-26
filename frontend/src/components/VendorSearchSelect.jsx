import { useMemo, useState } from "react";
import { Label } from "@/components/ui/label";

const INPUT_CLASS =
  "h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed";

/**
 * Searchable vendor dropdown used everywhere a vendor is picked by name.
 * `valueKey` decides what is stored in the form — "name" (default) or "id".
 * Parent supplies the already-scoped vendor list (e.g. approved vendors only).
 */
export function VendorSearchSelect({ vendors = [], value, onChange, label = "Vendor",
                                     testid = "vendor-search-select", placeholder = "Search vendor by name / code…",
                                     valueKey = "name", required = false, disabled = false,
                                     emptyNote = "", className = "" }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const selected = vendors.find((v) => String(v[valueKey]) === String(value));

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return vendors;
    return vendors.filter((v) =>
      [v.name, v.vendor_code, v.gst, v.gstin, v.city, v.category, (v.categories || []).join(" ")]
        .some((x) => (x || "").toString().toLowerCase().includes(s)));
  }, [vendors, q]);

  return (
    <div className={`relative ${className}`}>
      {label && <Label className="text-[10px] uppercase tracking-wider">{label}{required && " *"}</Label>}
      <input
        value={open ? q : (selected ? `${selected.name}${selected.vendor_code ? ` (${selected.vendor_code})` : ""}` : "")}
        onChange={(e) => { setQ(e.target.value); if (!open) setOpen(true); }}
        onFocus={() => { setOpen(true); setQ(""); }}
        onClick={() => { if (!open) { setOpen(true); setQ(""); } }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        disabled={disabled}
        className={INPUT_CLASS}
        data-testid={testid}
      />
      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-60 overflow-y-auto bg-popover border border-border rounded-sm shadow-md"
             data-testid={`${testid}-list`}>
          {value && (
            <button type="button" onMouseDown={(ev) => { ev.preventDefault(); onChange("", null); setOpen(false); setQ(""); }}
              className="w-full text-left px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-secondary"
              data-testid={`${testid}-clear`}>— clear selection —</button>
          )}
          {filtered.slice(0, 200).map((v) => (
            <button
              key={v.id}
              type="button"
              onMouseDown={(ev) => { ev.preventDefault(); onChange(v[valueKey], v); setOpen(false); setQ(""); }}
              className={`w-full text-left px-2.5 py-1.5 text-sm hover:bg-secondary ${String(v[valueKey]) === String(value) ? "bg-secondary" : ""}`}
              data-testid={`${testid}-option-${v.id}`}
            >
              <div className="font-medium">{v.name} {v.vendor_code && <span className="text-[11px] text-muted-foreground">({v.vendor_code})</span>}</div>
              {(v.city || v.gst || v.gstin || v.category) && (
                <div className="text-[10px] text-muted-foreground">
                  {[v.category, v.city, v.gst || v.gstin].filter(Boolean).join(" · ")}
                </div>
              )}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="p-2.5 text-xs text-muted-foreground">{emptyNote || "No matching vendors"}</div>
          )}
        </div>
      )}
    </div>
  );
}
