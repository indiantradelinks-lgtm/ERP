import { useMemo, useState } from "react";
import { Label } from "@/components/ui/label";

const INPUT_CLASS =
  "h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed";

// Searchable employee dropdown. Parent supplies the (already scoped/filtered) employee list.
export function EmployeeSearchSelect({ employees = [], value, onChange, label = "Employee",
                                       testid = "employee-search-select", placeholder = "Search employee…",
                                       required = false, disabled = false, className = "" }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const selected = employees.find((e) => e.id === value);
  const code = (e) => e.employee_id || e.emp_code || "";

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return employees;
    return employees.filter((e) =>
      [e.name, e.employee_id, e.emp_code, e.department, e.designation, e.current_project_code]
        .some((v) => (v || "").toLowerCase().includes(s)));
  }, [employees, q]);

  return (
    <div className={`relative ${className}`}>
      {label && <Label className="text-[10px] uppercase tracking-wider">{label}{required && " *"}</Label>}
      <input
        value={open ? q : (selected ? `${selected.name}${code(selected) ? ` (${code(selected)})` : ""}` : "")}
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
          {filtered.slice(0, 150).map((e) => (
            <button
              key={e.id}
              type="button"
              onMouseDown={(ev) => { ev.preventDefault(); onChange(e.id, e); setOpen(false); setQ(""); }}
              className={`w-full text-left px-2.5 py-1.5 text-sm hover:bg-secondary ${e.id === value ? "bg-secondary" : ""}`}
              data-testid={`${testid}-option-${e.id}`}
            >
              <div className="font-medium">{e.name} {code(e) && <span className="text-[11px] text-muted-foreground">({code(e)})</span>}</div>
              <div className="text-[10px] text-muted-foreground">
                {[(e.departments || [])[0] || e.department, e.designation, e.current_project_code || "Head Office"].filter(Boolean).join(" · ")}
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="p-2.5 text-xs text-muted-foreground">No matching employees</div>
          )}
        </div>
      )}
    </div>
  );
}
