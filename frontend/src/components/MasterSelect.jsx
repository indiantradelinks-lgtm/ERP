/**
 * Shared master-data dropdown components (master-dropdown rollout, Phase 0).
 *
 * Single source of truth for Project / Site / Client / Category / Item pickers,
 * modelled on DepartmentSelect.jsx. Each entity:
 *   - fetches its master list from the existing (read-only) backend endpoint,
 *   - caches it at module level (with in-flight de-dupe) so repeated mounts
 *     don't refetch,
 *   - exposes a use<Entity>() hook returning the raw rows, and
 *   - exports a drop-in <EntitySelect> rendering a native <select> styled like
 *     the rest of the app's form fields.
 *
 * <EntitySelect> calls onChange(value, row): `value` is the selected option's
 * value (configurable via `valueKey`), `row` is the full master record so a
 * caller can also stamp a companion id field (e.g. project_id alongside
 * project_code). Callers that only need the value can ignore the second arg.
 *
 * To avoid silently blanking legacy records, if the bound `value` doesn't match
 * any current option it is still shown as an "(existing)" option.
 *
 * Endpoints (all already exist):
 *   Project   GET /projects
 *   Client    GET /clients
 *   Category  GET /procurement/master/categories
 *   Site      GET /sites[?client_id=]
 *   Item      GET /procurement/master/items[?category_id=]
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Label } from "@/components/ui/label";

const SELECT_CLASS =
  "h-9 w-full mt-1 rounded-sm border border-input bg-background px-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed";

// ── styled native select shared by every picker ───────────────────────────
function BaseSelect({ value, onChange, options, label, testid, disabled = false,
                      required = false, hint, includeBlank = true,
                      placeholder = "— select —", className = "" }) {
  const hasValue = value !== undefined && value !== null && value !== "";
  const matches = options.some((o) => String(o.value) === String(value));
  return (
    <div className={className}>
      {label && (
        <Label className="text-[10px] uppercase tracking-wider">
          {label}{required && " *"}
        </Label>
      )}
      <select
        value={value ?? ""}
        onChange={(e) => {
          const opt = options.find((o) => String(o.value) === e.target.value);
          onChange(e.target.value, opt ? opt.row : null);
        }}
        disabled={disabled}
        className={SELECT_CLASS}
        data-testid={testid}
      >
        {includeBlank && <option value="">{placeholder}</option>}
        {/* Keep an unmatched legacy value visible instead of silently blanking it. */}
        {hasValue && !matches && <option value={value}>{`${value} (existing)`}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {hint && <p className="text-[10px] text-muted-foreground mt-0.5">{hint}</p>}
    </div>
  );
}

// ── cache factory for parameterless master lists ──────────────────────────
function makeGlobalList(endpoint) {
  let cache = null;
  let inflight = null;
  async function fetchAll(forceReload = false) {
    if (cache && !forceReload) return cache;
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const { data } = await api.get(endpoint);
        cache = Array.isArray(data) ? data : [];
      } catch {
        cache = [];
      } finally {
        inflight = null;
      }
      return cache;
    })();
    return inflight;
  }
  function useList() {
    const [list, setList] = useState(cache || []);
    useEffect(() => {
      let alive = true;
      // fetchAll() resolves immediately to the cache when already loaded, so
      // setState always happens asynchronously inside the effect.
      fetchAll().then((d) => { if (alive) setList(d); });
      return () => { alive = false; };
    }, []);
    return list;
  }
  return { fetchAll, useList };
}

// ── cache factory for lists scoped by a single query param (keyed cache) ───
function makeKeyedList(endpoint, paramName) {
  const cache = {};      // key -> rows
  const inflight = {};   // key -> promise
  async function fetchFor(paramValue, forceReload = false) {
    const key = paramValue || "__all__";
    if (cache[key] && !forceReload) return cache[key];
    if (inflight[key]) return inflight[key];
    inflight[key] = (async () => {
      try {
        const params = paramValue ? { [paramName]: paramValue } : {};
        const { data } = await api.get(endpoint, { params });
        cache[key] = Array.isArray(data) ? data : [];
      } catch {
        cache[key] = [];
      } finally {
        delete inflight[key];
      }
      return cache[key];
    })();
    return inflight[key];
  }
  function useList(paramValue) {
    const [list, setList] = useState(cache[paramValue || "__all__"] || []);
    useEffect(() => {
      let alive = true;
      fetchFor(paramValue).then((d) => { if (alive) setList(d); });
      return () => { alive = false; };
    }, [paramValue]);
    return list;
  }
  return { fetchFor, useList };
}

// ─── Project ───────────────────────────────────────────────────────────────
const _projects = makeGlobalList("/projects");
export const fetchProjects = _projects.fetchAll;
export const useProjects = _projects.useList;

export function ProjectSelect({ value, onChange, label = "Project", testid = "project-select",
                                valueKey = "code", disabled = false, required = false, hint,
                                includeBlank = true, includeHeadOffice = false,
                                placeholder = "— select project —", className = "" }) {
  const rows = useProjects();
  const options = [
    ...(includeHeadOffice ? [{ value: "HEAD-OFFICE", label: "HEAD-OFFICE · Head Office (Delhi)" }] : []),
    ...rows.map((p) => ({
      value: p[valueKey] ?? p.code ?? p.id,
      label: [p.code, p.name].filter(Boolean).join(" · ") || p.name || p.code || p.id,
      row: p,
    })),
  ];
  const emptyPlaceholder = options.length === 0 ? "No Project Assigned" : placeholder;
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, className }} placeholder={emptyPlaceholder} />;
}

// ─── Client ──────────────────────────────────────────────────────────────
const _clients = makeGlobalList("/clients");
export const fetchClients = _clients.fetchAll;
export const useClients = _clients.useList;

export function ClientSelect({ value, onChange, label = "Client", testid = "client-select",
                               valueKey = "name", disabled = false, required = false, hint,
                               includeBlank = true, placeholder = "— select client —", className = "" }) {
  const rows = useClients();
  const options = rows.map((c) => ({
    value: c[valueKey] ?? c.name ?? c.id,
    label: c.name || c.id,
    row: c,
  }));
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}

// ─── Category (procurement master) ──────────────────────────────────────────
const _categories = makeGlobalList("/procurement/master/categories");
export const fetchCategories = _categories.fetchAll;
export const useCategories = _categories.useList;

export function CategorySelect({ value, onChange, label = "Category", testid = "category-select",
                                 valueKey = "code", disabled = false, required = false, hint,
                                 includeBlank = true, placeholder = "— select category —", className = "" }) {
  const rows = useCategories();
  const options = rows.map((c) => ({
    value: c[valueKey] ?? c.code ?? c.id,
    label: [c.code, c.name].filter(Boolean).join(" · ") || c.name || c.code,
    row: c,
  }));
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}

// ─── Site (scoped by client_id when provided) ───────────────────────────────
const _sites = makeKeyedList("/sites", "client_id");
export const fetchSites = _sites.fetchFor;
export function useSites(clientId) { return _sites.useList(clientId); }

export function SiteSelect({ value, onChange, clientId, label = "Site", testid = "site-select",
                             valueKey = "site_code", disabled = false, required = false, hint,
                             includeBlank = true, placeholder = "— select site —", className = "" }) {
  const rows = useSites(clientId);
  const options = rows.map((s) => {
    const display = s.name || s.site_name || `${s.client_name || ""}${s.city ? " — " + s.city : ""}`;
    return {
      value: s[valueKey] ?? s.site_code ?? s.id,
      label: [s.site_code, display].filter(Boolean).join(" · ") || s.site_code || s.id,
      row: s,
    };
  });
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}

// ─── Site Location (centralized: Site Master + handovers + projects) ────────
const _siteLocations = makeGlobalList("/sites/locations");
export function SiteLocationSelect({ value, onChange, clientId, label = "Site Location",
                                     testid = "site-location-select", disabled = false, required = false,
                                     hint, includeBlank = true, placeholder = "— select site location —",
                                     className = "" }) {
  const rows = _siteLocations.useList();
  const options = rows.map((s) => ({ value: s.location, label: s.location, row: s }));
  // keep a manually-typed / legacy value selectable
  if (value && !options.some((o) => o.value === value)) {
    options.unshift({ value, label: value, row: { location: value } });
  }
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}

// ─── Item (scoped by category_id when provided) ─────────────────────────────
const _items = makeKeyedList("/procurement/master/items", "category_id");
export const fetchItems = _items.fetchFor;
export function useItems(categoryId) { return _items.useList(categoryId); }

export function ItemSelect({ value, onChange, categoryId, label = "Item", testid = "item-select",
                            valueKey = "code", disabled = false, required = false, hint,
                            includeBlank = true, placeholder = "— select item —", className = "" }) {
  const rows = useItems(categoryId);
  const options = rows.map((i) => ({
    value: i[valueKey] ?? i.code ?? i.id,
    label: [i.code, i.name].filter(Boolean).join(" · ") || i.name || i.code,
    row: i,
  }));
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}

// ─── Purchase / work order (shown as "PO" in billing) ───────────────────────
// The /orders endpoint returns all orders; orders link to a project via
// `project_code` and carry the client as `customer` (there is no client_id on
// an order). We filter client-side by the optional `projectCode` / `customer`
// props so callers can scope the PO list to the selected project/client.
const _orders = makeGlobalList("/orders");
export const fetchOrders = _orders.fetchAll;
export const useOrders = _orders.useList;

export function POSelect({ value, onChange, projectCode, customer, label = "PO Number",
                           testid = "po-select", valueKey = "order_no", disabled = false,
                           required = false, hint, includeBlank = true,
                           placeholder = "— select PO —", className = "" }) {
  const rows = useOrders();
  const filtered = rows.filter((o) =>
    (!projectCode || o.project_code === projectCode) &&
    (!customer || o.customer === customer));
  const options = filtered.map((o) => ({
    value: o[valueKey] ?? o.order_no ?? o.id,
    label: [o.order_no, o.customer].filter(Boolean).join(" · ") || o.order_no || o.id,
    row: o,
  }));
  return <BaseSelect {...{ value, onChange, options, label, testid, disabled, required, hint, includeBlank, placeholder, className }} />;
}
