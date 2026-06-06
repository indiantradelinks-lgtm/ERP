/**
 * Shared department picker components (Iter 59).
 *
 * Single source of truth for all department dropdowns across the app.
 * Fetches GET /api/departments once per session and caches the result.
 * Use <DepartmentSelect /> for single-pick, <DepartmentMultiSelect /> for multi-pick.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Label } from "@/components/ui/label";

// Module-level cache so multiple components don't refetch on each render.
let _cache = null;
let _inflight = null;

export async function fetchDepartments(forceReload = false) {
  if (_cache && !forceReload) return _cache;
  if (_inflight) return _inflight;
  _inflight = (async () => {
    try {
      const { data } = await api.get("/departments");
      _cache = (data || []).map((d) => d.name || d.code).filter(Boolean).sort();
    } catch {
      _cache = [];
    } finally {
      _inflight = null;
    }
    return _cache;
  })();
  return _inflight;
}

export function useDepartments() {
  const [list, setList] = useState(_cache || []);
  useEffect(() => {
    if (_cache) { setList(_cache); return; }
    fetchDepartments().then(setList);
  }, []);
  return list;
}

/**
 * Drop-in replacement for free-text department inputs.
 * Renders a native <select> styled like the rest of the form fields in the app.
 */
export function DepartmentSelect({ value, onChange, label = "Department", testid = "department-select",
                                    disabled = false, required = false, hint, includeBlank = true, className = "" }) {
  const list = useDepartments();
  return (
    <div className={className}>
      {label && (
        <Label className="text-[10px] uppercase tracking-wider">
          {label}{required && " *"}
        </Label>
      )}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid={testid}
      >
        {includeBlank && <option value="">— select department —</option>}
        {list.map((d) => <option key={d} value={d}>{d}</option>)}
      </select>
      {hint && <p className="text-[10px] text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}

/**
 * Multi-select using a checkbox grid (kept simple, matches the existing
 * pattern used elsewhere in the codebase, no extra dependencies).
 */
export function DepartmentMultiSelect({ value = [], onChange, label = "Departments",
                                          testid = "department-multiselect", disabled = false }) {
  const list = useDepartments();
  const selected = new Set(value || []);
  const toggle = (d) => {
    const next = new Set(selected);
    if (next.has(d)) next.delete(d); else next.add(d);
    onChange(Array.from(next));
  };
  return (
    <div>
      {label && <Label className="text-[10px] uppercase tracking-wider">{label}</Label>}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-1 mt-1" data-testid={testid}>
        {list.map((d) => (
          <label key={d} className={`flex items-center gap-2 px-2 py-1 border rounded-sm text-xs cursor-pointer ${selected.has(d) ? "bg-blue-50 border-blue-400" : "border-input"} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}>
            <input
              type="checkbox"
              checked={selected.has(d)}
              onChange={() => !disabled && toggle(d)}
              disabled={disabled}
              data-testid={`${testid}-${d}`}
            />
            {d}
          </label>
        ))}
        {list.length === 0 && (
          <span className="text-xs text-muted-foreground col-span-3 py-2">Loading departments…</span>
        )}
      </div>
    </div>
  );
}
